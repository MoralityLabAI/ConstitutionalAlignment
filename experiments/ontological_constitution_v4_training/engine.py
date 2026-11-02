"""Interleaved paired SFT and capped evaluation; CUDA paths are explicitly invoked."""
from __future__ import annotations
from contextlib import nullcontext
from pathlib import Path
import copy
import gc
import hashlib
import json
import time
from experiments.constitutional_reasoning_gym_v3.runtime import segmented_loss, local_identity
from experiments.ontological_constitution_v4.logic import canon, digest
from .contracts import (ARMS, encode_entry, load_corpus, load_tokenizer, make_schedule, measure,
                        file_hash, source_hashes, validate_schedule, write_json)
from . import evaluation


def named_adapter_parameters(model, arm):
    selected = {}
    for name, parameter in model.named_parameters():
        for component in ('lora_A', 'lora_B'):
            token = f'.{component}.{arm}.'
            if token in '.'+name:
                selected[name.replace(token, f'.{component}.ADAPTER.')] = parameter
    if not selected: raise ValueError('no recognized LoRA parameters for ' + arm)
    return selected


def activate(model, arm):
    model.set_adapter(arm)
    wanted = named_adapter_parameters(model, arm)
    ids = {id(p) for p in wanted.values()}
    for p in model.parameters():
        p.requires_grad_(id(p) in ids)
        if id(p) not in ids: p.grad = None
    return list(wanted.values())


def copy_initialization(model):
    import torch
    a, b = (named_adapter_parameters(model, arm) for arm in ARMS)
    if set(a) != set(b): raise ValueError('adapter architecture mismatch')
    with torch.no_grad():
        for name in a:
            if a[name].shape != b[name].shape: raise ValueError('adapter shape mismatch')
            b[name].copy_(a[name])


def adapter_hash(model, arm):
    h = hashlib.sha256()
    for name, p in sorted(named_adapter_parameters(model, arm).items()):
        t = p.detach().cpu().contiguous()
        h.update(name.encode()); h.update(str(tuple(t.shape)).encode()); h.update(str(t.dtype).encode())
        h.update(t.view(__import__('torch').uint8).numpy().tobytes())
    return h.hexdigest()


def train_pair(model, tokenizer, schedule, out, deadline, clock=time.monotonic):
    """One identical example allocation per arm; independent optimizer state."""
    import torch
    from experiments.ontological_constitution_v4.curriculum import build_rows
    validate_schedule(schedule, build_rows(2))
    out = Path(out); out.mkdir(parents=True, exist_ok=False)
    counts = {a:0 for a in ARMS}; logs = []; status = 'PARTIAL'; error = None
    initial = {a:adapter_hash(model,a) for a in ARMS}
    if len(set(initial.values())) != 1: raise ValueError('adapters must start identically')
    optimizers = {}
    for a in ARMS: optimizers[a] = torch.optim.AdamW(activate(model,a), lr=1e-4)
    device = next(model.parameters()).device
    def checkpoint(label):
        model.save_pretrained(out/label, selected_adapters=list(ARMS), safe_serialization=True)
        write_json(out/(label+'-steps.json'), counts)
    try:
        model.train()
        with (out/'updates.jsonl').open('w',encoding='utf-8',newline='\n') as stream:
            for block in schedule['blocks']:
                for arm in block['arm_order']:
                    if clock() >= deadline: raise TimeoutError('training deadline')
                    entry = block['entries'][arm]; enc = encode_entry(tokenizer, entry)
                    params = activate(model, arm); opt = optimizers[arm]
                    model.zero_grad(set_to_none=True); opt.zero_grad(set_to_none=True)
                    ids = torch.tensor([enc['input_ids']],device=device)
                    labels = torch.tensor([enc['labels']],device=device)
                    segments = torch.tensor([enc['segments']],device=device)
                    started = clock()
                    loss = segmented_loss(model(input_ids=ids,attention_mask=torch.ones_like(ids),use_cache=False).logits,
                                          labels,segments,enc['rationale_weight'],enc['action_weight'])
                    if not torch.isfinite(loss): raise FloatingPointError('nonfinite training loss')
                    loss.backward(); norm = torch.nn.utils.clip_grad_norm_(params,1.)
                    if not torch.isfinite(norm): raise FloatingPointError('nonfinite gradient')
                    opt.step(); counts[arm] += 1
                    row = {'block':block['index'],'arm':arm,'step':counts[arm],'pair_id':entry['pair_id'],
                           'kind':entry['kind'],'loss':float(loss.detach().cpu()),'gradient_norm':float(norm.detach().cpu()),
                           'input_tokens':len(enc['input_ids']),'rationale_tokens':enc['segments'].count(1),
                           'action_tokens':enc['segments'].count(2),'seconds':clock()-started}
                    logs.append(row); stream.write(canon(row)+'\n'); stream.flush()
                    del ids,labels,segments,loss
                if block['index'] == 17: checkpoint('half')
            status = 'COMPLETE'
    except TimeoutError as exc:
        error = str(exc)
    except Exception as exc:
        status = 'FAILED'; error = repr(exc)
    finally:
        # Attempt to preserve partial adapters. Never report a save that failed.
        saved = False
        try: checkpoint('final'); saved = True
        except Exception as exc: error = (error or '')+'; checkpoint: '+repr(exc)
        final = {a:adapter_hash(model,a) for a in ARMS}
        receipt = {'status':status,'error':error,'steps':counts,'planned_steps_per_arm':36,
                   'equal_completed_updates':len(set(counts.values()))==1,'updates':len(logs),
                   'schedule_sha256':schedule['sha256'],'initial_adapter_sha256':initial,
                   'final_adapter_sha256':final,'adapters_saved':saved,
                   'source_evidence_class':'CERTIFICATE_RENDERED_PUBLIC_EXPLANATION_AND_CHECKED_PRACTICE',
                   'learning_rate':1e-4,'rationale_weight':.25,'action_weight':1.,
                   'equal_token_counts_claimed':False,'final_test_access':False}
        write_json(out/'training_receipt.json',receipt)
        model.zero_grad(set_to_none=True); optimizers.clear(); gc.collect()
        if torch.cuda.is_available(): torch.cuda.empty_cache()
    return receipt


