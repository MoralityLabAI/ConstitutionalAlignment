"""Resumable, strictly budgeted inference adapters; CPU offline by default."""
from __future__ import annotations
import json
import os
from pathlib import Path
import hashlib
import time
from urllib import request, error, parse as urlparse
from .cases import canon, scripted
from .plan import assignments, spread_assignments, verify_plan
from .score import record_for, score


def extract_final(text):
    """Score only a model's final channel, retaining the full output separately.

    A dangling <think> segment is malformed. Reasoning text alone can never be
    promoted to an answer or used as semantic proof evidence.
    """
    if not isinstance(text, str):raise TypeError('generated text required')
    if '</think>' in text:
        return text.rsplit('</think>', 1)[-1].strip()
    return text.strip()


def decode_hf_final(tokenizer, generated_ids):
    """Decode strict final content, excluding only terminal model EOS tokens.

    Preserve the verbatim rendering and token IDs for audit. Only identified
    terminal EOS/end-of-message markers may be removed. An internal marker,
    an unfinished reasoning block, or trailing explanatory prose remains
    visible to the strict JSON parser.
    """
    ids = generated_ids.tolist() if hasattr(generated_ids, 'tolist') else list(generated_ids)
    if not all(type(token) is int for token in ids):
        raise TypeError('generated token ids must be integers')
    full = tokenizer.decode(ids, skip_special_tokens=False)
    terminal = {tokenizer.eos_token_id} if type(getattr(tokenizer, 'eos_token_id', None)) is int else set()
    if hasattr(tokenizer, 'convert_tokens_to_ids'):
        for name in ('<|im_end|>', '<|endoftext|>'):
            value = tokenizer.convert_tokens_to_ids(name)
            if type(value) is int and value >= 0 and value != getattr(tokenizer, 'unk_token_id', None):
                terminal.add(value)
    ending=[]
    while ids and ids[-1] in terminal:
        ending.append(ids.pop())
    cleaned = tokenizer.decode(ids, skip_special_tokens=False)
    return extract_final(cleaned), full, list(reversed(ending))


