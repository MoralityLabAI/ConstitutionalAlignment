"""Ontology-bearing lessons with certificate-rendered public explanations.

Teacher free text is kept outside the verified SFT target. The same certificate
shapes and numeric action contract are shared across the four interpretation arms.
"""
from __future__ import annotations
from pathlib import Path
import copy
import json
import random
from .logic import canon, digest, render_formula
from .certificates import fixtures, issue, verify
from .sources import ARMS, SHARED_CONSTITUTION, SOURCES

VIEWS = ('derivation', 'exposition')


def _vocabulary(arm):
    if arm == 'formal_control': return ('dependency system', 'reference source', 'designated invariant', 'calibration metric')
    if arm == 'secular_realism': return ('order of reasons', 'common explanatory basis', 'necessary principle', 'objective moral value')
    if arm == 'platonic_grounding': return ('ontological order', 'first principle', 'necessary bearer', 'objective goodness')
    return ('ontological order', 'divine-ground candidate', 'God-like bearer', 'divine goodness')


def lesson_content(cert, arm, view='derivation'):
    verify(cert)
    if arm not in ARMS or view not in VIEWS: raise ValueError('unknown lesson condition')
    kind, inp, r = cert['kind'], cert['input'], cert['result']
    domain, root, bearer, value = _vocabulary(arm)
    claims = []
    def claim(cid, statement, provenance='computed'):
        claims.append({'id': cid, 'statement': statement, 'provenance': provenance})
    if kind == 'grounding':
        question = f'In this {domain}, edges point from an immediate ground to its dependent. Decide what follows about a {root}.'
        public = {'domain_size': inp['n'], 'grounding_edges': inp['edges'],
                  'definitions': 'A root has no incoming ground. A universal root reaches every object. Local coherence gives a common ancestor to each pair of immediate co-grounds.'}
        conclusions = ['There is exactly one universal root.', 'The displayed structure has no unique universal root.', 'Root uniqueness alone establishes every evaluative attribute.']
        answer = 0 if r['unique_first_principle'] else 1
        for key in ('well_founded', 'common_effect', 'local_coherence'):
            claim(key, f"{key.replace('_', ' ')} evaluates to {str(r[key]).lower()} in the displayed structure.")
        claim('roots', f"The roots are {r['roots']}; the universal roots are {r['universal_roots']}.")
        if r['theorem_applicable']: claim('theorem', 'The nonempty domain, well-foundedness, common effects and local coherence satisfy the source theorem premises.', 'source-linked finite application')
    elif kind == 'necessary_dependent':
        question = f'Does necessary existence alone make being b the {root}?'
        public = {'worlds': ['w0', 'w1'], 'accessibility': 'all pairs', 'exists_b': [True, True], 'grounding_edges': [['a', 'b']]}
        conclusions = [f'Being b exists necessarily and is nevertheless grounded by a.', f'Being b must be ungrounded because it exists necessarily.', 'An observation cue changes whether b is grounded.']; answer = 0
        claim('necessity', 'Being b exists at every accessible world, so its existence is necessary in this model.')
        claim('dependence', 'The incoming grounding edge from a to b makes b dependent.')
    elif kind == 'anderson':
        question = f'In the specified Anderson-style semantics, can a necessary {bearer} coexist with contingent truths?'
        public = {'worlds': 2, 'individuals': 1, 'accessibility': 'all pairs',
                  'positive_property': 'P(phi) means phi holds of the individual at every world',
                  'definitions': 'G*(x) iff every positive property is exactly a necessary property of x. Essence* uses necessary properties. Necessary existence* requires every essence* to be instantiated necessarily.',
                  'test_proposition': [True, False]}
        conclusions = ['The axioms hold in this finite model and the test proposition remains contingent.', 'Necessary existence makes the test proposition true at every world.', 'The finite model proves every interpretation of positivity.']; answer = 0
        claim('properties', 'All four intensional properties of the one-individual, two-world domain were enumerated.')
        claim('axioms', 'Anderson A1*, A2, A3, A4 and A5 hold in this finite instance.')
        claim('contingency', 'The test proposition is true in one accessible world and false in the other, so modal collapse fails.')
    elif kind == 'identity':
        question = f'Under these interpretations, do the {bearer} and {root} coincide?'
        public = {'worlds': 1, 'individuals': [0, 1], 'grounding_edges': [[0, 1]],
                  'positivity': f"P(phi) is the value of phi at individual {inp['positive_bearer']}",
                  'distinguished_definition': 'an individual has every positive property', 'A6': 'being ungrounded is positive'}
        conclusions = ['They coincide, and A6 holds for this interpretation.', 'They differ, and A6 fails for this interpretation.', 'They coincide independently of A6 in every combined model.']
        answer = 0 if r['coincides_with_first_principle'] else 1
        claim('root', 'Individual 0 is the unique universal grounding root.')
        claim('bearer', f"The distinguished bearer is {r['godlike_bearers'][0]}.")
        claim('A6', f"A6 evaluates to {str(r['A6_root_positive']).lower()}.")
    elif kind == 'value':
        question = f'What connects the unique {root} to {value}?'
        public = {'domain': ['g'], 'grounding_edges': [], 'valuation_at_g': inp['good_root'],
                  'value_bridge': f'Every first principle has {value}.'}
        conclusions = [f'This interpretation satisfies the value bridge and has a valued first principle.',
                       f'The unique root remains, while this interpretation fails the value bridge.',
                       'The grounding relation fixes the valuation without a value premise.']
        answer = 0 if r['value_bridge_holds'] else 1
        claim('root', 'The singleton with no grounding edges has exactly one universal root.')
        claim('valuation', f"The supplied valuation at that root is {str(inp['good_root']).lower()}.")
        claim('bridge', f"The value bridge therefore evaluates to {str(r['value_bridge_holds']).lower()}.")
    elif kind == 'bridge':
        names = ARMS[arm]['names']
        question = 'Does the stated conclusion follow from these premises in S5? Track every value and application bridge.'
        public = {'premises': [{**p, 'reading': render_formula(p['formula'], names)} for p in r['premises']],
                  'conclusion': render_formula(r['conclusion'], names), 'frame': 'S5',
                  'definitions': 'Box quantifies over accessible worlds. The value predicate and the duty predicate are separate.',
                  'bridge_reading': ARMS[arm]['bridge_text']}
        conclusions = ['The conclusion follows under every listed premise.', 'The remaining premises permit a countermodel to the conclusion.', 'The conclusion makes every contingent fact necessary.']
        answer = 0 if r['entailed'] else 1
        for p in r['premises']: claim(p['id'], p['id']+' states: '+render_formula(p['formula'], names)+'.', p['kind'])
        if r['entailed']:
            for step in r['steps'][5:]:
                claim(step['id'], 'Applying '+step['rule']+' gives '+render_formula(step['formula'], names)+'.', 'checked inference')
        else:
            values = r['countermodel']['model']['valuation']
            claim('withdrawal', f"Premise {r['withdrawn']} has been withdrawn; the original derivation cannot reuse it.")
            claim('countermodel', 'A one-world S5 countermodel satisfies every remaining premise with '+
                  '; '.join(names[k]+' = '+str(v[0]).lower() for k, v in sorted(values.items()))+'.')
    elif kind == 'guidance':
        subject = 'a measurement source' if arm == 'formal_control' else 'a claimed source of guidance'
        question = f'How should the supplied evidence about {subject} change belief, and does it supply authority to command?'
        public = {'prior': inp['prior'], 'reports': inp['reports'],
                  'semantics': 'Hit and false alarm are stipulated calibrated likelihoods. Repeated copies of one source event contribute one likelihood update. Command authority is a distinct field.'}
        conclusions = [f"Posterior {r['posterior']}; delegated authority is {str(r['delegated_authority_present']).lower()}.",
                       'A persuasive report proves both the claim and authority to command.',
                       'Every repeated copy from the same event supplies independent evidence.']; answer = 0
        claim('source_events', f"The admitted source events are {r['used_source_events']}; excluded events are {r['excluded_source_events']}.")
        claim('posterior', f"The exact rational posterior is {r['posterior']} under the supplied evidence model.")
        claim('authority', f"Delegated authority evaluates to {str(r['delegated_authority_present']).lower()} and is not inferred from the posterior.")
    elif kind == 'knowledge':
        question = 'Does correctly representing an obligation by itself ensure compliance when observation changes?'
        if arm == 'formal_control': question = 'Does correctly representing a functional specification by itself ensure its implementation under every execution mode?'
        public = {'represented_requirement': True, 'observed_behavior_satisfies_requirement': True,
                  'unobserved_behavior_satisfies_requirement': False}
        conclusions = ['This model separates correct judgment from compliance.', 'Correct judgment forces compliance in every context.', 'Identical vocabulary certifies every execution.']; answer = 0
        claim('knowledge', 'The represented requirement is correct.')
        claim('policy', 'The unobserved behavior violates that requirement, so knowledge alone does not entail compliance.')
    elif kind == 'priority':
        question = 'Which conditions connect maximizing a score to selecting an admissible action?'
        public = inp
        conclusions = ['Feasibility, strict priority and maximization hold, and the chosen action is admissible.',
                       'At least one contract condition fails; this theorem route supplies no guarantee for the selected action.',
                       'Any score-maximizing action is necessarily admissible.']
        answer = 0 if r['contract_holds'] else 1
        for k in ('feasible', 'priority', 'maximizes', 'chosen_lawful'):
            claim(k, k.replace('_', ' ')+' evaluates to '+str(r[k]).lower()+'.')
    else: raise ValueError('unrendered certificate kind')
    if view == 'exposition':
        # Same topic and conclusion, with the derivation steps withheld as a declared ablation.
        rationale = conclusions[answer]+' The source vocabulary and premises are those displayed in the task.'
        claim_ids = []
    else:
        rationale = ' '.join(c['statement'] for c in claims)+' '+conclusions[answer]
        claim_ids = [c['id'] for c in claims]
    return {'question': question, 'public': public, 'options': conclusions, 'answer_index': answer,
            'claims': claims, 'claim_ids': claim_ids, 'rationale': rationale}


