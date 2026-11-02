"""Finite Kripke semantics and a small, checked conditional proof calculus.

Finite checks are witnesses or bounded audits. They never replace a Lean proof
of an unbounded theorem. Necessity and moral obligation are distinct symbols.
"""
from __future__ import annotations
from itertools import product
import hashlib
import json


def canon(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canon(value).encode()).hexdigest()


def freeze(x):
    return tuple(freeze(y) for y in x) if isinstance(x, (tuple, list)) else x


def valid_formula(f):
    if isinstance(f, str):
        if not f or not f.replace('_', '').isalnum(): raise ValueError('invalid atom')
        return True
    if not isinstance(f, (tuple, list)) or not f: raise ValueError('invalid formula')
    op, *args = f
    arity = {'top': 0, 'bottom': 0, 'not': 1, 'and': 2, 'or': 2,
             'implies': 2, 'box': 1, 'dia': 1}
    if op not in arity or len(args) != arity[op]: raise ValueError('invalid connective/arity')
    for a in args: valid_formula(a)
    return True


def atoms(f):
    valid_formula(f)
    return {f} if isinstance(f, str) else set().union(*(atoms(x) for x in f[1:]))


def validate_model(m):
    n = m['n']
    if type(n) is not int or not 1 <= n <= 8: raise ValueError('nonempty bounded world domain required')
    edges = m['edges']
    if any(len(e) != 2 or any(type(x) is not int or x not in range(n) for x in e) for e in edges):
        raise ValueError('edge outside world domain')
    if len({tuple(e) for e in edges}) != len(edges): raise ValueError('duplicate edge')
    for a, values in m['valuation'].items():
        valid_formula(a)
        if len(values) != n or any(type(v) is not bool for v in values): raise ValueError('Boolean valuation required')
    return True


def frame_has(m, kind):
    validate_model(m)
    if kind not in ('K', 'T', 'S4', 'S5'): raise ValueError('unknown frame class')
    e = {tuple(x) for x in m['edges']}; ws = range(m['n'])
    refl = all((w, w) in e for w in ws)
    trans = all((a, c) in e for a, b in e for bb, c in e if b == bb)
    symm = all((b, a) in e for a, b in e)
    return kind == 'K' or refl and (kind == 'T' or trans and (kind == 'S4' or symm))


def holds(f, m, w=0):
    valid_formula(f); validate_model(m)
    if w not in range(m['n']): raise ValueError('unknown evaluation world')
    if not atoms(f) <= set(m['valuation']): raise ValueError('missing valuation')
    def go(x, world):
        if isinstance(x, str): return m['valuation'][x][world]
        op, *a = x
        if op == 'top': return True
        if op == 'bottom': return False
        if op == 'not': return not go(a[0], world)
        if op == 'and': return go(a[0], world) and go(a[1], world)
        if op == 'or': return go(a[0], world) or go(a[1], world)
        if op == 'implies': return not go(a[0], world) or go(a[1], world)
        values = [go(a[0], v) for u, v in m['edges'] if u == world]
        return all(values) if op == 'box' else any(values)
    return go(f, w)


def truth_set(f, m):
    """Independent set-algebra evaluator for differential tests."""
    valid_formula(f); validate_model(m)
    universe = set(range(m['n']))
    if isinstance(f, str):
        if f not in m['valuation']: raise ValueError('missing valuation')
        return {i for i, v in enumerate(m['valuation'][f]) if v}
    op, *a = f
    if op == 'top': return universe
    if op == 'bottom': return set()
    left = truth_set(a[0], m)
    if op == 'not': return universe-left
    if op == 'and': return left & truth_set(a[1], m)
    if op == 'or': return left | truth_set(a[1], m)
    if op == 'implies': return (universe-left) | truth_set(a[1], m)
    e = {tuple(x) for x in m['edges']}
    if op == 'box': return {w for w in universe if not any((w, v) in e for v in universe-left)}
    return {w for w in universe if any((w, v) in e for v in left)}