class LocalActor:
    def __init__(self,model,tokenizer,deadline):
        self.model,self.tok,self.deadline=model,tokenizer,deadline
        self.failure=None
    def __call__(self,arm,messages):
        import torch
        from transformers import StoppingCriteriaList, MaxTimeCriteria
        from experiments.ontological_constitution_v4.dilemmas import parse_choice
        if self.failure is not None:raise RuntimeError('backend stopped after '+self.failure)
        if arm!='base': self.model.set_adapter(arm)
        guard=self.model.disable_adapter() if arm=='base' else nullcontext()
        prompt=self.tok.apply_chat_template(messages,tokenize=False,add_generation_prompt=True,enable_thinking=False)
        inputs=self.tok(prompt,return_tensors='pt',add_special_tokens=False)
        width=inputs.input_ids.shape[1]
        if width+32>4096:raise RuntimeError('evaluation context overflow')
        inputs={k:v.to(self.model.device) for k,v in inputs.items()}
        tokenizer=self.tok
        class Parsed:
            def __call__(self,ids,scores,**kwargs):
                try:parse_choice(tokenizer.decode(ids[0,width:],skip_special_tokens=True));return True
                except (ValueError,TypeError):return False
        remaining=min(20.,self.deadline-time.monotonic())
        if remaining<=0:raise TimeoutError('evaluation deadline')
        start=time.monotonic()
        try:
            with guard, torch.inference_mode():
                output=self.model.generate(**inputs,do_sample=False,max_new_tokens=32,pad_token_id=self.tok.pad_token_id,
                    stopping_criteria=StoppingCriteriaList([Parsed(),MaxTimeCriteria(remaining)]))
        except RuntimeError as exc:
            self.failure=repr(exc)
            raise
        ids=output[0,width:].tolist();text=self.tok.decode(ids,skip_special_tokens=True)
        timed_out=False
        if time.monotonic()-start>=remaining:
            try:parse_choice(text)
            except (ValueError,TypeError):timed_out=True
        return {'text':text,'generated_token_ids':ids,'prompt_tokens':width,'new_tokens':len(ids),
                'seconds':time.monotonic()-start,'timed_out':timed_out}


