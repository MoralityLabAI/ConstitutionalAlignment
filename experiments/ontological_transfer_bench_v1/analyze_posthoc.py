"""Independent re-analysis of retained raw responses; writes aggregate findings only.

Deliberately does not call posthoc.py or score.py for its numbers: it re-reads the
raw JSONL, strips trailing terminal token IDs itself, parses with its own strict
validator, and joins to the plan's answer key. posthoc.py is used only as a
cross-check in the tests/report. Raw text and prompts are never written out.
"""
from __future__ import annotations
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

ARMS = ('base', 'formal_control', 'platonic_grounding')


def strict_json(text):
    """Exactly one object with integer keys choice and reason_code in 0..3; None otherwise."""
    def pairs(items):
        out = {}
        for k, v in items:
            if k in out:raise ValueError('duplicate key')
            out[k] = v
        return out
    try:
        o = json.loads(text.strip(), object_pairs_hook=pairs)
    except (ValueError, AttributeError):
        return None
    if type(o) is not dict or set(o) != {'choice', 'reason_code'}:return None
    if any(type(o[k]) is not int or not 0 <= o[k] < 4 for k in o):return None
    return o


FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.S)


def lenient_json(text):
    """Exploratory only: the last fenced {...} block, validated by the same strict rules."""
    blocks = FENCE.findall(text)
    return strict_json(blocks[-1]) if blocks else None


def final_text(raw_text, ids, tmap):
    """Drop the trailing run of turn-ending IDs and their markers; keep text after the last </think>."""
    turn = {i: n for i, n in tmap.items() if n != '</think>'}
    text = raw_text;tail = 0
    for t in reversed(ids):
        if t not in turn or not text.endswith(turn[t]):break
        text = text[:-len(turn[t])];tail += 1
    if '</think>' in text:text = text.rsplit('</think>', 1)[-1]
    return text.strip(), tail


def wilson(k, n, z=1.96):
    if n == 0:return None
    p = k / n;d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d;h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(max(0, c - h), 3), round(min(1, c + h), 3)]


def analyze(plan, rows, tmap):
    key = {c['case_id']: c for b in plan['blocks'] for c in b['cells']}
    per_case = defaultdict(dict)
    arms = {}
    for arm in ARMS:
        mine = [r for r in rows if r['arm'] == arm]
        total_assigned = sum(1 for b in plan['blocks'] for _ in b['cells'])
        strict_ok = sum(strict_json(r['raw']) is not None for r in mine)
        rec = valid = act = rea = joint = no_term = invalid = 0
        len_valid = len_joint = len_act = 0;by_factor = defaultdict(Counter)
        stop_kinds = Counter();fam = defaultdict(Counter)
        for r in mine:
            m = r['metadata'];c = key[r['case_id']]
            text, tail = final_text(m['raw_model_text'], m['raw_generated_token_ids'], tmap)
            if tail == 0:no_term += 1
            p = strict_json(text)
            f = fam[c['family']];f['attempted'] += 1
            lp = p if p is not None else lenient_json(text)
            if lp is not None:
                len_valid += 1;len_act += lp['choice'] == c['answer']['choice']
                len_joint += lp['choice'] == c['answer']['choice'] and lp['reason_code'] == c['answer']['reason_code']
            if p is None:
                invalid += 1;f['invalid'] += 1
                per_case[r['case_id']][arm] = None
                continue
            valid += 1;f['valid'] += 1
            a = p['choice'] == c['answer']['choice'];b = p['reason_code'] == c['answer']['reason_code']
            act += a;rea += b;joint += a and b
            f['action'] += a;f['reason'] += b;f['joint'] += a and b
            for fac, val in c['flags'].items():
                g = by_factor[f'{fac}={int(val)}'];g['valid'] += 1;g['joint'] += a and b
            per_case[r['case_id']][arm] = {'choice': p['choice'], 'reason_code': p['reason_code'], 'action_ok': a, 'reason_ok': b}
        n = len(mine)
        arms[arm] = {'assigned': total_assigned, 'attempted': n, 'unattempted_unknown': total_assigned - n,
                     'strict_valid_original': strict_ok, 'no_terminal_token_in_output': no_term,
                     'recovered_valid_json': valid, 'invalid_after_strip': invalid,
                     'observed_action_correct': act, 'observed_reason_correct': rea, 'observed_joint_correct': joint,
                     'observed_only': {'valid_json_rate': [valid, n], 'action_acc_of_attempted': [act, n],
                                       'reason_acc_of_attempted': [rea, n], 'joint_acc_of_attempted': [joint, n],
                                       'action_acc_of_valid': [act, valid], 'joint_acc_of_valid': [joint, valid],
                                       'joint_wilson95_of_attempted': wilson(joint, n)},
                     'bounds_over_all_assigned': {
                         'action': [act, act + total_assigned - n], 'reason': [rea, rea + total_assigned - n],
                         'joint': [joint, joint + total_assigned - n], 'denominator': total_assigned},
                     'by_family': {k: dict(v) for k, v in sorted(fam.items())},
                     'by_factor_value_valid_only': {k: dict(v) for k, v in sorted(by_factor.items())},
                     'lenient_fence_diagnostic': {'valid': len_valid, 'action_correct': len_act, 'joint_correct': len_joint,
                                                  'attempted': n, 'note': 'exploratory; contract says fences are malformed'}}
    return arms, per_case, key