def _row(label, cert, arm, view, variant):
    content = lesson_content(cert, arm, view)
    # Permutations are common across frames and views for the same semantic task.
    order = list(range(3)); random.Random(int(digest([label, variant, 'choices'])[:16], 16)).shuffle(order)
    options = [{'id': i, 'text': content['options'][j]} for i, j in enumerate(order)]
    choice = order.index(content['answer_index'])
    group_id = digest([cert['kind'], cert['input']])[:24]
    public = {'question': content['question'], 'given': content['public'], 'options': options}
    system = ARMS[arm]['frame']+'\nShared practical constitution: '+SHARED_CONSTITUTION
    user = canon(public)+'\nGive a public explanation followed by one numeric action object.'
    assistant = content['rationale']+'\nAction: '+canon({'choice': choice})
    row = {'id': digest([group_id, arm, view, variant]), 'group_id': group_id, 'template_family': cert['kind'],
           'label': label, 'arm': arm, 'view': view, 'variant': variant, 'split': 'train',
           'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': user},
                        {'role': 'assistant', 'content': assistant}],
           'certificate': cert, 'claim_ledger': content['claims'], 'used_claim_ids': content['claim_ids'],
           'choice': choice, 'expected_assistant_sha256': digest(assistant),
           'evidence_class': 'CERTIFICATE_RENDERED_PUBLIC_EXPLANATION',
           'natural_eos_targets': 1, 'teacher_free_text_included': False}
    row['sha256'] = digest(row)
    return row