def sha_file(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def adapter_files(path):
    p=Path(path)
    if not p.is_dir() or p.is_symlink():raise ValueError('adapter directory must be mounted before allocation')
    files={name:sha_file(p/name) for name in ('adapter_config.json','adapter_model.safetensors')
           if (p/name).is_file() and not (p/name).is_symlink()}
    if set(files)!= {'adapter_config.json','adapter_model.safetensors'}:raise ValueError('adapter files missing or symlinked')
    return files


def write_json(path, value):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_name(p.name+'.tmp');tmp.write_text(json.dumps(value,sort_keys=True,indent=2,ensure_ascii=False)+'\n',encoding='utf-8');tmp.replace(p)


def read_records(path):
    p=Path(path)
    if not p.is_file():return []
    rows=[]
    for line in p.read_text(encoding='utf-8').splitlines():
        if line.strip():rows.append(json.loads(line))
    return rows


def _check_resumption(path, plan, arm):
    previous=read_records(path)
    wanted={a['assignment_id']:a for a in assignments(plan,[arm])}
    seen=set()
    for r in previous:
        aid=r.get('assignment_id')
        if aid in seen or aid not in wanted or r.get('plan_sha256')!=plan['sha256']:
            raise ValueError('prior run has duplicate or incorrect assignment; use fresh output')
        seen.add(aid)
        for field in ('prompt','case_sha256','arm'):
            if r.get(field)!=wanted[aid][field]:raise ValueError('incompatible prior run: '+field)
    return seen


def run_fixture(plan, out, arm='platonic_grounding', policy='oracle'):
    verify_plan(plan);out=Path(out)
    seen=_check_resumption(out,plan,arm)
    case_by_id={c['case_id']:c for b in plan['blocks'] for c in b['cells']}
    with out.open('a',encoding='utf-8') as f:
        for a in assignments(plan,[arm]):
            if a['assignment_id'] in seen:continue
            try:raw=scripted(case_by_id[a['case_id']],policy);exc=None
            except TimeoutError as e:raw=None;exc=str(e)
            r=record_for(plan,a,raw,error=exc,model_id='synthetic:'+policy)
            f.write(canon(r)+'\n');f.flush()
    return score(plan,read_records(out),[arm])


def _safe_endpoint(url):
    u=urlparse.urlparse(url)
    if u.scheme=='https' and u.hostname and u.username is None and u.password is None:return url.rstrip('/')
    if u.scheme=='http' and u.hostname in ('localhost','127.0.0.1','::1'):return url.rstrip('/')
    raise ValueError('HTTPS endpoint required, except loopback-only local vLLM')


def _chat(url,key,model,prompt,max_output_tokens,timeout,reasoning_effort=None):
    body={'model':model,'messages':[{'role':'system','content':'Answer with the final strict JSON contract. Reason carefully about the case.'},
                                    {'role':'user','content':prompt}],
          'temperature':0,'max_tokens':max_output_tokens,'stream':False}
    if reasoning_effort is not None:body['reasoning_effort']=reasoning_effort
    payload=canon(body).encode('utf-8')
    req=request.Request(url,data=payload,headers={'Content-Type':'application/json','Authorization':'Bearer '+key},method='POST')
    with request.urlopen(req,timeout=timeout) as resp:
        out=json.load(resp)
    if not isinstance(out,dict) or not isinstance(out.get('choices'),list) or len(out['choices'])!=1:raise ValueError('invalid provider response schema')
    msg=out['choices'][0].get('message') or {}
    content=msg.get('content')
    if isinstance(content,list):content=''.join(p.get('text','') for p in content if p.get('type')=='text')
    if not isinstance(content,str):content=''
    raw_content=content
    content=extract_final(content)
    usage=out.get('usage') or {}
    safe_usage={k:usage.get(k) for k in ('prompt_tokens','completion_tokens','total_tokens') if isinstance(usage.get(k),int)}
    finish=out['choices'][0].get('finish_reason')
    # No private reasoning text is exported as proof evidence. Store counts only.
    return content,{'usage':safe_usage,'finish_reason':finish,'provider_response_id':out.get('id'),
                    'raw_assistant_content':raw_content,
                    'raw_reasoning_content':msg.get('reasoning_content') if isinstance(msg.get('reasoning_content'),str) else None,
                    'reasoning_tokens':(usage.get('completion_tokens_details') or {}).get('reasoning_tokens')}


def run_endpoint(plan, out, arm, *, model_id, base_url, approval, max_requests, total_output_cap,
                 output_tokens_per_request=2048, per_request_timeout=120, reasoning_effort=None,
                 api_key_env='BENCH_API_KEY'):
    verify_plan(plan)
    if not approval:raise PermissionError('external inference requires explicit --approved')
    if not model_id or arm not in plan['arms']:raise ValueError('registered arm/model id required')
    if any(type(v) is not int or v<=0 for v in (max_requests,total_output_cap,output_tokens_per_request,per_request_timeout)):
        raise ValueError('positive hard request/token/time caps required')
    if output_tokens_per_request>total_output_cap:raise ValueError('per-response cap exceeds total budget')
    if reasoning_effort not in (None,'low','medium','high'):raise ValueError('unsupported reasoning effort')
    url=_safe_endpoint(base_url)
    if not url.endswith('/chat/completions'):raise ValueError('use full OpenAI-compatible chat/completions URL')
    key=os.environ.get(api_key_env)
    if not key:raise ValueError('missing credential environment variable; never persist keys')
    out=Path(out);out.parent.mkdir(parents=True,exist_ok=True)
    if out.exists() and out.stat().st_size:raise ValueError('external endpoint runs require a fresh output file to avoid ambiguous billing')
    target=list(spread_assignments(plan,[arm]))
    if max_requests>len(target):raise ValueError('request cap exceeds assigned plan; select a smaller value')
    max_possible=min(max_requests,total_output_cap//output_tokens_per_request)
    if max_possible<1:raise ValueError('budget insufficient for one assigned response')
    issued=0;usage_total=0
    with out.open('x',encoding='utf-8') as f:
        for a in target[:max_possible]:
            issued+=1
            start=time.monotonic()
            try:
                raw,metadata=_chat(url,key,model_id,a['prompt'],output_tokens_per_request,per_request_timeout,reasoning_effort)
                usage_total+=metadata['usage'].get('completion_tokens',output_tokens_per_request)
                err=None
            except (TimeoutError,error.URLError,ValueError,OSError) as exc:
                raw=None;metadata={};err=type(exc).__name__+': '+str(exc)
            r=record_for(plan,a,raw,error=err,metadata={**metadata,'latency_seconds':round(time.monotonic()-start,3)},model_id=model_id)
            f.write(canon(r)+'\n');f.flush()
            if err:break   # fail closed on transport/provider failure, no automatic retry
            if usage_total>=total_output_cap:break
    report=score(plan,read_records(out),[arm]);report['provider_requests_sent']=issued
    report['observed_provider_completion_tokens']=usage_total
    report['provider_model_id']=model_id
    report['provider_endpoint_origin']=urlparse.urlparse(url).scheme+'://'+urlparse.urlparse(url).netloc
    return report


def _prepare_generation_inputs(tokenized, device):
    """Normalize either tensor or BatchEncoding before Transformers.generate.

    Recent Transformers chat tokenizers default to a BatchEncoding when
    return_dict=True. Passing that object positionally to generate() breaks
    generation, which expects a tensor or named input_ids/attention_mask.
    Keep the attention mask and validate one nonempty, unpadded chat prompt.
    This helper imports neither Torch nor Transformers, so CPU tests can
    exercise the exact interface with lightweight stand-ins.
    """
    if hasattr(tokenized, 'items'):
        if not hasattr(tokenized, '__getitem__'):
            raise TypeError('tokenizer mapping cannot be indexed')
        inputs = dict(tokenized.items())
        if not set(inputs).issubset({'input_ids', 'attention_mask'}):
            raise ValueError('unexpected text-only chat tokenizer fields')
    elif hasattr(tokenized, 'shape') and hasattr(tokenized, 'to'):
        inputs = {'input_ids': tokenized}
    else:
        raise TypeError('chat tokenizer must return a tensor or mapping of tensors')
    if 'input_ids' not in inputs:
        raise ValueError('missing input_ids in chat tokenizer output')
    result = {}
    for name, value in inputs.items():
        if not hasattr(value, 'to') or not hasattr(value, 'shape'):
            raise TypeError('chat tokenizer %s must be a tensor' % name)
        moved = value.to(device)
        if not hasattr(moved, 'shape'):
            raise TypeError('moved chat tokenizer %s must be a tensor' % name)
        result[name] = moved
    ids = result['input_ids']
    if len(ids.shape) != 2 or ids.shape[0] != 1 or ids.shape[1] < 1:
        raise ValueError('expected one nonempty batched chat prompt')
    if 'attention_mask' in result and result['attention_mask'].shape != ids.shape:
        raise ValueError('chat attention_mask shape mismatch')
    return result, int(ids.shape[1])


def preflight_hf_tokenizer(plan, *, base_model, model_revision, out, thinking=False):
    """Check the actual locally retained chat tokenizer without loading model weights.

    This gate exercises the BatchEncoding path that caused the earlier crash.
    It validates a real assigned prompt, named tensor inputs and a nonempty
    sequence before a provider can allocate an inference GPU.
    """
    verify_plan(plan)
    if len(model_revision)!=40 or any(c not in '0123456789abcdef' for c in model_revision):
        raise ValueError('40-hex revision required')
    out=Path(out)
    if out.exists():raise FileExistsError('fresh tokenizer preflight receipt required')
    from transformers import AutoTokenizer
    tokenizer=AutoTokenizer.from_pretrained(base_model,local_files_only=True,use_fast=True)
    if not tokenizer.is_fast or not tokenizer.chat_template:
        raise ValueError('native chat tokenizer required')
    sample=next(iter(spread_assignments(plan,['base','formal_control','platonic_grounding'])))
    messages=[{'role':'system','content':'Provide a final JSON answer using the case menu IDs.'},
              {'role':'user','content':sample['prompt']}]
    encoded=tokenizer.apply_chat_template(messages,add_generation_prompt=True,
              tokenize=True,return_dict=True,return_tensors='pt',enable_thinking=thinking)
    inputs,prompt_length=_prepare_generation_inputs(encoded,'cpu')
    template=tokenizer.chat_template
    if not isinstance(template,(str,dict)):
        raise ValueError('unexpected chat template type')
    receipt={'status':'TOKENIZER_ONLY_PRE_GPU_PASS','model_revision_claim':model_revision,
             'model_weights_loaded':False,'GPU_allocated':False,
             'sample_assignment_id':sample['assignment_id'],
             'plan_sha256':plan['sha256'],'thinking_enabled':bool(thinking),
             'tokenizer_output_type':type(encoded).__name__,
             'input_tensor_names':sorted(inputs),'prompt_tokens':prompt_length,
             'chat_template_sha256':hashlib.sha256(canon(template).encode('utf-8')).hexdigest()}
    write_json(out,receipt)
    return receipt


def run_hf(plan,out,*,arm,base_model,model_revision,adapter_path=None,approval=False,max_requests=64,
           max_new_tokens=2048,thinking=True):
    """Existing Qwen base or saved PEFT adapter on a managed GPU worker.

    Loads no weights during package import or CPU tests. A provider lease
    needs a separately enforced hard cap. The model revision is an assertion;
    the worker must independently check retained checkpoint metadata.
    """
    verify_plan(plan)
    if not approval:raise PermissionError('GPU inference must be explicitly approved')
    if arm not in ('base','formal_control','platonic_grounding'):raise ValueError('local arm')
    if (arm=='base') != (adapter_path is None):raise ValueError('adapter required for trained arm; forbidden for unchanged base')
    if not model_revision or len(model_revision)!=40 or any(c not in '0123456789abcdef' for c in model_revision):raise ValueError('pinned model revision must be 40-hex')
    if not 1<=max_requests<=len(list(assignments(plan,[arm]))) or not 1<=max_new_tokens<=8192:raise ValueError('resource cap')
    out=Path(out);out.parent.mkdir(parents=True,exist_ok=True)
    if out.exists() and out.stat().st_size:raise ValueError('fresh destination required')
    from transformers import AutoModelForCausalLM,AutoTokenizer
    import torch
    from contextlib import nullcontext
    tokenizer=AutoTokenizer.from_pretrained(base_model,local_files_only=True,use_fast=True)
    if not tokenizer.is_fast or tokenizer.chat_template is None:raise ValueError('native chat tokenizer required')
    model=AutoModelForCausalLM.from_pretrained(base_model,local_files_only=True,torch_dtype=torch.bfloat16,device_map='auto')
    if arm!='base':
        from peft import PeftModel
        model=PeftModel.from_pretrained(model,adapter_path,is_trainable=False,local_files_only=True)
    model.eval()
    with out.open('x',encoding='utf-8') as f:
        for a in list(spread_assignments(plan,[arm]))[:max_requests]:
            err=None;raw=None;meta={}
            try:
                chat=[{'role':'system','content':'Give a final answer in strict JSON.'},{'role':'user','content':a['prompt']}]
                encoded=tokenizer.apply_chat_template(chat,add_generation_prompt=True,tokenize=True,
                      return_dict=True,return_tensors='pt',enable_thinking=thinking)
                model_inputs,prompt_length=_prepare_generation_inputs(encoded,model.device)
                with torch.inference_mode():
                    res=model.generate(**model_inputs,max_new_tokens=max_new_tokens,do_sample=False,
                                       pad_token_id=tokenizer.eos_token_id)
                tokens=res[0,prompt_length:]
                raw,generated_text,stripped_terminal_tokens=decode_hf_final(tokenizer,tokens)
                meta={'raw_model_text':generated_text,'stripped_terminal_token_ids':stripped_terminal_tokens,'input_tokens':prompt_length,'generated_tokens':int(len(tokens)),
                      'raw_generated_token_ids':tokens.detach().cpu().tolist()}
            except (RuntimeError,ValueError,OSError,TypeError,AttributeError) as exc:
                err=type(exc).__name__+': '+str(exc)
            f.write(canon(record_for(plan,a,raw,error=err,metadata=meta,model_id=model_revision+':'+arm))+'\n');f.flush()
            if err:break
    return score(plan,read_records(out),[arm])


def run_hf_group(plan,out,*,base_model,model_revision,formal_adapter,platonic_adapter,
                 approval=False,max_assignments=192,max_new_tokens=1024,max_wall_seconds=900,
                 thinking=False):
    """Evaluate three Qwen arms with one weight load and two mounted adapters.

    The inference lease/provider cap must be enforced outside this worker too.
    Every assigned record beyond the cap remains unknown during scoring.
    """
    verify_plan(plan)
    if not approval:raise PermissionError('explicit model-inference approval required')
    if len(model_revision)!=40 or any(c not in '0123456789abcdef' for c in model_revision):raise ValueError('40-hex revision required')
    if type(max_assignments) is not int or not 1<=max_assignments<=len(list(assignments(plan,['base','formal_control','platonic_grounding']))):raise ValueError('max_assignments')
    if not 1<=max_new_tokens<=8192 or not 1<=max_wall_seconds<=7200:raise ValueError('budgets')
    attest={'formal_control':adapter_files(formal_adapter),'platonic_grounding':adapter_files(platonic_adapter)}
    out=Path(out);out.parent.mkdir(parents=True,exist_ok=True)
    if out.exists():raise FileExistsError('fresh durable output required')
    from transformers import AutoTokenizer,AutoModelForCausalLM
    from peft import PeftModel
    from contextlib import nullcontext
    import torch
    start=time.monotonic()
    tokenizer=AutoTokenizer.from_pretrained(base_model,local_files_only=True,use_fast=True)
    if not tokenizer.is_fast or not tokenizer.chat_template:raise ValueError('native template required')
    m=AutoModelForCausalLM.from_pretrained(base_model,local_files_only=True,torch_dtype=torch.bfloat16,device_map='auto')
    model=PeftModel.from_pretrained(m,formal_adapter,adapter_name='formal_control',is_trainable=False,local_files_only=True)
    model.load_adapter(platonic_adapter,adapter_name='platonic_grounding',is_trainable=False)
    model.eval()
    with out.open('x',encoding='utf-8') as f:
        for a in list(spread_assignments(plan,['base','formal_control','platonic_grounding']))[:max_assignments]:
            if time.monotonic()-start>=max_wall_seconds:break
            raw=None;err=None;metadata={'checkpoint_safetensors_sha256':attest}
            try:
                messages=[{'role':'system','content':'Provide a final JSON answer using the case menu IDs.'},
                          {'role':'user','content':a['prompt']}]
                encoded=tokenizer.apply_chat_template(messages,add_generation_prompt=True,
                         tokenize=True,return_dict=True,return_tensors='pt',enable_thinking=thinking)
                model_inputs,prompt_length=_prepare_generation_inputs(encoded,model.device)
                if a['arm']=='base':
                    ctx=model.disable_adapter()
                else:
                    model.set_adapter(a['arm']);ctx=nullcontext()
                with ctx,torch.inference_mode():
                    generated=model.generate(**model_inputs,max_new_tokens=max_new_tokens,do_sample=False,
                                             pad_token_id=tokenizer.eos_token_id)
                out_ids=generated[0,prompt_length:]
                raw,full,stripped_terminal_tokens=decode_hf_final(tokenizer,out_ids)
                metadata.update(raw_model_text=full,stripped_terminal_token_ids=stripped_terminal_tokens,input_tokens=prompt_length,
                                output_tokens=int(len(out_ids)),raw_generated_token_ids=out_ids.detach().cpu().tolist())
            except (RuntimeError,ValueError,OSError,TypeError,AttributeError) as exc:
                err=type(exc).__name__+': '+str(exc)
            row=record_for(plan,a,raw,error=err,metadata=metadata,model_id=model_revision+':'+a['arm'])
            f.write(canon(row)+'\n');f.flush()
            if err:break
    summary=score(plan,read_records(out),['base','formal_control','platonic_grounding'])
    summary['run_adapter_file_sha256']=attest
    summary['reported_model_revision']=model_revision
    summary['GPU_peak_allocated_bytes']=int(torch.cuda.max_memory_allocated()) if torch.cuda.is_available() else None
    summary['elapsed_seconds']=time.monotonic()-start
    return summary