def paired(per_case, key, a, b, field):
    """Contingency on cases both arms attempted AND produced valid JSON."""
    both = fa = fb = neither = 0;disagreements = [];attempted_both = valid_both = 0
    for cid, d in per_case.items():
        if a in d and b in d:attempted_both += 1
        else:continue
        if d[a] is None or d[b] is None:continue
        valid_both += 1
        if field == 'joint':
            x, y = d[a]['action_ok'] and d[a]['reason_ok'], d[b]['action_ok'] and d[b]['reason_ok']
        else:
            x, y = d[a][field], d[b][field]
        both += x and y;fa += x and not y;fb += y and not x;neither += (not x) and (not y)
        if x != y:
            c = key[cid]
            disagreements.append({'case_id': cid, 'family': c['family'], 'flags': c['flags'],
                                  'answer': c['answer'], a: {k: d[a][k] for k in ('choice', 'reason_code')},
                                  b: {k: d[b][k] for k in ('choice', 'reason_code')}})
    # exact two-sided McNemar from discordant counts
    n = fa + fb
    p = 1.0 if n == 0 else min(1.0, 2 * sum(math.comb(n, i) for i in range(0, min(fa, fb) + 1)) / 2 ** n)
    return {'arms': [a, b], 'field': field, 'cases_attempted_by_both': attempted_both, 'cases_valid_in_both': valid_both,
            'both_correct': both, f'{a}_only': fa, f'{b}_only': fb, 'neither': neither,
            'mcnemar_exact_p': round(p, 4), 'disagreements': disagreements}


def cue_blindness(per_case, key, arm):
    """Within a family, do identical menus get identical answers across truth values (observed cells only)?"""
    out = {}
    by = defaultdict(list)
    for cid, d in per_case.items():
        if arm in d and d[arm] is not None:
            c = key[cid];by[c['family']].append((c['flags']['truth'], (d[arm]['choice'], d[arm]['reason_code']), c['answer']['choice']))
    for fam, items in sorted(by.items()):
        truths = {t for t, _, _ in items}
        outputs = {o for _, o, _ in items}
        out[fam] = {'observed_cells': len(items), 'truth_values_seen': sorted(truths), 'distinct_outputs': len(outputs),
                    'distinct_correct_choices': len({a for _, _, a in items})}
    return out


def sha_file(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def run(plan, records_path, tmap_path, expected_sha=None):
    got = sha_file(records_path)
    if expected_sha and got != expected_sha:raise ValueError('raw JSONL hash mismatch')
    rows = [json.loads(l) for l in Path(records_path).read_text(encoding='utf-8').splitlines() if l.strip()]
    tdoc = json.loads(Path(tmap_path).read_text(encoding='utf-8'))
    tmap = {int(k): v for k, v in tdoc['map'].items()}
    arms, per_case, key = analyze(plan, rows, tmap)
    pairs = {f'{a}_vs_{b}': {fld: paired(per_case, key, a, b, fld) for fld in ('action_ok', 'reason_ok', 'joint')}
             for a, b in (('formal_control', 'platonic_grounding'), ('base', 'formal_control'), ('base', 'platonic_grounding'))}
    # action_ok / reason_ok keys are per-record booleans already
    return {'status': 'INDEPENDENT_POSTHOC_ANALYSIS_NOT_FROZEN_SCORE', 'plan_sha256': plan['sha256'],
            'raw_records_sha256': got, 'raw_records': len(rows), 'terminal_map_label': tdoc.get('tokenizer_label'),
            'terminal_map_sha256': sha_file(tmap_path), 'arms': arms, 'paired': pairs,
            'cue_blindness_observed': {arm: cue_blindness(per_case, key, arm) for arm in ARMS},
            'cases_by_arm_overlap': {arm: sum(arm in d for d in per_case.values()) for arm in ARMS}}
