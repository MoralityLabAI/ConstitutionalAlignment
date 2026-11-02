"""Admission, paired schedule, and local-only tokenizer accounting."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import random
import re
from experiments.ontological_constitution_v4 import curriculum, dilemmas, training
from experiments.ontological_constitution_v4.logic import canon, digest
from experiments.ontological_constitution_v4.sources import SHARED_CONSTITUTION
from experiments.constitutional_reasoning_gym_v3.core import strict_json
from experiments.constitutional_reasoning_gym_v3.runtime import encode_sft

BASE_SHA = 'af65c17d2f85fc2049c50a4074e518bcf903dbf7'
MODEL_REVISION = '1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0'
ARMS = ('formal_control', 'platonic_grounding')
UPSTREAM_RECEIPT_SHA = '256825450a3e298bf2c9d5a4f5140355053142a968884ab692d21cf75205af90'
EVIDENCE = 'CERTIFICATE_RENDERED_PUBLIC_EXPLANATION'
PACKAGE = Path(__file__).resolve().parent
ROOT = PACKAGE.parents[1]


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''): h.update(block)
    return h.hexdigest()


def write_json(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n', encoding='utf-8', newline='\n')
    tmp.replace(path)


def source_hashes():
    paths = list(PACKAGE.rglob('*.py')) + list((ROOT/'experiments/ontological_constitution_v4').glob('*.py'))
    paths += [ROOT/'experiments/constitutional_reasoning_gym_v3'/n for n in ('runtime.py', 'core.py')]
    paths += list((PACKAGE/'scripts').glob('*.sh'))
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes().replace(b'\r\n', b'\n')).hexdigest()
            for p in sorted(paths) if '__pycache__' not in p.parts}


def verify_upstream():
    parent = ROOT/'experiments/ontological_constitution_v4'
    receipt = parent/'results/cpu_receipt.json'
    raw = receipt.read_bytes().replace(b'\r\n', b'\n')
    if hashlib.sha256(raw).hexdigest() != UPSTREAM_RECEIPT_SHA:
        raise ValueError('pinned upstream receipt changed')
    hashes = json.loads(raw)['source_sha256']
    for name, expected in hashes.items():
        actual = hashlib.sha256((parent/name).read_bytes().replace(b'\r\n', b'\n')).hexdigest()
        if actual != expected: raise ValueError('upstream source changed: ' + name)
    return hashes


def load_corpus(directory):
    """Recompute the entire canonical roster before loading any model."""
    verify_upstream()
    directory = Path(directory)
    manifest = strict_json((directory/'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('version') != 'ontology-v4-curriculum-v1' or manifest.get('final_test_access') is not False:
        raise ValueError('wrong corpus contract')
    expected = curriculum.build_rows(2)
    expected_files = {f'{a}_{v}.jsonl' for a in curriculum.ARMS for v in curriculum.VIEWS}
    if set(manifest.get('files', {})) != expected_files: raise ValueError('corpus file roster changed')
    rows = []
    for name in sorted(expected_files):
        path = directory/name
        if path.is_symlink() or not path.is_file(): raise ValueError('corpus files must be regular files')
        meta = manifest['files'][name]
        if file_hash(path) != meta['sha256']: raise ValueError('corpus file hash: ' + name)
        found = [strict_json(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
        canonical = [r for r in expected if f"{r['arm']}_{r['view']}.jsonl" == name]
        if canon(found) != canon(canonical): raise ValueError('certificate/renderer/roster differs: ' + name)
        if meta['rows'] != len(found) or meta['groups'] != len({r['group_id'] for r in found}):
            raise ValueError('manifest counts')
        for row in found: curriculum.verify_row(row)
        rows.extend(found)
    if manifest['records'] != len(rows) or manifest['unique_semantic_groups'] != 20:
        raise ValueError('manifest total')
    return rows, manifest


def proof_entry(row):
    curriculum.verify_row(row)
    if row['evidence_class'] != EVIDENCE or row['split'] != 'train' or row['teacher_free_text_included']:
        raise ValueError('unadmitted proof source')
    return {'kind': 'proof', 'pair_id': digest(['proof', row['group_id'], row['variant']]),
            'source_row': row, 'sft': training.as_sft(row)}


def practice_entry(scene, truth):
    # A separate, openly declared common practice set. No development records are imported.
    case = dilemmas.make_case(scene, truth, False, False, True, seed=14011, instance=list(dilemmas.SCENES).index(scene))
    dilemmas.verify_case(case)
    sft = {'record_id': case['sha256'], 'group_id': case['motif_id'], 'split': 'train',
           'arm': 'common_practice', 'system': SHARED_CONSTITUTION, 'user': dilemmas.prompt(case),
           'rationale': '', 'final': canon({'choice': case['expected_choice']}), 'format_only': True,
           'rationale_weight': 0., 'action_weight': 1., 'natural_eos_targets': 1,
           'source_evidence_class': 'CHECKED_PRACTICAL_APPLICATION'}
    return {'kind': 'practice', 'pair_id': digest(['practice', case['sha256']]), 'source_case': case, 'sft': sft}


def validate_entry(entry):
    if entry.get('kind') == 'proof':
        expected = proof_entry(entry['source_row'])
    elif entry.get('kind') == 'practice':
        c = entry['source_case']; expected = practice_entry(c['scene'], c['truth'])
    else: raise ValueError('source type not admitted')
    if canon(entry) != canon(expected): raise ValueError('SFT target does not follow the verified source')
    return True


def make_schedule(rows, seed=11):
    if type(seed) is not int or seed < 0: raise ValueError('seed')
    chosen = {a: [] for a in ARMS}
    for group in sorted({r['group_id'] for r in rows}):
        variant = int(digest([seed, group, 'common-permutation'])[:8], 16) % 2
        for a in ARMS:
            candidates = [r for r in rows if r['group_id'] == group and r['arm'] == a and r['view'] == 'derivation' and r['variant'] == variant]
            if len(candidates) != 1: raise ValueError('incomplete paired curriculum')
            chosen[a].append(proof_entry(candidates[0]))
    for scene in dilemmas.SCENES:
        for truth in (False, True):
            entry = practice_entry(scene, truth)
            for a in ARMS: chosen[a].append(entry)
    order = list(range(len(chosen[ARMS[0]]))); random.Random(seed).shuffle(order)
    blocks = []
    for i, index in enumerate(order):
        entries = {a: chosen[a][index] for a in ARMS}
        if len({e['pair_id'] for e in entries.values()}) != 1: raise ValueError('pair mismatch')
        blocks.append({'index': i, 'arm_order': list(ARMS[i % 2:] + ARMS[:i % 2]), 'entries': entries})
    body = {'version': 'v4-certificate-training-schedule-v1', 'base_source': BASE_SHA, 'seed': seed,
            'arms': list(ARMS), 'view': 'derivation', 'proof_groups_per_arm': 20,
            'common_practice_per_arm': 16, 'updates_per_arm': 36, 'blocks': blocks,
            'equal_examples_and_updates': True, 'equal_token_counts_claimed': False,
            'pilot_only': True, 'final_test_access': False}
    return {**body, 'sha256': digest(body)}


def validate_schedule(schedule, rows):
    if canon(schedule) != canon(make_schedule(rows, schedule['seed'])):
        raise ValueError('schedule regeneration failed')
    for block in schedule['blocks']:
        for entry in block['entries'].values(): validate_entry(entry)
    return True


def tokenizer_identity(root, revision):
    root = Path(root)
    if not root.is_dir() or not re.fullmatch('[0-9a-f]{40}', revision): raise ValueError('local tokenizer and immutable declared revision required')
    if any(not (root/n).is_file() for n in ('tokenizer.json', 'tokenizer_config.json', 'config.json')):
        raise ValueError('tokenizer metadata missing')
    names = ('tokenizer.json', 'tokenizer_config.json', 'config.json', 'special_tokens_map.json', 'added_tokens.json', 'vocab.json', 'merges.txt', 'chat_template.jinja')
    files = {n: file_hash(root/n) for n in names if (root/n).is_file()}
    for p in sorted((root/'chat_templates').glob('*.jinja')): files[p.relative_to(root).as_posix()] = file_hash(p)
    return {'declared_model_revision': revision, 'revision_attestation': 'compare file hashes with retained provider receipt', 'files': files}


def load_tokenizer(root, revision):
    import os
    os.environ['HF_HUB_OFFLINE'] = '1'; os.environ['TRANSFORMERS_OFFLINE'] = '1'
    identity = tokenizer_identity(root, revision)
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(str(root), local_files_only=True, trust_remote_code=False)
    if not tok.chat_template or tok.eos_token_id is None: raise ValueError('native chat template and EOS required')
    if tok.pad_token_id is None: tok.pad_token_id = tok.eos_token_id
    return tok, identity


def encode_entry(tokenizer, entry, context=4096):
    validate_entry(entry)
    if not tokenizer.chat_template or type(tokenizer.eos_token_id) is not int:
        raise ValueError('native template/EOS required')
    encoded = encode_sft(tokenizer, entry['sft'], context)
    ids, labels, seg = encoded['input_ids'], encoded['labels'], encoded['segments']
    if len(ids) != len(labels) or len(ids) != len(seg): raise ValueError('encoding lengths')
    if sum(x == tokenizer.eos_token_id for x in labels) != 1 or labels[-1] != tokenizer.eos_token_id:
        raise ValueError('exactly one supervised EOS required')
    if any(label != -100 for label, kind in zip(labels, seg) if kind == 0): raise ValueError('prompt loss leakage')
    if any(label != token for label, token, kind in zip(labels, ids, seg) if kind == 2): raise ValueError('action masking')
    if not any(kind == 2 for kind in seg): raise ValueError('missing action targets')
    return encoded


def measure(tokenizer, rows, schedule, context=4096):
    validate_schedule(schedule, rows)
    all_conditions = {}
    failures = []
    for row in rows:
        key = row['arm'] + '_' + row['view']
        totals = all_conditions.setdefault(key, {'rows': 0, 'input_tokens': 0, 'rationale_tokens': 0, 'action_tokens': 0, 'max_sequence': 0})
        try: enc = encode_entry(tokenizer, proof_entry(row), context)
        except ValueError as exc:
            failures.append({'record_id': row['id'], 'error': str(exc)}); continue
        totals['rows'] += 1; totals['input_tokens'] += len(enc['input_ids'])
        totals['rationale_tokens'] += enc['segments'].count(1); totals['action_tokens'] += enc['segments'].count(2)
        totals['max_sequence'] = max(totals['max_sequence'], len(enc['input_ids']))
    selected = {a: {'updates': 0, 'input_tokens': 0, 'rationale_tokens': 0, 'action_tokens': 0, 'EOS_targets': 0} for a in ARMS}
    encodings = {}
    for b in schedule['blocks']:
        for a in ARMS:
            try: enc = encode_entry(tokenizer, b['entries'][a], context)
            except ValueError as exc:
                failures.append({'pair_id': b['entries'][a]['pair_id'], 'arm': a, 'error': str(exc)}); continue
            encodings[f"{b['index']}:{a}"] = digest(enc)
            s = selected[a]; s['updates'] += 1; s['input_tokens'] += len(enc['input_ids'])
            s['rationale_tokens'] += enc['segments'].count(1); s['action_tokens'] += enc['segments'].count(2)
            s['EOS_targets'] += sum(x == tokenizer.eos_token_id for x in enc['labels'])
    denom = selected[ARMS[0]]['input_tokens']
    delta = None if not denom else (selected[ARMS[1]]['input_tokens'] - denom) / denom
    return {'status': 'TOKENIZER_PASS' if not failures else 'TOKENIZER_FAIL', 'failures': failures,
            'all_conditions': all_conditions, 'scheduled_counts': selected, 'encoding_sha256': encodings,
            'relative_input_delta_platonic_minus_formal': delta, 'context_limit': context,
            'chat_template_sha256': digest(tokenizer.chat_template), 'eos_token_id': tokenizer.eos_token_id,
            'equal_token_counts_claimed': False, 'source_sha256': source_hashes()}


def preflight(corpus, tokenizer_dir, revision, out, context=4096):
    out = Path(out)
    if out.exists(): raise FileExistsError('fresh preflight directory required')
    rows, manifest = load_corpus(corpus); schedule = make_schedule(rows)
    tok, identity = load_tokenizer(tokenizer_dir, revision)
    report = measure(tok, rows, schedule, context)
    report.update(tokenizer=identity, corpus_manifest_sha256=file_hash(Path(corpus)/'manifest.json'),
                  schedule_sha256=schedule['sha256'], tokenizer_evidence='RETAINED_NATIVE_TOKENIZER',
                  weights_loaded=False, GPU_jobs=0)
    out.mkdir(parents=True); write_json(out/'schedule.json', schedule)
    write_json(out/'tokenizer_preflight.json', report)
    if report['status'] != 'TOKENIZER_PASS': raise ValueError('tokenizer gate failed; see preserved receipt')
    return report