def models(names, n, kind):
    names = sorted(set(names))
    if not 1 <= n <= 3 or len(names) > 6: raise ValueError('exhaustive search bound exceeded')
    pairs = list(product(range(n), repeat=2))
    for mask in range(1 << len(pairs)):
        edges = [list(e) for i, e in enumerate(pairs) if mask >> i & 1]
        shell = {'n': n, 'edges': edges, 'valuation': {}}
        if not frame_has(shell, kind): continue
        for bits in product((False, True), repeat=n*len(names)):
            yield {**shell, 'valuation': {a: list(bits[i*n:(i+1)*n]) for i, a in enumerate(names)}}


def countermodel(premises, conclusion, kind='S5', max_worlds=2):
    names = set().union(*(atoms(f) for f in [*premises, conclusion]))
    for n in range(1, max_worlds+1):
        for m in models(names, n, kind):
            for w in range(n):
                if all(holds(p, m, w) for p in premises) and not holds(conclusion, m, w):
                    return {'model': m, 'world': w}
    return None


def verify_countermodel(witness, premises, conclusion, kind):
    m, w = witness['model'], witness['world']
    return frame_has(m, kind) and all(holds(p, m, w) for p in premises) and not holds(conclusion, m, w)


def check_proof(premises, steps, conclusion, frame='S5'):
    """No unrestricted necessitation: a local assumption cannot become necessary."""
    if frame not in ('K', 'T', 'S4', 'S5'): raise ValueError('unknown frame class')
    if len({p['id'] for p in premises}) != len(premises): raise ValueError('duplicate premise')
    pool = {}; deps = {}; supplied = {p['id']: p for p in premises}
    for p in premises: valid_formula(p['formula'])
    for st in steps:
        sid, rule, refs = st['id'], st['rule'], st.get('refs', [])
        if sid in pool: raise ValueError('duplicate proof step')
        f = freeze(st['formula']); valid_formula(f)
        if rule == 'premise':
            if len(refs) != 1 or refs[0] not in supplied: raise ValueError('unknown premise')
            if f != freeze(supplied[refs[0]]['formula']): raise ValueError('changed premise')
            used = {refs[0]}
        else:
            if any(r not in pool for r in refs): raise ValueError('forward or missing proof reference')
            args = [pool[r] for r in refs]
            used = set().union(*(deps[r] for r in refs))
            if rule == 'mp' and len(args) == 2:
                if args[0] != ('implies', args[1], f): raise ValueError('invalid modus ponens')
            elif rule == 'and_intro' and len(args) == 2:
                if f != ('and', *args): raise ValueError('invalid conjunction')
            elif rule in ('left', 'right') and len(args) == 1:
                if not isinstance(args[0], tuple) or args[0][0] != 'and' or f != args[0][1 if rule == 'left' else 2]:
                    raise ValueError('invalid projection')
            elif rule == 'box_mp' and len(args) == 2:
                if not isinstance(f, tuple) or f[0] != 'box': raise ValueError('boxed conclusion required')
                if not isinstance(args[1], tuple) or args[1][0] != 'box': raise ValueError('boxed antecedent required')
                if args[0] != ('box', ('implies', args[1][1], f[1])): raise ValueError('invalid modal distribution')
            elif rule == 'box_T' and len(args) == 1:
                if frame == 'K' or args[0] != ('box', f): raise ValueError('reflexivity required')
            else: raise ValueError('unsupported inference')
        pool[sid] = f; deps[sid] = used
    if not steps or pool[steps[-1]['id']] != freeze(conclusion): raise ValueError('missing final conclusion')
    return {'verified': True, 'used_premises': sorted(deps[steps[-1]['id']]),
            'steps': len(steps), 'frame': frame, 'proof_sha256': digest([premises, steps, conclusion, frame])}


def render_formula(f, names):
    if isinstance(f, str): return names[f]
    op, *a = f
    if op == 'top': return 'true'
    if op == 'bottom': return 'false'
    if op == 'box': return 'necessarily ('+render_formula(a[0], names)+')'
    if op == 'dia': return 'possibly ('+render_formula(a[0], names)+')'
    if op == 'not': return 'not ('+render_formula(a[0], names)+')'
    word = {'and': ' and ', 'or': ' or ', 'implies': ' implies '}[op]
    return '('+render_formula(a[0], names)+word+render_formula(a[1], names)+')'