def build_rows(variants=2):
    if type(variants) is not int or not 1 <= variants <= 12: raise ValueError('variant budget')
    return [_row(label, cert, arm, view, v) for label, cert in fixtures()
            for v in range(variants) for arm in ARMS for view in VIEWS]


def verify_row(row):
    cert = row['certificate']; verify(cert)
    expected = _row(row['label'], cert, row['arm'], row['view'], row['variant'])
    if canon(row) != canon(expected): raise ValueError('row, interpretation or rendered claims changed')
    return True


def teacher_request(row):
    verify_row(row)
    ledger = row['claim_ledger']
    return {'record_id': row['id'], 'source_sha256': row['sha256'], 'training_eligible': False,
            'messages': row['messages'][:2]+[{'role': 'user', 'content':
                'You may select and order the verified claims below for teaching. Return exactly '+
                '{"claim_order":[IDs],"commentary":"optional connecting prose"}. '+
                'Do not change premise types or substitute a different counterfactual. '+canon(ledger)}],
            'approved_claim_ids': [x['id'] for x in ledger],
            'certificate': row['certificate']['sha256'], 'free_text_requires_separate_review': True}


def inspect_teacher_reply(row, raw):
    verify_row(row)
    def unique_pairs(pairs):
        out = {}
        for k, v in pairs:
            if k in out: raise ValueError('duplicate field')
            out[k] = v
        return out
    obj = json.loads(raw, object_pairs_hook=unique_pairs)
    if not isinstance(obj, dict) or set(obj) != {'claim_order', 'commentary'}: raise ValueError('teacher schema')
    expected = {x['id'] for x in row['claim_ledger']}
    ids = obj['claim_order']
    if not isinstance(ids, list) or any(not isinstance(x, str) for x in ids) or len(ids) != len(set(ids)) or set(ids) != expected:
        raise ValueError('claims omitted, invented or duplicated')
    if row['certificate']['kind'] == 'bridge' and row['certificate']['result']['entailed']:
        steps = row['certificate']['result']['steps']
        aliases = {s['id']: s['refs'][0] if s['rule'] == 'premise' else s['id'] for s in steps}
        position = {cid: i for i, cid in enumerate(ids)}
        for st in steps:
            if st['rule'] != 'premise' and any(position[aliases[r]] >= position[st['id']] for r in st['refs']):
                raise ValueError('claim order violates proof dependencies')
    if not isinstance(obj['commentary'], str): raise ValueError('commentary must be text')
    # Verified order is allowed; arbitrary commentary is quarantined, never auto-exported.
    by_id = {x['id']: x['statement'] for x in row['claim_ledger']}
    return {'verified_text': ' '.join(by_id[x] for x in ids), 'commentary': obj['commentary'],
            'commentary_sha256': digest(obj['commentary']), 'commentary_training_eligible': False,
            'claim_selection_verified': True, 'free_text_semantics_verified': False}