def pilot(base, revision, corpus, preflight_dir, out, approved=False, seconds=1160):
    if not approved: raise PermissionError('approved bounded pilot required')
    if not 120 <= seconds <= 1160: raise ValueError('pilot wall limit')
    out=Path(out)
    if out.exists():raise FileExistsError('new pilot output directory required')
    start=time.monotonic();deadline=start+seconds
    rows,manifest=load_corpus(corpus);schedule=make_schedule(rows)
    tok,identity=load_tokenizer(base,revision)
    expected=json.loads((Path(preflight_dir)/'tokenizer_preflight.json').read_text())
    measured=measure(tok,rows,schedule)
    if expected['status']!='TOKENIZER_PASS' or expected['tokenizer_evidence']!='RETAINED_NATIVE_TOKENIZER':
        raise ValueError('production tokenizer preflight required')
    if identity!=expected['tokenizer'] or expected['encoding_sha256']!=measured['encoding_sha256']:
        raise ValueError('tokenizer/input encoding drift')
    if expected['source_sha256']!=source_hashes() or expected['schedule_sha256']!=schedule['sha256']:
        raise ValueError('executed source/schedule differs from preflight')
    if expected['corpus_manifest_sha256']!=file_hash(Path(corpus)/'manifest.json'):
        raise ValueError('corpus drift')
    out.mkdir(parents=True);write_json(out/'schedule.json',schedule)
    write_json(out/'tokenizer_preflight.json',expected)
    receipt={'status':'STARTED','source_sha256':source_hashes(),'identity':identity,
             'plan_sha256':schedule['sha256'],'GPU_jobs':1,'old_adapters_reused':False,
             'teacher_generation_calls':0,'final_test_access':False,'seconds_cap':seconds}
    write_json(out/'run.json',receipt)
    model=None
    try:
        import torch
        import transformers,peft
        from transformers import AutoModelForCausalLM
        from peft import LoraConfig,get_peft_model
        if not torch.cuda.is_available() or torch.cuda.device_count()!=1:raise RuntimeError('one visible CUDA device required')
        name=torch.cuda.get_device_name(0);free,total=torch.cuda.mem_get_info(0)
        if 'H100' not in name or total<70*1024**3 or free<64*1024**3:raise RuntimeError('one mostly free H100 80GB required')
        receipt.update(checkpoint=local_identity(base,revision),libraries={'torch':torch.__version__,'transformers':transformers.__version__,'peft':peft.__version__},device=name)
        write_json(out/'run.json',receipt)
        torch.manual_seed(11);torch.cuda.manual_seed_all(11);torch.cuda.reset_peak_memory_stats()
        model=AutoModelForCausalLM.from_pretrained(str(base),local_files_only=True,trust_remote_code=False,
                                                 torch_dtype=torch.bfloat16,device_map={'':0})
        config=LoraConfig(r=16,lora_alpha=32,lora_dropout=0.,target_modules='all-linear',task_type='CAUSAL_LM')
        model=get_peft_model(model,config,adapter_name=ARMS[0]);model.add_adapter(ARMS[1],copy.deepcopy(config))
        copy_initialization(model)
        model.config.use_cache=False;model.gradient_checkpointing_enable();model.enable_input_require_grads()
        training_report=train_pair(model,tok,schedule,out/'training',deadline-300)
        receipt['training']=training_report
        # The common base remains unchanged. Its disabled-adapter forward is a baseline.
        model.eval();model.gradient_checkpointing_disable();model.config.use_cache=True
        actor=LocalActor(model,tok,deadline)
        if training_report['status']=='FAILED':
            def actor(arm,messages):raise RuntimeError('training infrastructure failure; inference withheld')
        scores=evaluation.run(evaluation.make_plan(),actor,out/'evaluation',deadline)
        receipt.update(status=('FAILED' if training_report['status']=='FAILED' else
                       'COMPLETE' if training_report['status']=='COMPLETE' and all(v['unknown']==0 for v in scores['arms'].values()) else 'PARTIAL'),
                       evaluation=scores,peak_cuda_bytes=torch.cuda.max_memory_allocated())
    except Exception as exc:
        receipt.update(status='FAILED',error=repr(exc))
        try:
            import torch
            receipt['peak_cuda_bytes']=torch.cuda.max_memory_allocated() if torch.cuda.is_available() else None
        except ImportError:pass
    finally:
        receipt['elapsed_seconds']=time.monotonic()-start
        write_json(out/'run.json',receipt)
    return receipt
