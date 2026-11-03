"""Frozen, counterbalanced assignment roster with novel family-level holdouts."""
from __future__ import annotations
import itertools
from . import VERSION
from .cases import FAMILIES, make_case, verify_case, canon, digest, prompt

ARMS = ('base', 'formal_control', 'platonic_grounding', 'intellect3')
DEFAULT_SEED = 20261102


def cells(mode):
    if mode == 'smoke':
        # Orthogonal strength-2 8-run array for 5 binary factors.
        return [(bool(a^c),bool(a),bool(b),bool(c),bool(a^b))
                for a,b,c in itertools.product((0,1),repeat=3)]
    if mode == 'paired_smoke':
        # Paired single-factor interventions, same semantic motif. Distinct from frozen smoke.
        zero=(False,)*5
        return [zero]+[tuple(i==k for i in range(5)) for k in range(5)]
    if mode == 'full':return list(itertools.product((False,True),repeat=5))
    raise ValueError('mode must be smoke or full')


def make_plan(mode='smoke', motifs_per_family=None, seed=DEFAULT_SEED):
    if type(seed) is not int or not 0<=seed<2**63:raise ValueError('invalid seed')
    if motifs_per_family is None:motifs_per_family=1 if mode in ('smoke','paired_smoke') else 2
    if type(motifs_per_family) is not int or not 1<=motifs_per_family<=12:raise ValueError('invalid motif count')
    block_list=[]
    for fi,family in enumerate(FAMILIES):
        for m in range(motifs_per_family):
            # Distinct independent motif domains; each has the same five-factor assignment.
            cases=[make_case(family,m,*flags,seed=seed) for flags in cells(mode)]
            block_list.append({'motif_id':cases[0]['motif_id'], 'family':family,'motif_index':m,
                               'cells':cases})
    total=sum(len(x['cells']) for x in block_list)
    body={'version':VERSION,'mode':mode,'motifs_per_family':motifs_per_family,'seed':seed,
          'split':'prospective_development', 'final_test_access':False,
          'arms':list(ARMS),'blocks':block_list,'records_per_arm':total,
          'assigned_records_all_arms':total*len(ARMS),
          'independence_unit':'semantic motif',
          'response_schema':{'choice':'integer 0..3','reason_code':'integer 0..3'},
          'training_exclusion':'This split and every derived response must be excluded from later training.'}
    body['sha256']=digest(body)
    return body


def verify_plan(plan):
    expected=make_plan(plan['mode'],plan['motifs_per_family'],plan['seed'])
    if canon(expected)!=canon(plan):raise ValueError('plan/certificates/roster modified')
    return True


def assignments(plan, arms=None):
    verify_plan(plan)
    selected=plan['arms'] if arms is None else list(arms)
    if not selected or len(set(selected))!=len(selected) or any(a not in plan['arms'] for a in selected):raise ValueError('invalid arms')
    # Model order rotates at the motif level; within each model the case order
    # is fixed before observing a response.
    for i,block in enumerate(plan['blocks']):
        rotated=plan['arms'][i%len(plan['arms']):]+plan['arms'][:i%len(plan['arms'])]
        for arm in rotated:
            if arm not in selected:continue
            for case in block['cells']:
                yield {'assignment_id':digest([plan['sha256'],arm,case['case_id']])[:28],
                       'arm':arm,'case_id':case['case_id'],'case_sha256':case['sha256'],
                       'motif_id':block['motif_id'],'family':block['family'],
                       'prompt':prompt(case)}


def public_cases(plan):
    verify_plan(plan)
    return [{'case_id':c['case_id'],'motif_id':c['motif_id'],'family':c['family'],
             'public':c['public'],'public_sha256':digest(c['public'])}
            for b in plan['blocks'] for c in b['cells']]


def spread_assignments(plan, arms=None):
    """Interleave model arms and families under a bounded run budget.

    A truncated inference budget then covers every semantic family early,
    avoiding first-family-only partial receipts. Exact roster identity and
    scoring are unchanged.
    """
    chosen=plan['arms'] if arms is None else list(arms)
    grouped={(family,arm):[] for family in FAMILIES for arm in chosen}
    for a in assignments(plan,chosen):grouped[(a['family'],a['arm'])].append(a)
    mx=max(map(len,grouped.values()))
    for index in range(mx):
        for fi,family in enumerate(FAMILIES):
            rotated=chosen[fi%len(chosen):]+chosen[:fi%len(chosen)]
            for arm in rotated:
                rows=grouped[(family,arm)]
                if index<len(rows):yield rows[index]
