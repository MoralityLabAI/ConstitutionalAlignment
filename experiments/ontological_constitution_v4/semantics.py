"""Independent finite witnesses for the pinned ontological and guidance sources."""
from fractions import Fraction as F
from itertools import product
from .logic import digest


def graph_facts(n, edges):
    if type(n) is not int or not 1 <= n <= 8: raise ValueError('nonempty finite domain required')
    e = {tuple(x) for x in edges}
    if len(e) != len(edges) or any(len(x) != 2 or any(type(i) is not int or i not in range(n) for i in x) for x in e):
        raise ValueError('invalid grounding relation')
    reach = {(i, i) for i in range(n)} | e
    for k in range(n):
        for i in range(n):
            for j in range(n):
                if (i, k) in reach and (k, j) in reach: reach.add((i, j))
    roots = [i for i in range(n) if not any(b == i for a, b in e)]
    wf = not any((i, i) in e or any((i, j) in e and (j, i) in reach for j in range(n)) for i in range(n))
    common_effect = all(any((x, z) in reach and (y, z) in reach for z in range(n)) for x in range(n) for y in range(n))
    coherent = all(any((w, x) in reach and (w, y) in reach for w in range(n))
                   for x, z in e for y, zz in e if z == zz)
    universal = [r for r in roots if all((r, x) in reach for x in range(n))]
    return {'nonempty': True, 'well_founded': wf, 'common_effect': common_effect,
            'local_coherence': coherent, 'roots': roots, 'universal_roots': universal,
            'unique_first_principle': len(universal) == 1,
            'theorem_applicable': wf and common_effect and coherent,
            'reach': [list(x) for x in sorted(reach)]}


def graph_reference(n, edges):
    """BFS and Kahn elimination, separate from the closure implementation."""
    if n < 1: raise ValueError('empty domain')
    adjacency = {i: set() for i in range(n)}
    for a, b in edges: adjacency[a].add(b)
    def reachable(start):
        seen = {start}; todo = [start]
        while todo:
            for nxt in adjacency[todo.pop()]-seen: seen.add(nxt); todo.append(nxt)
        return seen
    rows = [reachable(i) for i in range(n)]
    incoming = {i: {a for a in range(n) if i in adjacency[a]} for i in range(n)}
    remaining = set(range(n))
    while True:
        ready = {v for v in remaining if not (incoming[v] & remaining)}
        if not ready: break
        remaining -= ready
    roots = [v for v in range(n) if not incoming[v]]
    return {'well_founded': not remaining,
            'common_effect': all(rows[x] & rows[y] for x in range(n) for y in range(n)),
            'local_coherence': all(any(x in rows[w] and y in rows[w] for w in range(n))
                                   for z in range(n) for x in incoming[z] for y in incoming[z]),
            'universal_roots': [v for v in roots if len(rows[v]) == n]}


def value_bridge_witness(good_root):
    if type(good_root) is not bool: raise ValueError('Boolean valuation required')
    g = graph_facts(1, [])
    return {'graph': g, 'good': [good_root], 'value_bridge_holds': good_root,
            'good_first_principle_exists': good_root,
            'grounding_without_value_counterexample': g['unique_first_principle'] and not good_root}


def anderson_two_worlds():
    """Exhaust every intensional property of one individual in two S5 worlds."""
    props = list(product((False, True), repeat=2))
    pos = lambda p: all(p)
    ent = lambda p, q: all(not a or b for a, b in zip(p, q))
    godlike = tuple(all(pos(p) == all(p) for p in props) for _ in range(2))
    essence = lambda p: all(all(q) == ent(p, q) for q in props)
    ne = tuple(all(not essence(p) or all(p) for p in props) for _ in range(2))
    axioms = {'A1_weak': all(not pos(p) or not pos(tuple(not v for v in p)) for p in props),
              'A2': all(not (pos(p) and ent(p, q)) or pos(q) for p in props for q in props),
              'A3': pos(godlike), 'A4': all(not pos(p) or all(pos(p) for _ in range(2)) for p in props),
              'A5': pos(ne)}
    return {'worlds': 2, 'individuals': 1, 'properties_enumerated': len(props),
            'frame': 'S5_total', 'axioms': axioms, 'necessary_godlike_existence': all(godlike),
            'contingent_property': [True, False], 'modal_collapse': False,
            'evidence': 'EXACT_FINITE_INSTANCE_OF_PINNED_MODEL'}


