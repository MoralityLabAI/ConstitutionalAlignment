"""Separate exploratory diagnostic of retained raw Qwen outputs.

The original strict records and results are kept verbatim. For malformed records
only, consider removing ONE exact trailing chat-end marker from the raw text.
The diagnostic never changes published score, splits, or original provenance.
"""
from __future__ import annotations
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
