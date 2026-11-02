"""Reproducible, independent CPU verification, with no endpoint or GPU access."""
from __future__ import annotations
from pathlib import Path
import hashlib
import json
import os
import re
import subprocess
import sys
from .plan import make_plan,verify_plan,public_cases,assignments
from .cases import canon,digest,FAMILIES,scripted
from .score import score,record_for
from .run import write_json

ROOT=Path(__file__).resolve().parents[2]
PACKAGE=Path(__file__).parent


def sha_file(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sources():
    paths=sorted(PACKAGE.rglob('*.py')) + [ROOT/'experiments/ontological_constitution_v4/semantics.py']
    paths=sorted(p for p in paths if '__pycache__' not in p.parts)
    return {p.relative_to(ROOT).as_posix():sha_file(p) for p in paths}


def verify(out):
    out=Path(out)
    if out.exists():raise FileExistsError('fresh output directory required')
    out.mkdir(parents=True)
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1')
    p=subprocess.run([sys.executable,'-m','unittest','discover','-s',
        'experiments/ontological_transfer_bench_v1/tests','-v'],cwd=ROOT,env=env,
        capture_output=True,text=True)
    log=p.stdout+p.stderr
    (out/'tests.log').write_text(log,encoding='utf-8')
    if p.returncode:raise RuntimeError('new benchmark CPU tests failed: tests.log')
    match=re.search(r'Ran (\d+) tests',log)
    if not match or 'skipped=' in log:raise RuntimeError('test suite did not pass with zero skips')
    smoke=make_plan('smoke');full=make_plan('full');verify_plan(smoke);verify_plan(full)
    write_json(out/'smoke_plan.json',smoke);write_json(out/'full_plan.json',full)
    examples=[{'family':b['family'],'case_id':b['cells'][0]['case_id'],
               'public':b['cells'][0]['public'],'answer':b['cells'][0]['answer'],
               'case_sha256':b['cells'][0]['sha256']}
              for b in full['blocks'] if b['motif_index']==0]
    write_json(out/'eight_worked_cases.json',examples)
    by_id={c['case_id']:c for b in smoke['blocks'] for c in b['cells']}
    all_records=[]
    for arm in smoke['arms']:
        for a in assignments(smoke,[arm]):
            all_records.append(record_for(smoke,a,scripted(by_id[a['case_id']]),model_id='synthetic_oracle'))
    perfect=score(smoke,all_records)
    if any(v['joint_correct']!=64 for v in perfect['arms'].values()):raise AssertionError('scripted oracle did not pass')
    diagnostics={}
    for policy in ('always_first','bonus_sensitive','training_sensitive','ontology_sensitive','reason_bypass','timeout','malformed'):
        rows=[]
        for a in assignments(smoke,['platonic_grounding']):
            try:output=scripted(by_id[a['case_id']],policy);err=None
            except TimeoutError as exc:output=None;err=str(exc)
            rows.append(record_for(smoke,a,output,error=err,model_id='synthetic:'+policy))
        x=score(smoke,rows,['platonic_grounding'])['arms']['platonic_grounding']
        diagnostics[policy]={'joint_correct':x['joint_correct'],'unknown':x['unknown'],'malformed':x['malformed']}
    if diagnostics['reason_bypass']['joint_correct']!=0 or diagnostics['timeout']['unknown']!=64:
        raise AssertionError('control behavior check failed')
    receipt={'status':'CPU_VERIFIED_NO_MODEL_CALLED','new_tests':int(match.group(1)),'skipped':0,
             'families':list(FAMILIES),'smoke_motifs':len(smoke['blocks']),
             'smoke_records_per_arm':smoke['records_per_arm'],
             'full_motifs':len(full['blocks']),'full_records_per_arm':full['records_per_arm'],
             'smoke_plan_sha256':smoke['sha256'],'full_plan_sha256':full['sha256'],
             'smoke_plan_file_sha256':sha_file(out/'smoke_plan.json'),
             'full_plan_file_sha256':sha_file(out/'full_plan.json'),
             'eight_worked_cases_sha256':sha_file(out/'eight_worked_cases.json'),
             'source_sha256':sources(),'test_log_sha256':sha_file(out/'tests.log'),
             'synthetic_oracle':{a:perfect['arms'][a]['joint_correct'] for a in smoke['arms']},
             'synthetic_failure_controls':diagnostics,
             'trained_checkpoint_loaded':False,'INTELLECT_3_called':False,'paid_compute':False,
             'seal_status':'PROSPECTIVE_DEVELOPMENT_UNSEALED','data_for_training':False}
    write_json(out/'cpu_receipt.json',receipt)
    return receipt
