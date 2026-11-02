"""Recomputable certificates. Model-written prose cannot supply a missing premise."""
from .logic import canon, digest, freeze, holds, countermodel, verify_countermodel, check_proof
from .semantics import (graph_facts, graph_reference, value_bridge_witness, anderson_two_worlds,
                        scott_grounding_witness, bayes, guidance, knowledge_without_compliance,
                        maximizer_contract)
from .sources import SOURCES


def bridge_problem(missing=None):
    premises = [
      {'id': 'M1', 'kind': 'metaphysical_premise', 'formula': ('box', 'g')},
      {'id': 'V1', 'kind': 'value_bridge', 'formula': ('box', ('implies', 'g', 'v'))},
      {'id': 'N1', 'kind': 'normative_bridge', 'formula': ('box', ('implies', 'v', 'd'))},
      {'id': 'N2', 'kind': 'application_bridge', 'formula': ('implies', 'd', ('implies', 'e', 'a'))},
      {'id': 'E1', 'kind': 'empirical_condition', 'formula': 'e'}]
    if missing is not None and missing not in {p['id'] for p in premises}: raise ValueError('unknown withdrawal')
    kept = [p for p in premises if p['id'] != missing]
    steps = [{'id': p['id'].lower(), 'rule': 'premise', 'refs': [p['id']], 'formula': p['formula']} for p in premises]
    steps += [
      {'id': 'value', 'rule': 'box_mp', 'refs': ['v1', 'm1'], 'formula': ('box', 'v')},
      {'id': 'duty', 'rule': 'box_mp', 'refs': ['n1', 'value'], 'formula': ('box', 'd')},
      {'id': 'here', 'rule': 'box_T', 'refs': ['duty'], 'formula': 'd'},
      {'id': 'conditional_action', 'rule': 'mp', 'refs': ['n2', 'here'], 'formula': ('implies', 'e', 'a')},
      {'id': 'action', 'rule': 'mp', 'refs': ['conditional_action', 'e1'], 'formula': 'a'}]
    if missing is None:
        proof = check_proof(kept, steps, 'a', 'S5')
        return {'premises': kept, 'steps': steps, 'conclusion': 'a', 'entailed': True, 'proof': proof,
                'countermodel': None, 'frame': 'S5',
                'satisfying_witness': {'n': 1, 'edges': [[0, 0]],
                    'valuation': {a: [True] for a in ('g', 'v', 'd', 'e', 'a')}}}
    witness = countermodel([p['formula'] for p in kept], 'a', max_worlds=1)
    if witness is None: raise AssertionError('withdrawal must have a countermodel')
    return {'premises': kept, 'steps': [], 'conclusion': 'a', 'entailed': False,
            'withdrawn': missing, 'countermodel': witness, 'frame': 'S5'}


def calculate(kind, data):
    if kind == 'grounding':
        result = graph_facts(data['n'], data['edges']); ref = graph_reference(data['n'], data['edges'])
        for k, v in ref.items():
            if result[k] != v: raise AssertionError('independent grounding oracle disagrees')
        if result['theorem_applicable'] and not result['unique_first_principle']: raise AssertionError('ground theorem failed')
        return result, ['grounding']
    if kind == 'necessary_dependent':
        m = {'n': 2, 'edges': [[0, 0], [0, 1], [1, 0], [1, 1]], 'valuation': {'exists_b': [True, True]}}
        return {'model': m, 'grounds': [[0, 1]], 'necessary_b': holds(('box', 'exists_b'), m),
                'b_is_root': 1 in graph_facts(2, [[0, 1]])['roots']}, ['necessity']
    if kind == 'anderson': return anderson_two_worlds(), ['anderson']
    if kind == 'identity': return scott_grounding_witness(data['positive_bearer']), ['identity']
    if kind == 'value': return value_bridge_witness(data['good_root']), ['value']
    if kind == 'bridge': return bridge_problem(data.get('missing')), ['value', 'grounding']
    if kind == 'guidance': return guidance(data['prior'], data['reports'], data.get('independence_declared', False)), ['guidance', 'authentication']
    if kind == 'knowledge': return knowledge_without_compliance(), ['knowledge']
    if kind == 'priority': return maximizer_contract(data['scores'], data['lawful'], data['chosen']), ['motivation']
    raise ValueError('unknown certificate family')


def issue(kind, data):
    result, sources = calculate(kind, data)
    body = {'version': 'ontology-v4-certificate-v1', 'kind': kind, 'input': data, 'result': result,
            'sources': {k: SOURCES[k] for k in sources},
            'new_formal_extension': kind == 'bridge',
            'evidence': 'CHECKED_CONDITIONAL_DERIVATION' if kind == 'bridge' and result['entailed'] else 'EXACT_FINITE_WITNESS',
            'lean_rebuilt': False}
    return {**body, 'sha256': digest(body)}


def verify(cert):
    fresh = issue(cert['kind'], cert['input'])
    if canon(cert) != canon(fresh): raise ValueError('certificate differs from independent recomputation')
    return True


def fixtures():
    report = {'source_id': 'archive_A', 'source_event_id': 'event_1', 'hit': '3/4', 'false_alarm': '1/4',
              'authenticated': True, 'reliability_admitted': True, 'delegated_authority': False}
    return [
      ('root', issue('grounding', {'n': 3, 'edges': [[0, 1], [0, 2], [1, 2]]})),
      ('coherence_withdrawn', issue('grounding', {'n': 3, 'edges': [[0, 2], [1, 2]]})),
      ('necessity_and_dependence', issue('necessary_dependent', {})),
      ('noncollapse', issue('anderson', {})),
      ('identification_without_A6', issue('identity', {'positive_bearer': 1})),
      ('identification_with_A6', issue('identity', {'positive_bearer': 0})),
      ('bare_ground', issue('value', {'good_root': False})),
      ('valued_ground', issue('value', {'good_root': True})),
      ('complete_bridge', issue('bridge', {})),
      *[(f'withdraw_{key}', issue('bridge', {'missing': key})) for key in ('M1', 'V1', 'N1', 'N2', 'E1')],
      ('authenticated_guidance', issue('guidance', {'prior': '1/3', 'reports': [report]})),
      ('repeated_guidance', issue('guidance', {'prior': '1/3', 'reports': [report, report]})),
      ('revoked_source', issue('guidance', {'prior': '1/3', 'reports': [{**report, 'authenticated': False}]})),
      ('knowledge_action_gap', issue('knowledge', {})),
      ('priority_sufficient', issue('priority', {'scores': ['3', '1'], 'lawful': [True, False], 'chosen': 0})),
      ('priority_missing', issue('priority', {'scores': ['1', '3'], 'lawful': [True, False], 'chosen': 1})),
    ]
