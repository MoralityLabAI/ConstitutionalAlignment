"""Separate exploratory diagnostic of retained raw Qwen outputs.

The original strict records and results are kept verbatim. For malformed records
only, consider removing ONE exact trailing chat-end marker from the raw text.
The diagnostic never changes published score, splits, or original provenance.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from .run import extract_final, read_records, write_json
from .score import record_for, score
from .plan import verify_plan, assignments
from .cases import parse

END_MARKER = '<|im_end|>'


def diagnose(plan, records):
    verify_plan(plan)
    rows=list(records)
    original=score(plan,rows)
    lookup={a['assignment_id']:a for a in assignments(plan)}
    diagnostic=[]
    flags={'all_submitted':len(rows),'malformed_original':0,'terminal_marker_present':0,
           'valid_after_one_terminal_marker':0,'still_invalid_after_marker':0,
           'not_eligible_for_recovery':0}
    for row in rows:
        a=lookup[row['assignment_id']]
        raw=row.get('raw')
        candidate=raw
        if row['status']=='malformed':
            flags['malformed_original']+=1
            full=row.get('metadata',{}).get('raw_model_text')
            # A full, original text witness is required for post-hoc extraction.
            if not isinstance(full,str) or raw!=extract_final(full) or not raw.endswith(END_MARKER):
                flags['not_eligible_for_recovery']+=1
            else:
                flags['terminal_marker_present']+=1
                candidate=raw[:-len(END_MARKER)].strip()
                try:
                    parse(candidate)
                except (TypeError,ValueError):
                    flags['still_invalid_after_marker']+=1
                    candidate=raw
                else:
                    flags['valid_after_one_terminal_marker']+=1
        diagnostic.append(record_for(plan,a,candidate,error=row.get('error'),
             metadata={'original_record_sha256':row['record_sha256'],
                       'diagnostic_only':True},model_id=row.get('model_id')))
    rescored=score(plan,diagnostic)
    return {'status':'POST_HOC_FORMAT_DIAGNOSTIC_NOT_FROZEN_SCORE',
            'original_plan_sha256':plan['sha256'],
            'original_strict_score':original,
            'one_terminal_marker_diagnostic':rescored,
            'audit':flags,'modifies_original_records':False,
            'claim':'Exploratory exact-suffix post-hoc diagnosis, no prespecified success estimate.'}


THINK_END = '</think>'


def load_terminal_map(path):
    """Read a map written by `terminal-map` from a real tokenizer; verify its shape."""
    doc = json.loads(Path(path).read_text(encoding='utf-8'))
    raw = doc.get('map')
    if not isinstance(raw, dict) or not raw:raise ValueError('terminal map missing')
    tmap = {}
    for key, name in raw.items():
        if not key.isdigit() or not isinstance(name, str):raise ValueError('terminal map entry')
        tmap[int(key)] = name
    if not any(n != THINK_END for n in tmap.values()):raise ValueError('no turn-ending token in map')
    return tmap, doc


def _strip_terminal(text, ids, tmap):
    """Remove only the trailing run of turn-ending token IDs, and exactly their markers from the text."""
    turn = {i: n for i, n in tmap.items() if n != THINK_END}
    tail = []
    for t in reversed(ids):
        if t not in turn:break
        tail.append(t)
    if not tail:return None, []
    stripped = text
    for t in tail:   # tail is last-to-first, matching the text's end
        if not stripped.endswith(turn[t]):return None, tail
        stripped = stripped[:-len(turn[t])]
    return stripped, list(reversed(tail))


def diagnose_tokens(plan, records, tmap):
    """Token-ID post-hoc rescoring. Raw text and IDs stay in each diagnostic record."""
    verify_plan(plan)
    rows = list(records)
    original = score(plan, rows)
    lookup = {a['assignment_id']: a for a in assignments(plan)}
    out = []
    audit = {'submitted': len(rows), 'malformed_original': 0, 'no_token_witness': 0, 'no_terminal_token': 0,
             'text_does_not_end_with_marker': 0, 'recovered_valid': 0, 'still_invalid_after_strip': 0,
             'stripped_token_ids': {}}
    for row in rows:
        a = lookup[row['assignment_id']]
        candidate = row.get('raw')
        meta = row.get('metadata', {})
        if row['status'] == 'malformed':
            audit['malformed_original'] += 1
            text, ids = meta.get('raw_model_text'), meta.get('raw_generated_token_ids')
            if not isinstance(text, str) or not isinstance(ids, list) or not all(type(i) is int for i in ids):
                audit['no_token_witness'] += 1
            else:
                stripped, tail = _strip_terminal(text, ids, tmap)
                if stripped is None and not tail:audit['no_terminal_token'] += 1
                elif stripped is None:audit['text_does_not_end_with_marker'] += 1
                else:
                    cand = extract_final(stripped)
                    try:parse(cand)
                    except (TypeError, ValueError):audit['still_invalid_after_strip'] += 1
                    else:
                        candidate = cand;audit['recovered_valid'] += 1
                        key = ','.join(str(t) for t in tail)
                        audit['stripped_token_ids'][key] = audit['stripped_token_ids'].get(key, 0) + 1
        out.append(record_for(plan, a, candidate, error=row.get('error'), model_id=row.get('model_id'),
                              metadata={'original_record_sha256': row['record_sha256'], 'diagnostic_only': True,
                                        'raw_model_text': meta.get('raw_model_text'),
                                        'raw_generated_token_ids': meta.get('raw_generated_token_ids')}))
    rescored = score(plan, out)
    return {'status': 'POST_HOC_TOKEN_DIAGNOSTIC_NOT_FROZEN_SCORE', 'original_plan_sha256': plan['sha256'],
            'original_strict_score': original, 'token_strip_diagnostic': rescored, 'audit': audit,
            'accuracy_by_arm': {arm: {k: v[k] for k in ('assigned', 'unknown', 'malformed', 'choice_correct', 'choice_accuracy_bounds',
                                                        'reason_correct', 'reason_accuracy_bounds', 'joint_correct', 'joint_accuracy_bounds')}
                                for arm, v in rescored['arms'].items()},
            'modifies_original_records': False,
            'claim': 'Exploratory: only verified terminal token IDs removed; unknown assignments bound the accuracy, never imputed.'}


def import_records(plan, src, expect=None):
    """Validate retained raw responses from a copied artifact directory or JSONL file.

    Every row is checked by the scorer (plan hash, roster, prompt, record hash, parse
    consistency). Nothing is synthesized: absent assignments stay unknown.
    """
    verify_plan(plan)
    src = Path(src)
    files = [src] if src.is_file() else sorted(src.rglob('*.jsonl')) if src.is_dir() else []
    if not files:
        raise FileNotFoundError('no *.jsonl response file found; required: the hf-group --out JSONL of the original run')
    rows, hashes = [], {}
    for f in files:
        hashes[str(f.name)] = hashlib.sha256(f.read_bytes()).hexdigest()
        rows += read_records(f)
    strict = score(plan, rows)
    counts = {'records': len(rows),
              'observed': sum(r['status'] == 'observed' for r in rows),
              'malformed': sum(r['status'] == 'malformed' for r in rows),
              'unknown_recorded': sum(r['status'] == 'unknown' for r in rows),
              'unattempted': strict['records_assigned'] - len(rows),
              'strict_joint_correct': sum(v['joint_correct'] for v in strict['arms'].values())}
    if expect is not None and {k: counts[k] for k in expect} != expect:
        raise ValueError('imported responses do not match the preserved strict score: %r vs %r' % (counts, expect))
    return {'status': 'IMPORTED_VERIFIED', 'plan_sha256': plan['sha256'], 'source_file_sha256': hashes,
            'counts': counts, 'strict_score': strict, 'rows': rows}
