"""Optional local-weight generation and SFT. Importing this file loads no weights."""
from __future__ import annotations
from pathlib import Path
import json
import os
import time
from .core import file_sha, sha, write_json, canon


def local_identity(model_dir, revision):
    root=Path(model_dir).resolve()
    if not root.is_dir() or len(revision)!=40 or any(c not in '0123456789abcdef' for c in revision):
        raise ValueError('existing snapshot and immutable 40-hex revision required')
    needed=('config.json','tokenizer_config.json','tokenizer.json')
    if any(not (root/n).is_file() for n in needed): raise ValueError('missing checkpoint/tokenizer metadata')
    weights=sorted(root.glob('*.safetensors'))
    if not weights: raise ValueError('no local safetensors weights')
    index=root/'model.safetensors.index.json'
    if index.exists():
        names=set(json.loads(index.read_text())['weight_map'].values())
        if any(not (root/n).is_file() for n in names): raise ValueError('missing indexed shard')
    return {'declared_revision':revision,'revision_verified_from_provider':False,
            'metadata_sha256':{n:file_sha(root/n) for n in needed},
            'weight_index_sha256':file_sha(index) if index.exists() else None,
            'weight_files':{p.name:p.stat().st_size for p in weights}}


class HFTeacher:
    evidence_class='MODEL_GENERATED'
    def __init__(self, model_dir, revision, approved=False, max_new_tokens=768,
                 context=4096, per_call_seconds=120, seed=41):
        if not approved: raise PermissionError('model run requires an approved lease')
        if not 32<=max_new_tokens<=2048 or not 1<=per_call_seconds<=300: raise ValueError('invalid generation limits')
        os.environ['HF_HUB_OFFLINE']='1';os.environ['TRANSFORMERS_OFFLINE']='1'
        self.identity=local_identity(model_dir,revision)
        import torch
        import transformers
        from transformers import AutoTokenizer, AutoModelForCausalLM
        if not torch.cuda.is_available(): raise RuntimeError('local CUDA device required')
        self.tok=AutoTokenizer.from_pretrained(model_dir,local_files_only=True,trust_remote_code=False)
        if not self.tok.chat_template: raise ValueError('native chat template required')
        if self.tok.eos_token_id is None: raise ValueError('EOS required')
        if self.tok.pad_token_id is None:self.tok.pad_token_id=self.tok.eos_token_id
        self.tok.padding_side='left'
        self.model=AutoModelForCausalLM.from_pretrained(model_dir,local_files_only=True,
                    trust_remote_code=False,torch_dtype=torch.bfloat16,device_map={'':0})
        self.model.eval(); self.context=context;self.max_new_tokens=max_new_tokens
        self.per_call_seconds=per_call_seconds;self.seed=seed
        self.library={'torch':torch.__version__,'transformers':transformers.__version__}
    def describe(self):
        return {'evidence_class':self.evidence_class,'identity':self.identity,'libraries':self.library,
                'max_new_tokens':self.max_new_tokens,'context':self.context,'seed':self.seed,
                'decoding':{'temperature':0.7,'top_p':0.95,'chat_template':True,'thinking':False},
                'template_sha256':sha(self.tok.chat_template)}
    def generate_many(self,requests):
        import torch
        prompts=[self.tok.apply_chat_template(r['messages'],tokenize=False,add_generation_prompt=True,
                                               enable_thinking=False) for r in requests]
        inp=self.tok(prompts,return_tensors='pt',padding=True,add_special_tokens=False)
        if inp.input_ids.shape[1]+self.max_new_tokens>self.context: raise ValueError('context overflow; no truncation')
        inp={k:v.to(self.model.device) for k,v in inp.items()}
        batch_seed=int(sha([self.seed,[r['request_id'] for r in requests]])[:8],16)
        torch.manual_seed(batch_seed); torch.cuda.manual_seed_all(batch_seed)
        start=time.monotonic()
        with torch.inference_mode():
            result=self.model.generate(**inp,max_new_tokens=self.max_new_tokens,do_sample=True,
                temperature=0.7,top_p=0.95,pad_token_id=self.tok.pad_token_id,
                max_time=self.per_call_seconds)
        rows=[]; width=inp['input_ids'].shape[1]
        for i,token_ids in enumerate(result[:,width:]):
            ids=token_ids.tolist()
            if self.tok.eos_token_id in ids:ids=ids[:ids.index(self.tok.eos_token_id)+1]
            text=self.tok.decode(ids,skip_special_tokens=True)
            rows.append({'text':text,'input_tokens':int(inp['attention_mask'][i].sum()),
                'output_tokens':len(ids),'finish_reason':'eos' if ids and ids[-1]==self.tok.eos_token_id else 'cap',
                'batch_seed':batch_seed,'batch_seconds':time.monotonic()-start,
                'raw_generated_token_ids':ids})
        return rows


