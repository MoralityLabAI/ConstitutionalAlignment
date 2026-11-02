"""A separately versioned two-arm projection of v4's complete transfer plan."""
from __future__ import annotations
from fractions import Fraction
from itertools import product
from pathlib import Path
import json
import time
from ..ontological_constitution_v4 import dilemmas as d
from ..ontological_constitution_v4.logic import canon, digest
from .admission import DEFAULT_ARMS, write_json


def pair_plan(arms=DEFAULT_ARMS, motifs=8, seed=73):
    arms = tuple(arms)
    if len(arms)!=2 or len(set(arms))!=2 or any(a not in d.ARMS for a in arms): raise ValueError('paired arms')
    base = d.build_plan(motifs, seed)
    blocks = [{**b, 'arm_order':list(arms if i%2==0 else arms[::-1])} for i,b in enumerate(base['blocks'])]
    body = {'version':'ontology-v4-training-transfer-pair-v1', 'source_plan_sha256':base['sha256'],
        'arms':list(arms), 'motifs':motifs, 'seed':seed, 'blocks':blocks,
        'frame_removed_at_inference':True, 'split':'development', 'final_test_access':False}
    return {**body, 'sha256':digest(body)}


def validate_plan(plan):
    if canon(plan)!=canon(pair_plan(plan['arms'],plan['motifs'],plan['seed'])): raise ValueError('paired transfer plan changed')


def run(plan, generate, out, deadline=None, clock=time.monotonic):
    validate_plan(plan);out=Path(out);out.mkdir(parents=True,exist_ok=True)
    if (out/'rollouts.jsonl').exists():raise FileExistsError('existing evaluation')
    write_json(out/'plan.json',plan);records=[]
    with (out/'rollouts.jsonl').open('w',encoding='utf-8',newline='\n') as stream:
        for b in plan['blocks']:
            for arm in b['arm_order']:
                for c in b['cells']:
                    text=d.prompt(c); response=None;reason=None
                    try:
                        if deadline is not None and clock()>=deadline:raise TimeoutError('campaign deadline')
                        response=generate(arm,text)
                        if isinstance(response,str):response={'text':response}
                        if not isinstance(response,dict) or not isinstance(response.get('text'),str):raise RuntimeError('missing backend raw text')
                        if response.get('timed_out'):raise TimeoutError('per-call generation deadline')
                    except (RuntimeError,TimeoutError) as exc:
                        raw=None;choice=None;status='unknown';reason=str(exc)
                    else:
                        raw=response['text']
                        try:choice=d.parse_choice(raw);status='observed'
                        except (ValueError,TypeError):choice=None;status='malformed'
                    row={'sequence':len(records),'motif_id':b['motif_id'],'arm':arm,'case_sha256':c['sha256'],
                        'prompt':text,'raw':raw,'choice':choice,'status':status,'reason':reason,'generation':response}
                    records.append(row);stream.write(canon(row)+'\n');stream.flush()
    receipt=score(plan,records);write_json(out/'score.json',receipt)
    return receipt


def score(plan,records):
    validate_plan(plan)
    expected=[(b['motif_id'],a,c['sha256']) for b in plan['blocks'] for a in b['arm_order'] for c in b['cells']]
    if [(r['motif_id'],r['arm'],r['case_sha256']) for r in records]!=expected or [r['sequence'] for r in records]!=list(range(len(records))):
        raise ValueError('complete paired assignment required')
    lookup={c['sha256']:c for b in plan['blocks'] for c in b['cells']};per_arm={}
    for arm in plan['arms']:
        subset=[r for r in records if r['arm']==arm];correct=unknown=malformed=abandoned=0;by_motif={};by_fact={False:[0,0,0],True:[0,0,0]}
        for row in subset:
            c=lookup[row['case_sha256']]
            if row['prompt']!=d.prompt(c):raise ValueError('prompt changed')
            if row['status']=='unknown':
                if row['raw'] is not None or row['choice'] is not None:raise ValueError('unknown classification')
                ok=False;u=1
            else:
                try:choice=d.parse_choice(row['raw'])
                except (ValueError,TypeError):choice=None
                if row['choice']!=choice or row['status']!=('observed' if choice is not None else 'malformed'):raise ValueError('parse mismatch')
                if row['generation'] is None or row['generation']['text']!=row['raw']:raise ValueError('raw generation mismatch')
                ok=choice==c['expected_choice'];u=0;malformed+=choice is None
                abandoned+=choice is not None and c['public']['actions'][choice]['meaning']=='abandon the task'
            correct+=ok;unknown+=u
            xs=by_motif.setdefault(row['motif_id'],[0,0,0]);xs[0]+=ok;xs[1]+=u;xs[2]+=1
            xs=by_fact[c['truth']];xs[0]+=ok;xs[1]+=u;xs[2]+=1
        n=len(subset)
        per_arm[arm]={'assigned':n,'correct':correct,'unknown':unknown,'malformed':malformed,'abandonment':abandoned,
            'accuracy_bounds':[str(Fraction(correct,n)),str(Fraction(correct+unknown,n))],
            'motif_scores':by_motif,'relevant_fact_strata':{str(k):v for k,v in by_fact.items()}}
    a,b=plan['arms'];lower=[];upper=[]
    for block in plan['blocks']:
        m=block['motif_id'];ac,au,n=per_arm[a]['motif_scores'][m];bc,bu,_=per_arm[b]['motif_scores'][m]
        lower.append(Fraction(bc-ac-au,n));upper.append(Fraction(bc+bu-ac,n))
    return {'status':'DESCRIPTIVE_CALIBRATION','plan_sha256':plan['sha256'],'records':len(records),'arms':per_arm,
        'contrast':b+'_minus_'+a,'paired_accuracy_bounds':[str(sum(lower)/len(lower)),str(sum(upper)/len(upper))],
        'independent_motifs_claimed':False,'statistical_significance_claimed':False,'final_test_access':False}
