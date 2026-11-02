"""Regenerate independently scored CPU fixtures and source-hashed receipts."""
from __future__ import annotations
from pathlib import Path
import argparse
import hashlib
import json
import platform
import re
import subprocess
import sys
from ..core import canon,sha,file_sha,write_json
from ..data import FixtureTeacher,produce,export_sft
from .generator import produce_adaptive,export_v31,planned_jobs
from .compare import compare
from . import VERSION


class CanaryShape(FixtureTeacher):
    """Test double: seven final counterfactual failures in 24 case/frame rows."""
    def __init__(self):
        jobs=planned_jobs(6,41)
        self.bad={(jobs[i][0].case_id,jobs[i][1]) for i in (12,13,14,16,17,20,21)}
    def generate_many(self, requests):
        rows=super().generate_many(requests)
        for req,row in zip(requests,rows):
            if req['stage'] in ('draft','rewrite') and (req['case']['case_id'],req['frame']) in self.bad:
                parsed=json.loads(row['text']);parsed['counterfactual_choice']=parsed['choice']
                row['text']=canon(parsed)
        return rows


def run_tests(repo,log_dir):
    tests=[]
    targets=['experiments/constitutional_reasoning_gym_v3/tests',
             'experiments/constitutional_reasoning_gym_v3/v31/tests']
    for target in targets:
        cmd=[sys.executable,'-m','unittest','discover','-s',target,'-v']
        r=subprocess.run(cmd,cwd=repo,capture_output=True,text=True,timeout=180)
        name='v3-legacy' if 'v31' not in target else 'v31-adaptive'
        log=log_dir/(name+'.log')
        log.write_text(r.stdout+r.stderr,encoding='utf-8')
        count=re.search(r'Ran (\d+) tests',r.stderr)
        if r.returncode or not count or 'FAILED' in r.stderr or 'skipped=' in r.stderr:
            raise RuntimeError('test failure: '+name+'; see '+str(log))
        tests.append({'suite':name,'count':int(count.group(1)),'status':'PASS','skipped':0,
                      'log_sha256':file_sha(log),'command':' '.join(cmd)})
    return tests


def verify(out):
    out=Path(out)
    if out.exists():raise FileExistsError('verification output must be new')
    out.mkdir(parents=True)
    package=Path(__file__).resolve().parent
    repo=package.parents[2]
    tests=run_tests(repo,out)
    old=produce(FixtureTeacher(),out/'v30_five_stage',groups=8,rounds=2)
    new=produce_adaptive(FixtureTeacher(),out/'v31_adaptive',groups=8)
    sft=export_v31(out/'v31_adaptive',out/'v31_sft',allow_fixture=True)
    matched=compare(out/'v30_five_stage',out/'v31_adaptive',out/'adaptive_vs_five_stage.json')
    if old['new_calls']!=160 or new['new_calls']!=32 or new['paired_accepted_motifs']!=8:
        raise AssertionError('fixture expected stage-count result changed')
    simulated_old=produce(CanaryShape(),out/'simulated_canary_v30',groups=6,rounds=2)
    simulated_old_sft=export_sft(out/'simulated_canary_v30',out/'simulated_old_sft',allow_fixture=True)
    simulated_new=produce_adaptive(FixtureTeacher(),out/'simulated_canary_v31',groups=6,
                                   legacy_root=out/'simulated_canary_v30')
    simulated_new_sft=export_v31(out/'simulated_canary_v31',out/'simulated_new_sft',True)
    simulated=compare(out/'simulated_canary_v30',out/'simulated_canary_v31',out/'simulated_canary_comparison.json')
    if not (simulated_old['accepted_rewrites']==17 and
            simulated_old_sft['accepted_semantic_motifs']==3 and
            simulated_new['accepted_rewrites']==24 and simulated_new['paired_accepted_motifs']==6 and
            simulated_new['new_calls']==7):
        raise AssertionError('simulated canary recovery assumptions changed')
    sources={}
    for p in sorted(package.rglob('*')):
        if p.is_file() and ('__pycache__' not in p.parts) and p.suffix in ('.py','.md','.sh','.json'):
            if 'results' not in p.parts:
                sources[p.relative_to(repo).as_posix()]=file_sha(p)
    for other in (repo/'experiments/constitutional_reasoning_gym_v3/core.py',
                  repo/'experiments/constitutional_reasoning_gym_v3/data.py',
                  repo/'experiments/constitutional_reasoning_gym_v3/runtime.py'):
        sources[other.relative_to(repo).as_posix()]=file_sha(other)
    artifacts={}
    for label,p in (
        ('old_fixture_manifest',out/'v30_five_stage/manifest.json'),
        ('adaptive_fixture_manifest',out/'v31_adaptive/manifest.json'),
        ('adaptive_vs_five_stage',out/'adaptive_vs_five_stage.json'),
        ('simulated_legacy_manifest',out/'simulated_canary_v30/manifest.json'),
        ('simulated_repair_manifest',out/'simulated_canary_v31/manifest.json'),
        ('simulated_canary_comparison',out/'simulated_canary_comparison.json'),
        ('SFT_manifest',out/'v31_sft/manifest.json'),
        ('repaired_SFT_manifest',out/'simulated_new_sft/manifest.json'),
    ):
        artifacts[label]={'path':p.relative_to(out).as_posix(),'sha256':file_sha(p)}
    receipt={'status':'CPU_VERIFIED','version':VERSION,
             'evidence_class':'SYNTHETIC_FIXTURE_ONLY','python':platform.python_version(),
             'tests':tests,'tests_total':sum(t['count'] for t in tests),'tests_skipped':0,
             'source_sha256':sources,'artifacts':artifacts,
             'ordinary_fixture':{'v30_teacher_stage_calls':old['new_calls'],
                                 'v31_teacher_stage_calls':new['new_calls'],
                                 'matched_rows':matched['matched_case_frame_records'],
                                 'complete_motifs':new['paired_accepted_motifs'],
                                 'v31_SFT_rows_per_arm':{k:v['rows'] for k,v in sft['arms'].items()},
                                 'stage_calls_ratio_old_to_new':old['new_calls']/new['new_calls']},
             'simulated_canary_shape':{'old_completed':simulated_old['completed_records'],
                     'old_accepted_final':simulated_old['accepted_rewrites'],
                     'old_complete_motifs':simulated_old_sft['accepted_semantic_motifs'],
                     'new_accepted':simulated_new['accepted_rewrites'],
                     'new_complete_motifs':simulated_new['paired_accepted_motifs'],
                     'new_repair_calls':simulated_new['new_calls'],
                     'new_SFT_rows_per_arm':{k:v['rows'] for k,v in simulated_new_sft['arms'].items()}},
             'actual_Silico_canary_access':False,
             'trained_teacher_calls':0,'model_training':False,'HuggingFace_upload':False,
             'GPU_leases_started':0,'tokenizer_measured_accepted_tokens':None,
             'measured_GPU_cost':None,'final_test_access':False,
             'human_semantic_review_required':True,
             'result_claim':'Deterministic CPU pipeline and fault-injected analogue only; no real-model data improvement demonstrated'}
    write_json(out/'verification.json',receipt)
    return receipt


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    r=verify(a.out)
    print(json.dumps({'status':r['status'],'tests':r['tests_total'],
                      'stage_ratio':r['ordinary_fixture']['stage_calls_ratio_old_to_new'],
                      'simulated_repair_calls':r['simulated_canary_shape']['new_repair_calls']},indent=2))

if __name__=='__main__':main()
