"""Pinned bounded-generation protocols and stop-reason classification.

The unbounded base-model run spent most of its time on verbose output while the
adapters answered in a few tokens. A protocol here fixes the thinking mode, the
reasoning budget, the answer budget and the stop token IDs before any call, and
records why each generation ended. Nothing imports Torch or Transformers, so
the control flow is testable on CPU with a scripted ``generate`` callable and a
real or stand-in tokenizer.

Stop reasons:
  eos_im_end / eos_endoftext  the model ended its own turn on a verified token
  think_closed                reasoning closed itself with </think> inside budget
  length_in_reasoning         budget reached with reasoning still open
  length_in_final             answer budget reached before the model ended its turn
"""
from __future__ import annotations
from .cases import canon, digest

FORCED_CLOSE_TEXT = ('\n\nConsidering the limited time, I have to give the solution '
                     'based on the thinking directly now.\n</think>\n\n')

PROTOCOLS = {
    # Thinking disabled: the chat template pre-closes the reasoning block, the
    # answer budget is the only budget. A verbose model fails by length, visibly.
    'direct_v1': {'thinking': False, 'reasoning_budget': 0, 'answer_budget': 64},
    # Thinking enabled with a hard reasoning budget. Reasoning that is still open
    # at the budget is closed with a fixed sentence and the model then has
    # answer_budget tokens to emit the JSON. Such records are flagged.
    'bounded_think_v1': {'thinking': True, 'reasoning_budget': 768, 'answer_budget': 64},
}


def protocol(name):
    if name not in PROTOCOLS:raise ValueError('unknown generation protocol')
    body={'name':name,**PROTOCOLS[name]}
    if body['thinking']:body['forced_close_text']=FORCED_CLOSE_TEXT
    body['sha256']=digest(body)
    return body


def terminal_map(tokenizer):
    """Verified {token_id: marker string} for turn-ending tokens plus </think>.

    Every entry is checked in both directions: the string maps to the ID and the
    single ID decodes back to the same string. A name that maps to the unknown
    token, or does not round-trip, fails closed.
    """
    out={}
    for name in ('<|im_end|>','<|endoftext|>','</think>'):
        token_id=tokenizer.convert_tokens_to_ids(name)
        unk=getattr(tokenizer,'unk_token_id',None)
        if type(token_id) is not int or token_id<0 or token_id==unk:
            raise ValueError('tokenizer lacks '+name)
        if tokenizer.decode([token_id],skip_special_tokens=False)!=name:
            raise ValueError('token does not round-trip: '+name)
        out[token_id]=name
    return out


def stop_ids(tmap):
    return {'turn':sorted(i for i,n in tmap.items() if n!='</think>'),
            'think_end':next(i for i,n in tmap.items() if n=='</think>')}


def classify(ids, tmap, *, phase_budget, hit_budget_in):
    """Name how one phase ended from its last generated token.

    </think> only ends the reasoning phase; in the answer phase it is ordinary text.
    """
    if ids and ids[-1] in tmap and (hit_budget_in=='reasoning' or tmap[ids[-1]]!='</think>'):
        return {'<|im_end|>':'eos_im_end','<|endoftext|>':'eos_endoftext','</think>':'think_closed'}[tmap[ids[-1]]]
    if len(ids)>=phase_budget:
        return 'length_in_'+hit_budget_in
    # The generator returned early without a verified terminal token.
    raise ValueError('generation stopped without a verified terminal token or the budget')


def bounded_generate(generate, tokenizer, prompt_ids, name, tmap):
    """Run one protocol. ``generate(ids, max_new_tokens, stop_token_ids)`` returns new IDs only.

    Returns every generated and forced ID, the final-answer IDs, the stop reason,
    and per-phase accounting. Forced IDs are listed separately so no inserted text
    is ever attributed to the model.
    """
    proto=protocol(name)
    stops=stop_ids(tmap)
    turn=stops['turn']
    prompt_ids=list(prompt_ids)
    phases=[];generated=[];forced=[]
    if not proto['thinking']:
        new=list(generate(prompt_ids,proto['answer_budget'],turn))
        reason=classify(new,tmap,phase_budget=proto['answer_budget'],hit_budget_in='final')
        phases.append({'phase':'answer','tokens':len(new),'stop':reason})
        generated+=new
        final=new;forced_close=False
    else:
        budget=proto['reasoning_budget']
        new=list(generate(prompt_ids,budget,turn+[stops['think_end']]))
        reason=classify(new,tmap,phase_budget=budget,hit_budget_in='reasoning')
        phases.append({'phase':'reasoning','tokens':len(new),'stop':reason})
        generated+=new
        forced_close=False
        if reason in ('eos_im_end','eos_endoftext'):
            final=new   # ended its turn without a separate answer phase
        else:
            context=prompt_ids+new
            if reason=='length_in_reasoning':
                forced=list(tokenizer.encode(FORCED_CLOSE_TEXT,add_special_tokens=False))
                if stops['think_end'] not in forced:raise ValueError('forced close must contain </think>')
                context+=forced;forced_close=True
            ans=list(generate(context,proto['answer_budget'],turn))
            end=classify(ans,tmap,phase_budget=proto['answer_budget'],hit_budget_in='final')
            phases.append({'phase':'answer','tokens':len(ans),'stop':end})
            generated+=ans;final=ans;reason=end
    return {'protocol':proto['name'],'protocol_sha256':proto['sha256'],
            'generated_token_ids':generated,'forced_token_ids':forced,'final_token_ids':final,
            'stop_reason':reason,'reasoning_force_closed':forced_close,'phases':phases,
            'total_model_tokens':len(generated),'total_forced_tokens':len(forced)}


def stitched_ids(result):
    """Audit order: model reasoning, inserted closer, model answer."""
    first=result['phases'][0]['tokens']
    ids=result['generated_token_ids']
    return ids[:first]+result['forced_token_ids']+ids[first:]


def hf_generate(model, torch, device):
    """Bind a Transformers model to the ``generate`` callable used above."""
    def call(ids, max_new_tokens, stop_token_ids):
        tensor=torch.tensor([ids],device=device)
        with torch.inference_mode():
            out=model.generate(input_ids=tensor,attention_mask=torch.ones_like(tensor),
                               max_new_tokens=max_new_tokens,do_sample=False,
                               eos_token_id=list(stop_token_ids),pad_token_id=stop_token_ids[0])
        return out[0,len(ids):].detach().cpu().tolist()
    return call


def budget_estimate(protocol_name, arms_calls, tokens_per_second, prompt_tokens=700, load_minutes=10):
    """Wall-clock bounds from stated throughput assumptions; not a measurement."""
    p=protocol(protocol_name)
    worst=p['reasoning_budget']+p['answer_budget']+(len(FORCED_CLOSE_TEXT)//3 if p['thinking'] else 0)
    best=24
    calls=sum(arms_calls.values())
    return {'protocol':p['name'],'calls':calls,'worst_case_generated_tokens_per_call':worst,
            'worst_case_generated_tokens':calls*worst,
            'tokens_per_second_assumed':tokens_per_second,
            'worst_case_generation_minutes':round(calls*worst/tokens_per_second/60,1),
            'concise_arm_generation_minutes':round(calls*best/tokens_per_second/60,1),
            'model_load_minutes_assumed':load_minutes,'prompt_tokens_assumed':prompt_tokens,
            'measured':False}
