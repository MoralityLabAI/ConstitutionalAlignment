"""Build the source-hashed aggregate report for a retained raw run (no raw text is written)."""
from __future__ import annotations
import json
from pathlib import Path
from . import analyze_posthoc as ap
from .plan import make_plan
from .posthoc import import_records, diagnose_tokens, load_terminal_map
from .run import write_json


def build(raw_jsonl, expected_sha, tmap_path, out_dir, raw_source):
    out = Path(out_dir)
    plan = make_plan('smoke')
    imp = import_records(plan, raw_jsonl, {'observed': 0, 'malformed': 65, 'unattempted': 127})
    tmap, doc = load_terminal_map(tmap_path)
    post = diagnose_tokens(plan, imp.pop('rows'), tmap)
    mine = ap.run(plan, raw_jsonl, tmap_path, expected_sha)
    # Cross-check the two independent implementations.
    for arm in ap.ARMS:
        a, b = mine['arms'][arm], post['token_strip_diagnostic']['arms'][arm]
        assert a['observed_joint_correct'] == b['joint_correct'], arm
        assert a['observed_action_correct'] == b['choice_correct'], arm
        assert a['observed_reason_correct'] == b['reason_correct'], arm
    here = Path(__file__).parent
    sources = {p: ap.sha_file(here / p) for p in ('analyze_posthoc.py', 'posthoc.py', 'report_posthoc.py', 'score.py', 'cases.py')}
    report = {'status': 'POSTHOC_REPORT_NOT_FROZEN_SCORE', 'raw_source': raw_source,
              'import_receipt': {k: imp[k] for k in ('status', 'plan_sha256', 'source_file_sha256', 'counts')},
              'frozen_strict_score': {'observed': 0, 'malformed': 65, 'unattempted_unknown': 127, 'strict_joint_correct': 0,
                                      'arms': {a: {k: post['original_strict_score']['arms'][a][k] for k in ('assigned', 'malformed', 'unknown', 'joint_correct')}
                                               for a in ap.ARMS}},
              'token_strip_audit': post['audit'], 'independent_analysis': mine, 'source_sha256': sources}
    write_json(out / 'analysis.json', report)
    write_json(out / 'posthoc_token_strip.json', post)
    return report