def encode_sft(tokenizer,row,max_length=4096):
    """Identical within-frame token streams; change only rationale-loss weights."""
    messages=[{'role':'system','content':row['system']},{'role':'user','content':row['user']}]
    if getattr(tokenizer,'chat_template',None):
        p=tokenizer.apply_chat_template(messages,tokenize=False,add_generation_prompt=True,enable_thinking=False)
    else:
        # Explicit fixture fallback; production command requires a native template.
        p='System: '+row['system']+'\nUser: '+row['user']+'\nAssistant: '
    prompt=tokenizer.encode(p,add_special_tokens=False)
    reason=[] if row.get('format_only') else tokenizer.encode('Rationale:\n'+row['rationale']+'\n',add_special_tokens=False)
    action=tokenizer.encode(('' if row.get('format_only') else 'Action:\n')+row['final'],add_special_tokens=False)
    eos=tokenizer.eos_token_id
    if eos is None or eos in reason+action: raise ValueError('exactly one natural EOS required')
    ids=prompt+reason+action+[eos]
    if len(ids)>max_length: raise ValueError('context overflow')
    # Segment codes separate prompt, public explanation and final action for normalized loss.
    seg=[0]*len(prompt)+[1]*len(reason)+[2]*(len(action)+1)
    labels=[-100]*len(prompt)+reason+action+[eos]
    if row['rationale_weight']==0: labels[len(prompt):len(prompt)+len(reason)]=[-100]*len(reason)
    return {'input_ids':ids,'labels':labels,'segments':seg,
            'rationale_weight':row['rationale_weight'],'action_weight':row['action_weight']}


def segmented_loss(logits,labels,segments,rationale_weight=.25,action_weight=1.):
    """Per-example mean CE per segment. Sequence length cannot silently dominate."""
    import torch
    if logits.ndim!=3 or labels.shape!=segments.shape or logits.shape[:2]!=labels.shape: raise ValueError('tensor shapes')
    loss=torch.nn.functional.cross_entropy(logits[:,:-1].reshape(-1,logits.shape[-1]),
                  labels[:,1:].reshape(-1),ignore_index=-100,reduction='none').view_as(labels[:,1:])
    terms=[]
    for i in range(labels.shape[0]):
        value=loss[i].sum()*0
        for seg,weight in ((1,rationale_weight),(2,action_weight)):
            mask=(segments[i,1:]==seg)&(labels[i,1:]!=-100)
            if mask.any(): value=value+float(weight)*loss[i][mask].mean()
            elif seg==2:raise ValueError('no final-action targets')
        terms.append(value)
    return torch.stack(terms).mean()


