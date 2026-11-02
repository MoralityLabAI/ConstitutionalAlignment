"""Admit a complete, regenerated certificate corpus before any tokenization."""
from __future__ import annotations
import hashlib
import json
import random
from pathlib import Path
from ..ontological_constitution_v4 import curriculum as source
from ..ontological_constitution_v4.logic import canon, digest
from ..ontological_constitution_v4.training import as_sft
from . import VERSION, UPSTREAM

EVIDENCE = 'CERTIFICATE_RENDERED_PUBLIC_EXPLANATION'
DEFAULT_ARMS = ('formal_control', 'platonic_grounding')
PACKAGE = Path(__file__).resolve().parent
REPO = PACKAGE.parents[1]


def hash_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    p = Path(path); p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + '.tmp')
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False)+'\n', encoding='utf-8')
    tmp.replace(p)


def strict_loads(text):
    def unique(items):
        out = {}
        for k, v in items:
            if k in out: raise ValueError('duplicate JSON field: '+k)
            out[k] = v
        return out
    def finite(_): raise ValueError('nonfinite JSON')
    return json.loads(text, object_pairs_hook=unique, parse_constant=finite)


def implementation_hashes():
    files = list(PACKAGE.rglob('*.py'))
    files += list((PACKAGE.parent/'ontological_constitution_v4').rglob('*.py'))
    files += [PACKAGE.parent/'constitutional_reasoning_gym_v3'/name for name in ('runtime.py','core.py')]
    return {p.relative_to(REPO).as_posix(): hashlib.sha256(p.read_bytes().replace(b'\r\n', b'\n')).hexdigest()
            for p in sorted(files) if '__pycache__' not in p.parts}


def load_corpus(directory):
    """Require the pinned v4 default 320-row corpus, not just a trusted class label."""
    root = Path(directory)
    manifest = strict_loads((root/'manifest.json').read_text(encoding='utf-8'))
    expected = source.build_rows(variants=2)
    by_name = {}
    for row in expected:
        by_name.setdefault(row['arm']+'_'+row['view']+'.jsonl', []).append(row)
    if set(manifest.get('files', {})) != set(by_name): raise ValueError('corpus roster mismatch')
    if manifest.get('final_test_access') is not False: raise ValueError('final-test flag')
    if manifest.get('status') != 'CPU_CERTIFICATE_CORPUS': raise ValueError('wrong corpus source')
    actual = {}
    hashes = {'manifest.json': hash_file(root/'manifest.json')}
    for name, reference in by_name.items():
        p = root/name
        if p.is_symlink() or not p.is_file(): raise ValueError('regular corpus file required')
        meta = manifest['files'][name]
        if hash_file(p) != meta['sha256']: raise ValueError('corpus bytes differ: '+name)
        rows = [strict_loads(s) for s in p.read_text(encoding='utf-8').splitlines() if s.strip()]
        if len(rows) != meta['rows'] or len(rows) != len(reference): raise ValueError('corpus count')
        for row, ref in zip(rows, reference):
            source.verify_row(row)
            if row['evidence_class'] != EVIDENCE or row['split'] != 'train': raise ValueError('source type/split')
            if row['teacher_free_text_included'] is not False or canon(row) != canon(ref):
                raise ValueError('row is outside pinned curriculum')
        if len({r['id'] for r in rows}) != len(rows): raise ValueError('duplicate row')
        actual[name] = rows; hashes[name] = hash_file(p)
    if manifest.get('records') != len(expected) or manifest.get('unique_semantic_groups') != 20:
        raise ValueError('corpus total/groups')
    return actual, {'upstream_revision': UPSTREAM, 'evidence_class': EVIDENCE, 'file_sha256': hashes,
                    'records': len(expected), 'semantic_groups': 20, 'all_certificates_revalidated': True,
                    'all_rendered_text_regenerated': True, 'teacher_free_text_admitted': False}


def schedule(corpus, arms=DEFAULT_ARMS, view='derivation', steps=20, seed=11):
    arms = tuple(arms)
    if len(arms) != 2 or len(set(arms)) != 2 or any(a not in source.ARMS for a in arms):
        raise ValueError('two distinct known interpretation arms required')
    if view not in source.VIEWS or type(steps) is not int or not 1 <= steps <= 400:
        raise ValueError('view/update budget')
    groups = {}
    for arm in arms:
        groups[arm] = {}
        for row in corpus[arm+'_'+view+'.jsonl']:
            groups[arm].setdefault(row['group_id'], {})[row['variant']] = row
    gids = sorted(groups[arms[0]])
    if set(gids) != set(groups[arms[1]]): raise ValueError('unmatched groups')
    random.Random(seed).shuffle(gids)
    rounds = []
    for i in range(steps):
        gid = gids[i % len(gids)]
        variant = (i // len(gids) + i % len(gids)) % 2
        rows = {a: groups[a][gid][variant] for a in arms}
        if len({(r['choice'], r['certificate']['sha256'], r['template_family']) for r in rows.values()}) != 1:
            raise ValueError('unmatched certificate/choice')
        rounds.append({'round': i, 'group_id': gid, 'variant': variant,
                       'arm_order': list(arms if i % 2 == 0 else arms[::-1]),
                       'record_ids': {a: r['id'] for a, r in rows.items()}})
    body = {'version': VERSION, 'arms': list(arms), 'view': view, 'seed': seed, 'steps_per_arm': steps,
            'rounds': rounds, 'dose_unit': 'same semantic groups, updates and segment-normalized losses',
            'equal_raw_token_counts_claimed': False}
    return {**body, 'sha256': digest(body)}


def admitted_sft(row):
    source.verify_row(row)
    if row['evidence_class'] != EVIDENCE or row['split'] != 'train': raise ValueError('source admission')
    return as_sft(row)
