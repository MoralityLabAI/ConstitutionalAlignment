"""Matched evidence-quality and stage-efficiency accounting for v3.0 vs v3.1.

This comparison conditions on observed cases. It is descriptive, not a
randomized estimate of downstream alignment or genuine teacher-token speed.
"""
from __future__ import annotations
from collections import Counter
from pathlib import Path
import json
from ..data import read_records
from ..core import case_from, write_json
from .audit import audit_candidate


def load_by_key(root):
    items={}
    for r in read_records(root):
        c=case_from(r['case'])
        if c.split!='train' or r['split']!='train':raise ValueError('evaluation rows cannot enter analysis')
        key=(c.case_id,r['frame'])
        if key in items:raise ValueError('duplicate source candidate')
        items[key]=r
    return items


def compare(old_root,new_root,out=None):
    old,new=load_by_key(old_root),load_by_key(new_root)
    keys=sorted(old.keys()&new.keys())
    if not keys:raise ValueError('no matched cases')
    def quality(rows):
        return {
            'legacy_oracle_accepted':sum(r['rewrite_audit']['accepted'] for r in rows),
            'v31_polarity_screen_accepted':sum(audit_candidate(case_from(r['case']),r['rewrite']['text'])['accepted'] for r in rows),
            'error_codes':dict(Counter(e for r in rows for e in audit_candidate(case_from(r['case']),r['rewrite']['text'])['errors'])),
            'rationale_words':sum(len(audit_candidate(case_from(r['case']),r['rewrite']['text'])['parsed'].get('rationale','').split())
                for r in rows if isinstance(audit_candidate(case_from(r['case']),r['rewrite']['text'])['parsed'],dict)),
        }
    a=[old[k] for k in keys];b=[new[k] for k in keys]
    manifest0=json.loads((Path(old_root)/'manifest.json').read_text());manifest1=json.loads((Path(new_root)/'manifest.json').read_text())
    r={'status':'DESCRIPTIVE_MATCHED_CPU_COMPARISON','matched_case_frame_records':len(keys),
       'old_complete_records':len(old),'new_complete_records':len(new),
       'old':quality(a),'new':quality(b),
       'old_candidate_stages_in_matched_rows':sum(len(x['revision_history']) for x in a),
       'new_candidate_stages_in_matched_rows':sum(len(x['v31_attempts'])+int(x['origin']=='V31_NEW') for x in b),
       'new_calls_to_teacher':manifest1['new_calls'],
       'source_legacy_calls_total':manifest0.get('calls_total'),
       'new_fully_paired_motifs':manifest1['paired_accepted_motifs'],
       'real_model_result':manifest1['evidence_class']=='MODEL_GENERATED',
       'observed_billed_GPU_time':None,
       'claim':'Observed acceptance, failure codes and generation calls. No causal training or mechanistic effect.',
       'old_status':manifest0['status'],'new_status':manifest1['status']}
    if out is not None:write_json(out,r)
    return r
