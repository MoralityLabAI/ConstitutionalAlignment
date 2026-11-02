"""Tokenizer-only measurement. No CUDA or model-weight import in this module."""
from __future__ import annotations
import json
from pathlib import Path
from ..ontological_constitution_v4.logic import digest
from .admission import (admitted_sft, load_corpus, schedule, DEFAULT_ARMS,
                        implementation_hashes, hash_file, write_json, strict_loads)

TOKENIZER_FILES = ('config.json', 'tokenizer.json', 'tokenizer_config.json', 'special_tokens_map.json',
                   'added_tokens.json', 'vocab.json', 'merges.txt', 'chat_template.jinja', 'generation_config.json')


def tokenizer_identity(path, revision):
    path = Path(path)
    if not path.is_dir() or len(revision) != 40 or any(c not in '0123456789abcdef' for c in revision):
        raise ValueError('local tokenizer snapshot and immutable revision required')
    for name in ('config.json', 'tokenizer.json', 'tokenizer_config.json'):
        if not (path/name).is_file(): raise FileNotFoundError(name)
    files = {name: hash_file(path/name) for name in TOKENIZER_FILES if (path/name).is_file()}
    template_dir = path/'chat_templates'
    if template_dir.is_dir():
        files.update({'chat_templates/'+p.name: hash_file(p) for p in sorted(template_dir.glob('*.jinja'))})
    return {'kind': 'LOCAL_STUDENT_TOKENIZER', 'declared_model_revision': revision, 'files_sha256': files,
            'snapshot_directory_matches_revision': path.resolve().name == revision,
            'provider_revision_attestation_required': True, 'weights_read': False}


def load_tokenizer(path):
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(str(path), local_files_only=True, trust_remote_code=False, use_fast=True)
    if not tok.is_fast or not tok.chat_template or tok.eos_token_id is None or not tok.eos_token:
        raise ValueError('fast native chat tokenizer and EOS required')
    if tok.pad_token_id is None: tok.pad_token_id = tok.eos_token_id
    return tok


def encode(row, tok, max_length=4096):
    """Tokenize the full causal sequence once; use offsets to mask exact spans.

    The native generation prefix is the actor's prefix too. One real EOS terminates
    the certified assistant continuation. Special-token text never gets duplicated.
    """
    s = admitted_sft(row)
    if not getattr(tok, 'is_fast', False) or not getattr(tok, 'chat_template', None):
        raise ValueError('native fast tokenizer required')
    messages = [{'role':'system','content':s['system']}, {'role':'user','content':s['user']}]
    prefix = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True, enable_thinking=False)
    reason = 'Rationale:\n'+s['rationale']+'\n'
    action = 'Action:\n'+s['final']
    if tok.eos_token in reason+action: raise ValueError('literal EOS inside certified response')
    text = prefix+reason+action+tok.eos_token
    enc = tok(text, add_special_tokens=False, return_offsets_mapping=True)
    ids = list(enc['input_ids']); offsets = enc['offset_mapping']
    if len(ids) > max_length: raise ValueError(f'context overflow: {len(ids)} > {max_length}; no truncation')
    if not ids or len(ids) != len(offsets) or ids[-1] != tok.eos_token_id: raise ValueError('token/offset/EOS contract')
    boundary = len(prefix); action_start = boundary+len(reason)
    labels = []; segments = []
    for i, (token, span) in enumerate(zip(ids, offsets)):
        lo, hi = map(int, span)
        if i == len(ids)-1:
            label, segment = token, 2
        elif hi <= boundary:
            label, segment = -100, 0
        elif lo < boundary:
            raise ValueError('token crosses prompt/target boundary')
        else:
            label, segment = token, (1 if hi <= action_start else 2)
        labels.append(label); segments.append(segment)
    first = next((i for i, v in enumerate(labels) if v != -100), None)
    if first is None or first == 0: raise ValueError('no masked prompt or targets')
    if ids[:first] != list(tok.encode(prefix, add_special_tokens=False)):
        raise ValueError('native prefix tokenization changed across boundary')
    if sum(v == tok.eos_token_id for v in labels if v != -100) != 1:
        raise ValueError('exactly one supervised EOS required')
    if not all(any(seg == k and lab != -100 for seg, lab in zip(segments, labels)) for k in (1,2)):
        raise ValueError('missing rationale or action segment')
    return {'record_id': row['id'], 'input_ids': ids, 'labels': labels, 'segments': segments,
            'attention_mask': [1]*len(ids), 'rationale_weight': .25, 'action_weight': 1.,
            'certificate_sha256': row['certificate']['sha256'], 'text_sha256': digest(text)}