def train_local(model_dir, revision, dataset, out, approved=False, steps=200, seconds=1200, seed=11):
    if not approved: raise PermissionError('approved training lease required')
    if not 1<=steps<=10000 or not 1<=seconds<=86400: raise ValueError('resource limits')
    out=Path(out)
    if out.exists(): raise ValueError('fresh run directory required')
    identity=local_identity(model_dir,revision)
    rows=[json.loads(x) for x in Path(dataset).read_text().splitlines() if x.strip()]
    if not rows or any(r['split']!='train' or r['source_evidence_class']!='MODEL_GENERATED' for r in rows):
        raise ValueError('only accepted model-generated train rows')
    if len({r['arm'] for r in rows})!=1:raise ValueError('one arm per run')
    if len({r['record_id'] for r in rows})!=len(rows):raise ValueError('duplicate training records')
    import torch
    from transformers import AutoTokenizer,AutoModelForCausalLM
    from peft import LoraConfig,get_peft_model
    if not torch.cuda.is_available():raise RuntimeError('CUDA required')
    os.environ['HF_HUB_OFFLINE']='1';os.environ['TRANSFORMERS_OFFLINE']='1'
    torch.manual_seed(seed);torch.cuda.manual_seed_all(seed)
    out.mkdir(parents=True);start=time.monotonic();status='FAILED';logs=[]
    receipt={'dataset_sha256':file_sha(dataset),'identity':identity,'seed':seed,'arm':rows[0]['arm'],
             'model_evaluation':False,'final_test_access':False,'steps_requested':steps}
    try:
        tok=AutoTokenizer.from_pretrained(model_dir,local_files_only=True,trust_remote_code=False)
        if not tok.chat_template:raise ValueError('native chat template required')
        examples=[encode_sft(tok,r) for r in rows]
        receipt['input_tokens_one_pass']=sum(len(e['input_ids']) for e in examples)
        receipt['target_tokens_one_pass']={str(k):sum(sum(s==k and l!=-100 for s,l in zip(e['segments'],e['labels'])) for e in examples) for k in (1,2)}
        model=AutoModelForCausalLM.from_pretrained(model_dir,local_files_only=True,trust_remote_code=False,
                           torch_dtype=torch.bfloat16,device_map={'':0})
        model=get_peft_model(model,LoraConfig(r=16,lora_alpha=32,lora_dropout=0.,target_modules='all-linear',task_type='CAUSAL_LM'))
        model.config.use_cache=False;model.gradient_checkpointing_enable();model.enable_input_require_grads();model.train()
        optimizer=torch.optim.AdamW((p for p in model.parameters() if p.requires_grad),lr=1e-4)
        order=list(range(len(examples)))
        import random
        random.Random(seed).shuffle(order)
        for i in range(steps):
            if time.monotonic()-start>=seconds:status='TIME_CAP';break
            e=examples[order[i%len(order)]]
            ids=torch.tensor([e['input_ids']],device=model.device)
            labels=torch.tensor([e['labels']],device=model.device)
            segments=torch.tensor([e['segments']],device=model.device)
            optimizer.zero_grad(set_to_none=True)
            loss=segmented_loss(model(input_ids=ids,attention_mask=torch.ones_like(ids)).logits,
                                labels,segments,e['rationale_weight'],e['action_weight'])
            if not torch.isfinite(loss):raise FloatingPointError('nonfinite loss')
            loss.backward();norm=torch.nn.utils.clip_grad_norm_(model.parameters(),1.0)
            if not torch.isfinite(norm):raise FloatingPointError('nonfinite gradient')
            optimizer.step();logs.append({'step':i+1,'loss':float(loss.detach().cpu()),'tokens':len(e['input_ids'])})
            if (i+1) in {max(1,steps//4),max(1,steps//2),steps}:model.save_pretrained(out/f'checkpoint-{i+1}',safe_serialization=True)
        else:status='COMPLETE'
        model.save_pretrained(out/'adapter',safe_serialization=True);tok.save_pretrained(out/'adapter')
    except Exception as exc:
        receipt['error']=repr(exc);raise
    finally:
        receipt.update(status=status,steps_completed=len(logs),losses=logs,
            elapsed_seconds=time.monotonic()-start,peak_cuda_bytes=torch.cuda.max_memory_allocated())
        write_json(out/'run.json',receipt)
    return receipt


class HFActor:
    """Single base load; named retained adapters and greedy native-template actions."""
    def __init__(self, model_dir,revision,adapters,approved=False):
        self.base=HFTeacher(model_dir,revision,approved,max_new_tokens=48,per_call_seconds=30)
        from peft import PeftModel
        if set(adapters)!={'S1','O1'}:raise ValueError('paired S1/O1 adapters required')
        for path in adapters.values():
            if not Path(path).is_dir():raise FileNotFoundError(path)
        model=PeftModel.from_pretrained(self.base.model,adapters['S1'],adapter_name='S1',
                                       local_files_only=True,is_trainable=False)
        model.load_adapter(adapters['O1'],adapter_name='O1',local_files_only=True,is_trainable=False)
        model.eval();self.model=model
        self.adapter_sha256={arm:{p.name:file_sha(p) for p in Path(path).glob('*') if p.is_file()}
                             for arm,path in adapters.items()}
    def describe(self):
        return {'base':self.base.identity,'adapters':self.adapter_sha256,
                'native_chat_template':True,'temperature':0,'max_new_tokens':48,
                'weights_loaded':True,'evidence_class':'MODEL_INFERENCE'}
    def __call__(self,arm,messages):
        import torch
        from transformers import StoppingCriteriaList,MaxTimeCriteria
        from .core import parse_action
        self.model.set_adapter(arm);tok=self.base.tok
        prompt=tok.apply_chat_template(messages,tokenize=False,add_generation_prompt=True,enable_thinking=False)
        inp=tok(prompt,return_tensors='pt',add_special_tokens=False)
        width=inp.input_ids.shape[1]
        if width+48>4096:raise RuntimeError('actor context limit; no truncation')
        inp={k:v.to(self.model.device) for k,v in inp.items()}
        class Parsed:
            def __call__(self,ids,scores,**kwargs):
                try:parse_action(tok.decode(ids[0,width:],skip_special_tokens=True));return True
                except (ValueError,TypeError):return False
        started=time.monotonic()
        with torch.inference_mode():
            ids=self.model.generate(**inp,do_sample=False,max_new_tokens=48,pad_token_id=tok.pad_token_id,
                                    stopping_criteria=StoppingCriteriaList([Parsed(),MaxTimeCriteria(30)]))
        rawids=ids[0,width:].tolist();text=tok.decode(rawids,skip_special_tokens=True)
        if time.monotonic()-started>=30:
            try:parse_action(text)
            except (ValueError,TypeError):raise TimeoutError('actor generation time limit')
        return {'text':text,'raw_generated_token_ids':rawids,'prompt_tokens':width,
                'output_tokens':len(rawids),'adapter':arm,'seconds':time.monotonic()-started}