def export(out, variants=2):
    out = Path(out)
    if out.exists(): raise FileExistsError('use a fresh output directory')
    out.mkdir(parents=True)
    rows = build_rows(variants)
    for row in rows: verify_row(row)
    files = {}
    for arm in ARMS:
        for view in VIEWS:
            subset = [r for r in rows if r['arm'] == arm and r['view'] == view]
            name = arm+'_'+view+'.jsonl'; text = ''.join(canon(r)+'\n' for r in subset)
            (out/name).write_text(text, encoding='utf-8', newline='\n')
            files[name] = {'rows': len(subset), 'groups': len({r['group_id'] for r in subset}),
                           'sha256': __import__('hashlib').sha256(text.encode()).hexdigest(),
                           'assistant_words': sum(len(r['messages'][-1]['content'].split()) for r in subset)}
    requests = [teacher_request(r) for r in rows if r['view'] == 'derivation']
    (out/'teacher_requests.jsonl').write_text(''.join(canon(r)+'\n' for r in requests), encoding='utf-8', newline='\n')
    manifest = {'version': 'ontology-v4-curriculum-v1', 'status': 'CPU_CERTIFICATE_CORPUS', 'records': len(rows),
                'paired_interpretation_arms': list(ARMS), 'views': list(VIEWS), 'files': files,
                'unique_semantic_groups': len({r['group_id'] for r in rows}),
                'proof_families': sorted({r['template_family'] for r in rows}),
                'generated_model_tokens': 0, 'tokenizer_counts': 'NOT_RUN', 'final_test_access': False,
                'lean_rebuilt': False, 'upstream_sources': SOURCES,
                'templates_not_population_sample': True, 'teacher_requests_unexecuted': len(requests)}
    (out/'manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True)+'\n', encoding='utf-8')
    return manifest