def scott_grounding_witness(positive_bearer=1):
    if positive_bearer not in (0, 1): raise ValueError('bearer outside domain')
    props = list(product((False, True), repeat=2))
    pos = lambda p: p[positive_bearer]
    ent = lambda p, q: all(not a or b for a, b in zip(p, q))
    godlike = [all(not pos(p) or p[x] for p in props) for x in range(2)]
    essence = lambda p, x: p[x] and all(not q[x] or ent(p, q) for q in props)
    ne = tuple(all(not essence(p, x) or any(p) for p in props) for x in range(2))
    axioms = {'A1': all(pos(tuple(not v for v in p)) == (not pos(p)) for p in props),
              'A2': all(not (pos(p) and ent(p, q)) or pos(q) for p in props for q in props),
              'A3': pos(godlike), 'A4': True, 'A5': pos(ne)}
    roots = [True, False]
    return {'worlds': 1, 'individuals': 2, 'properties_enumerated': 4, 'scott_axioms': axioms,
            'grounding': graph_facts(2, [[0, 1]]), 'godlike_bearers': [i for i, b in enumerate(godlike) if b],
            'A6_root_positive': pos(roots), 'coincides_with_first_principle': godlike[0]}


def bayes(prior, hit, false_alarm):
    p, h, f = F(prior), F(hit), F(false_alarm)
    if not 0 < p < 1 or not 0 <= h <= 1 or not 0 <= f <= 1: raise ValueError('invalid probability')
    den = p*h+(1-p)*f
    if den == 0: raise ValueError('zero-probability evidence')
    posterior = p*h/den
    return {'prior': str(p), 'hit': str(h), 'false_alarm': str(f), 'posterior': str(posterior),
            'increases': posterior > p, 'increase_iff_likelihood_favors_claim': (posterior > p) == (h > f)}


def guidance(prior, reports, independence_declared=False):
    """Authentication, calibrated likelihood and delegated authority stay separate."""
    p = F(prior)
    if not 0 < p < 1: raise ValueError('interior prior required')
    selected = {}; excluded = []; snapshots = {}
    for r in reports:
        if type(r['authenticated']) is not bool or type(r['reliability_admitted']) is not bool or type(r['delegated_authority']) is not bool:
            raise ValueError('source status must be Boolean')
        key = r['source_event_id']
        snapshot = (r['source_id'], F(r['hit']), F(r['false_alarm']), r['authenticated'], r['reliability_admitted'], r['delegated_authority'])
        if key in snapshots and snapshots[key] != snapshot: raise ValueError('conflicting source-event snapshot')
        snapshots[key] = snapshot
        if not r['authenticated'] or not r['reliability_admitted']:
            excluded.append(key); continue
        identity = (r['source_id'], F(r['hit']), F(r['false_alarm']), r['delegated_authority'])
        if key in selected and selected[key] != identity: raise ValueError('conflicting repeated source event')
        selected[key] = identity
    if len(selected) > 1 and not independence_declared: raise ValueError('joint likelihood or independence premise required')
    numerator, other = p, 1-p
    for source, h, f, authority in selected.values():
        if not 0 <= h <= 1 or not 0 <= f <= 1: raise ValueError('invalid likelihood')
        numerator *= h; other *= f
    if numerator+other == 0: raise ValueError('zero-probability evidence')
    result = numerator/(numerator+other)
    return {'posterior': str(result), 'used_source_events': sorted(selected), 'excluded_source_events': sorted(excluded),
            'delegated_authority_present': any(a for s, h, f, a in selected.values()),
            'independence_premise': independence_declared, 'source_truth_and_authority_distinct': True}


def knowledge_without_compliance():
    return {'knows_duty': True, 'watched_action_lawful': True, 'unwatched_action_lawful': False,
            'knowledge_implies_compliance': False, 'nonempty_actions': True}


def maximizer_contract(scores, lawful, chosen):
    scores = list(map(F, scores)); lawful = list(lawful)
    if not scores or len(scores) != len(lawful) or any(type(x) is not bool for x in lawful) or chosen not in range(len(scores)):
        raise ValueError('invalid finite action problem')
    feasible = any(lawful)
    priority = all(scores[i] > scores[j] for i in range(len(scores)) for j in range(len(scores)) if lawful[i] and not lawful[j])
    maximizes = all(x <= scores[chosen] for x in scores)
    return {'feasible': feasible, 'priority': priority, 'maximizes': maximizes,
            'chosen_lawful': lawful[chosen], 'contract_holds': feasible and priority and maximizes}