def preflight(corpus_dir, tok, identity, out=None, arms=DEFAULT_ARMS, steps=20, seed=11, max_length=4096, view='derivation'):
    corpus, admission = load_corpus(corpus_dir)
    plan = schedule(corpus, arms, view, steps, seed)
    encoded = {}; row_counts = {}; errors = []
    for filename, rows in corpus.items():
        counts = []
        for row in rows:
            try:
                e = encode(row, tok, max_length); encoded[row['id']] = e
                counts.append({'id': row['id'], 'group_id': row['group_id'], 'input_tokens': len(e['input_ids']),
                    'rationale_targets': e['segments'].count(1), 'action_targets_including_eos': e['segments'].count(2),
                    'supervised_eos_targets': 1})
            except (ValueError, TypeError, KeyError) as exc:
                errors.append({'id': row['id'], 'file': filename, 'error': str(exc)})
        row_counts[filename] = counts
    dose = {}
    if not errors:
        for arm in plan['arms']:
            examples = [encoded[r['record_ids'][arm]] for r in plan['rounds']]
            dose[arm] = {'updates': len(examples), 'semantic_groups': len({r['group_id'] for r in plan['rounds']}),
                'input_tokens': sum(len(e['input_ids']) for e in examples),
                'rationale_targets': sum(e['segments'].count(1) for e in examples),
                'action_targets_including_eos': sum(e['segments'].count(2) for e in examples),
                'maximum_sequence_length': max(len(e['input_ids']) for e in examples)}
    body = {'status': 'PREFLIGHT_PASS' if not errors else 'PREFLIGHT_FAIL', 'student_tokenizer_measured': identity['kind']=='LOCAL_STUDENT_TOKENIZER',
        'tokenizer': {**identity, 'chat_template_sha256': digest(tok.chat_template), 'eos_token_id': tok.eos_token_id,
                      'fast': True, 'enable_thinking': False, 'add_special_tokens': False},
        'admission': admission, 'schedule': plan, 'max_length': max_length, 'per_row': row_counts, 'scheduled_dose': dose,
        'errors': errors, 'implementation_sha256': implementation_hashes(), 'weights_loaded': False,
        'gpu_jobs': 0, 'final_test_access': False, 'equal_raw_token_counts_claimed': False}
    report = {**body, 'sha256': digest(body)}
    if out is not None: write_json(out, report)
    return report, encoded


def verify_preflight(report, corpus_dir, identity):
    if digest({k:v for k,v in report.items() if k != 'sha256'}) != report['sha256']: raise ValueError('preflight receipt tampered')
    if report['status'] != 'PREFLIGHT_PASS' or not report['student_tokenizer_measured']: raise ValueError('real tokenizer preflight required')
    if report['implementation_sha256'] != implementation_hashes(): raise ValueError('source changed after preflight')
    if report['admission'] != load_corpus(corpus_dir)[1]: raise ValueError('corpus changed after preflight')
    for key, val in identity.items():
        if report['tokenizer'].get(key) != val: raise ValueError('tokenizer changed: '+key)
    plan = report['schedule']
    if plan != schedule(load_corpus(corpus_dir)[0], plan['arms'], plan['view'], plan['steps_per_arm'], plan['seed']):
        raise ValueError('schedule changed')
    return True
