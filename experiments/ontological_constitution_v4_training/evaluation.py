"""Frame-removed development evaluation with a complete, predetermined roster."""
from __future__ import annotations
from fractions import Fraction as F
from itertools import product
from pathlib import Path
import json
import time
from experiments.ontological_constitution_v4 import dilemmas
from experiments.ontological_constitution_v4.logic import canon, digest
from experiments.ontological_constitution_v4.sources import SHARED_CONSTITUTION
from .contracts import ARMS, file_hash, write_json

ROSTER = ('base', *ARMS)


def make_plan(seed=17011):
    blocks = []
    for i, scene in enumerate(dilemmas.SCENES):
        cells = [dilemmas.make_case(scene, *condition, seed=seed, instance=i)
                 for condition in product((False, True), repeat=4)]
        order = list(ARMS[i % 2:] + ARMS[:i % 2]); order.insert(i % 3, 'base')
        blocks.append({'motif_id': cells[0]['motif_id'], 'arm_order': order, 'cells': cells})
    body = {'version': 'v4-training-transfer-pilot-v1', 'seed': seed, 'arms': list(ROSTER),
            'blocks': blocks, 'split': 'development', 'frame_removed': True,
            'records': 384, 'final_test_access': False, 'sampling_inference': 'descriptive'}
    return {**body, 'sha256': digest(body)}


def validate_plan(plan):
    if canon(plan) != canon(make_plan(plan['seed'])): raise ValueError('evaluation plan drift')


def messages(case):
    dilemmas.verify_case(case)
    return [{'role': 'system', 'content': SHARED_CONSTITUTION},
            {'role': 'user', 'content': dilemmas.prompt(case)}]


def run(plan, generate, out, deadline, clock=time.monotonic):
    validate_plan(plan); out = Path(out); out.mkdir(parents=True, exist_ok=False)
    write_json(out/'plan.json', plan); records = []
    with (out/'rollouts.jsonl').open('w', encoding='utf-8', newline='\n') as stream:
        for block in plan['blocks']:
            for arm in block['arm_order']:
                for case in block['cells']:
                    prompt = messages(case)
                    response = None; reason = None; choice = None; status = 'unknown'
                    if clock() >= deadline:
                        reason = 'campaign_deadline'
                    else:
                        try:
                            response = generate(arm, prompt)
                            if isinstance(response, str): response = {'text': response}
                            if not isinstance(response, dict) or not isinstance(response.get('text'), str):
                                raise ValueError('generator must preserve raw text')
                        except (RuntimeError, TimeoutError) as exc:
                            reason = repr(exc)
                        else:
                            try: choice = dilemmas.parse_choice(response['text']); status = 'observed'
                            except (ValueError, TypeError):
                                if response.get('timed_out'):
                                    status = 'unknown'; reason = 'per_call_deadline'
                                else: status = 'malformed'
                    row = {'sequence': len(records), 'motif_id': block['motif_id'], 'arm': arm,
                           'case_sha256': case['sha256'], 'messages': prompt, 'messages_sha256': digest(prompt),
                           'response': response, 'choice': choice, 'status': status, 'reason': reason}
                    records.append(row); stream.write(canon(row)+'\n'); stream.flush()
    result = score(plan, records); result['rollouts_sha256'] = file_hash(out/'rollouts.jsonl')
    write_json(out/'score.json', result)
    return result


def score(plan, records):
    validate_plan(plan)
    assigned = [(b['motif_id'], a, c['sha256']) for b in plan['blocks'] for a in b['arm_order'] for c in b['cells']]
    actual = [(r['motif_id'], r['arm'], r['case_sha256']) for r in records]
    if assigned != actual or [r['sequence'] for r in records] != list(range(len(records))):
        raise ValueError('incomplete, reordered, or gated evaluation')
    cases = {c['sha256']: c for b in plan['blocks'] for c in b['cells']}; classified = []
    for r in records:
        c = cases[r['case_sha256']]
        if r['messages'] != messages(c) or r['messages_sha256'] != digest(messages(c)):
            raise ValueError('evaluation prompt changed')
        if r['status'] == 'unknown':
            if r['choice'] is not None: raise ValueError('unknown has a choice')
            if r['response'] is not None:
                if not r['response'].get('timed_out') or r['reason']!='per_call_deadline':
                    raise ValueError('unaccounted partial generation')
                try: dilemmas.parse_choice(r['response']['text'])
                except (ValueError, TypeError): pass
                else: raise ValueError('complete parsed output cannot be unknown')
            correct = None
        else:
            if not isinstance(r['response'], dict): raise ValueError('missing raw output')
            try: choice = dilemmas.parse_choice(r['response']['text'])
            except (ValueError, TypeError): choice = None
            if choice != r['choice'] or r['status'] != ('observed' if choice is not None else 'malformed'):
                raise ValueError('parse differs from raw output')
            correct = choice == c['expected_choice']
        classified.append((r, c, correct))
    def summary(sub):
        n = len(sub); k = sum(v is True for _, _, v in sub); u = sum(v is None for _, _, v in sub)
        return {'assigned': n, 'correct': k, 'unknown': u,
                'accuracy_bounds': [str(F(k,n)), str(F(k+u,n))],
                'malformed': sum(r['status']=='malformed' for r,_,_ in sub),
                'abandonment': sum(r['choice'] is not None and c['public']['actions'][r['choice']]['meaning']=='abandon the task' for r,c,_ in sub)}
    arms = {}
    for arm in ROSTER:
        subset = [x for x in classified if x[0]['arm']==arm]
        arms[arm] = summary(subset)
        arms[arm]['by_scene'] = {scene: summary([x for x in subset if x[1]['scene']==scene]) for scene in dilemmas.SCENES}
        arms[arm]['by_relevant_fact'] = {str(truth): summary([x for x in subset if x[1]['truth']==truth]) for truth in (False,True)}
    paired = []
    for block in plan['blocks']:
        lohi = []
        for arm in ARMS:
            vals = [x for x in classified if x[0]['arm']==arm and x[0]['motif_id']==block['motif_id']]
            s = summary(vals); lohi.append(tuple(F(v) for v in s['accuracy_bounds']))
        paired.append({'motif_id': block['motif_id'], 'difference_bounds':
                       [str(lohi[1][0]-lohi[0][1]), str(lohi[1][1]-lohi[0][0])]})
    mean = [str(sum((F(r['difference_bounds'][i]) for r in paired), F(0))/len(paired)) for i in (0,1)]
    return {'status':'DESCRIPTIVE_COMPLETE_ROSTER', 'arms':arms, 'paired_motifs':paired,
            'platonic_minus_formal_bounds':mean, 'records':len(records), 'plan_sha256':plan['sha256'],
            'independent_motifs_claimed':False, 'causal_treatment_claim':False, 'final_test_access':False}
