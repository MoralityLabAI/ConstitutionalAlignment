"""One base load, fresh paired adapters, source-bound training and transfer receipts."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import time
from .admission import load_corpus, implementation_hashes, write_json, strict_loads, hash_file
from .preflight import tokenizer_identity, load_tokenizer, verify_preflight, preflight
from . import evaluation


def train_rounds(plan, step, log_path, deadline, clock=time.monotonic, after_round=None):
    """Outcomes never determine whether the other arm is assigned its update."""
    counts={a:0 for a in plan['arms']};rows=[];status='COMPLETE';errors=[]
    with Path(log_path).open('w',encoding='utf-8',newline='\n') as stream:
        for r in plan['rounds']:
            if clock()>=deadline:status='TIME_CAP';break
            round_errors=[]
            for arm in r['arm_order']:
                try:
                    if clock()>=deadline:raise TimeoutError('training deadline within paired round')
                    item={'status':'UPDATED',**step(arm,r['record_ids'][arm],r['round'])};counts[arm]+=1
                except (RuntimeError,ValueError,TimeoutError,FloatingPointError) as exc:
                    item={'status':'FAILED','error':repr(exc)};round_errors.append(item['error'])
                item.update(arm=arm,round=r['round'],record_id=r['record_ids'][arm]);rows.append(item)
                stream.write(json.dumps(item,sort_keys=True,allow_nan=False)+'\n');stream.flush()
            if round_errors:errors.extend(round_errors);status='PARTIAL';break
            if after_round:after_round(r['round']+1)
    return {'status':status,'steps_completed':counts,'paired_complete_rounds':min(counts.values()),
            'counts_equal':len(set(counts.values()))==1,'errors':errors,'updates_logged':len(rows)}


def state_hash(state):
    h=hashlib.sha256()
    for key,value in sorted(state.items()):
        t=value.detach().contiguous().cpu()
        h.update(key.encode());h.update(str(t.dtype).encode());h.update(str(tuple(t.shape)).encode())
        h.update(t.view(__import__('torch').uint8).numpy().tobytes())
    return h.hexdigest()


def run_pilot(corpus_dir, base, revision, preflight_path, out, approved=False,
              max_seconds=1080, eval_reserve=240, motifs=4, source_revision=None):
    if not approved:raise PermissionError('approved capped pilot required')
    if not 60<=max_seconds<=7200 or not 30<=eval_reserve<max_seconds:raise ValueError('deadline settings')
    base=Path(base);out=Path(out)
    if out.exists():raise FileExistsError('fresh pilot output required')
    report=strict_loads(Path(preflight_path).read_text(encoding='utf-8'))
    identity=tokenizer_identity(base,revision);verify_preflight(report,corpus_dir,identity)
    plan=report['schedule']
    if motifs not in (4,8,12,16):raise ValueError('small counterbalanced development plan required')
    # Validate tokenizer and every source row before reading a weight shard.
    tok=load_tokenizer(base)
    fresh,encoded=preflight(corpus_dir,tok,identity,arms=plan['arms'],steps=plan['steps_per_arm'],
                           seed=plan['seed'],max_length=report['max_length'],view=plan['view'])
    if fresh['sha256']!=report['sha256']:raise ValueError('preflight failed exact reproduction')
    weights=sorted(base.glob('*.safetensors'))
    if not weights:raise FileNotFoundError('retained safetensors required')
    index=base/'model.safetensors.index.json'
    if index.exists():
        for name in set(json.loads(index.read_text())['weight_map'].values()):
            path=Path(name)
            if path.is_absolute() or '..' in path.parts or not (base/path).is_file():raise ValueError('invalid/missing shard')
    import torch
    import transformers
    import peft
    from transformers import AutoModelForCausalLM, StoppingCriteriaList, MaxTimeCriteria
    from peft import LoraConfig, get_peft_model, get_peft_model_state_dict
    from experiments.constitutional_reasoning_gym_v3.runtime import segmented_loss
    if not torch.cuda.is_available() or torch.cuda.device_count()!=1:raise RuntimeError('one visible CUDA GPU required')
    free,total=torch.cuda.mem_get_info()
    if 'H100' not in torch.cuda.get_device_name(0) or total<70*1024**3 or free<65*1024**3:
        raise RuntimeError('one sufficiently free 80GB H100 required')
    out.mkdir(parents=True);write_json(out/'preflight.json',report)
    start=time.monotonic();deadline=start+max_seconds
    torch.cuda.reset_peak_memory_stats()
    receipt={'status':'LOADING','source_revision':source_revision,'source_sha256':implementation_hashes(),
        'preflight_sha256':report['sha256'],'model_identity':identity,'weight_index_sha256':hash_file(index) if index.exists() else None,
        'weight_sizes':{p.name:p.stat().st_size for p in weights},'weight_content_hashes_verified_here':False,
        'libraries':{'torch':torch.__version__,'transformers':transformers.__version__,'peft':peft.__version__},
        'training_seed':plan['seed'],'arms':plan['arms'],'hyperparameters':{'rank':16,'alpha':32,'dropout':0.,'lr':1e-4},
        'steps_requested_per_arm':plan['steps_per_arm'],'corpus_groups':20,'max_seconds':max_seconds,
        'final_test_access':False,'teacher_calls':0,'hub_uploads':0,'matched_outcome_comparison_eligible':False}
    write_json(out/'run.json',receipt)
    try:
        os.environ['HF_HUB_OFFLINE']='1';os.environ['TRANSFORMERS_OFFLINE']='1'
        model=AutoModelForCausalLM.from_pretrained(str(base),local_files_only=True,trust_remote_code=False,
                    torch_dtype=torch.bfloat16,device_map={'':0})
        arms=plan['arms'];cfg=lambda:LoraConfig(r=16,lora_alpha=32,lora_dropout=0.,target_modules='all-linear',task_type='CAUSAL_LM')
        torch.manual_seed(plan['seed']);torch.cuda.manual_seed_all(plan['seed'])
        model=get_peft_model(model,cfg(),adapter_name=arms[0])
        torch.manual_seed(plan['seed']);torch.cuda.manual_seed_all(plan['seed'])
        model.add_adapter(arms[1],cfg())
        initial={a:state_hash(get_peft_model_state_dict(model,adapter_name=a)) for a in arms}
        if len(set(initial.values()))!=1:raise ValueError('paired adapter initialization differs')
        receipt['initial_adapter_sha256']=initial
        parameters={};optimizers={}
        for arm in arms:
            model.set_adapter(arm)
            parameters[arm]=[p for p in model.parameters() if p.requires_grad]
            if not parameters[arm]:raise ValueError('no trainable adapter parameters')
            optimizers[arm]=torch.optim.AdamW(parameters[arm],lr=1e-4)
        if set(map(id,parameters[arms[0]])) & set(map(id,parameters[arms[1]])):
            raise ValueError('paired optimizers share trainable parameters')
        receipt['trainable_parameters']={a:sum(p.numel() for p in ps) for a,ps in parameters.items()}
        model.config.use_cache=False;model.gradient_checkpointing_enable();model.enable_input_require_grads();model.train()
        def step(arm,rid,round_index):
            model.set_adapter(arm);torch.manual_seed(plan['seed']+round_index);torch.cuda.manual_seed_all(plan['seed']+round_index)
            e=encoded[rid];device=model.device
            ids=torch.tensor([e['input_ids']],device=device)
            labels=torch.tensor([e['labels']],device=device);segments=torch.tensor([e['segments']],device=device)
            optimizers[arm].zero_grad(set_to_none=True)
            loss=segmented_loss(model(input_ids=ids,attention_mask=torch.ones_like(ids)).logits,
                                labels,segments,e['rationale_weight'],e['action_weight'])
            if not torch.isfinite(loss):raise FloatingPointError('nonfinite loss')
            loss.backward();norm=torch.nn.utils.clip_grad_norm_(parameters[arm],1.)
            if not torch.isfinite(norm):raise FloatingPointError('nonfinite gradient')
            optimizers[arm].step()
            return {'loss':float(loss.detach().cpu()),'gradient_norm':float(norm.detach().cpu()),
                    'input_tokens':len(e['input_ids']),'rationale_targets':e['segments'].count(1),
                    'action_targets_including_eos':e['segments'].count(2)}
        progress=train_rounds(plan,step,out/'training.jsonl',deadline-eval_reserve)
        receipt['training']=progress
        for arm in arms:
            if any(not torch.isfinite(p).all() for p in parameters[arm]):raise FloatingPointError('nonfinite adapter parameter')
        model.save_pretrained(out/'adapters',safe_serialization=True,selected_adapters=arms)
        tok.save_pretrained(out/'tokenizer')
        receipt['final_adapter_sha256']={a:state_hash(get_peft_model_state_dict(model,adapter_name=a)) for a in arms}
        receipt['adapter_files']={p.relative_to(out).as_posix():hash_file(p) for p in (out/'adapters').rglob('*') if p.is_file()}
        receipt['status']='TRAINED';write_json(out/'run.json',receipt)
        del optimizers
        model.zero_grad(set_to_none=True);model.gradient_checkpointing_disable();model.config.use_cache=True;model.eval()
        torch.cuda.empty_cache()
        class Parsed:
            def __init__(self,n):self.n=n
            def __call__(self,ids,scores,**kwargs):
                try:evaluation.d.parse_choice(tok.decode(ids[0,self.n:],skip_special_tokens=True));return True
                except (ValueError,TypeError):return False
        def generate(arm,text):
            if time.monotonic()>=deadline:raise TimeoutError('evaluation deadline')
            model.set_adapter(arm)
            messages=[{'role':'system','content':'Apply the supplied practical charter. Use the requested numeric action schema.'},
                      {'role':'user','content':text}]
            native=tok.apply_chat_template(messages,tokenize=False,add_generation_prompt=True,enable_thinking=False)
            batch=tok(native,return_tensors='pt',add_special_tokens=False)
            width=batch.input_ids.shape[1]
            if width+48>report['max_length']:raise RuntimeError('evaluation context overflow')
            batch={k:v.to(model.device) for k,v in batch.items()};limit=min(20.,max(.01,deadline-time.monotonic()))
            began=time.monotonic()
            with torch.inference_mode():
                value=model.generate(**batch,do_sample=False,max_new_tokens=48,pad_token_id=tok.pad_token_id,
                    stopping_criteria=StoppingCriteriaList([Parsed(width),MaxTimeCriteria(limit)]))
            ids=value[0,width:].tolist();raw=tok.decode(ids,skip_special_tokens=True)
            try:evaluation.d.parse_choice(raw);valid=True
            except (ValueError,TypeError):valid=False
            return {'text':raw,'token_ids':ids,'native_prompt':native,'native_prompt_sha256':evaluation.digest(native),
                'input_tokens':width,'output_tokens':len(ids),'adapter':arm,
                'timed_out':not valid and time.monotonic()-began>=limit}
        scores=evaluation.run(evaluation.pair_plan(arms,motifs),generate,out/'evaluation',deadline)
        receipt['evaluation']=scores;receipt['status']='COMPLETE' if progress['status']=='COMPLETE' else 'PARTIAL'
        receipt['matched_outcome_comparison_eligible']=progress['status']=='COMPLETE' and not any(x['unknown'] for x in scores['arms'].values())
    except Exception as exc:
        receipt.update(status='FAILED',error=repr(exc));raise
    finally:
        receipt.update(elapsed_seconds=time.monotonic()-start,peak_cuda_allocated_bytes=torch.cuda.max_memory_allocated(),
                       peak_cuda_reserved_bytes=torch.cuda.max_memory_reserved(),provider_billed_minutes=None)
        write_json(out/'run.json',receipt)
    return receipt
