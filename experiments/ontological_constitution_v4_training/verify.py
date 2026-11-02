"""Reproduce CPU admission, encoding, optimization and acquisition checks."""
from pathlib import Path
import json
import os
import platform
import re
import subprocess
import sys
import time
from experiments.ontological_constitution_v4.curriculum import export
from .contracts import load_corpus, make_schedule, measure, source_hashes, file_hash, write_json, ARMS
from .engine import train_pair,copy_initialization
from . import evaluation


def verify(out):
    out=Path(out)
    if out.exists():raise FileExistsError('fresh verification directory required')
    out.mkdir(parents=True)
    root=Path(__file__).resolve().parents[2]
    env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'}
    old=subprocess.run([sys.executable,'-m','experiments.ontological_constitution_v4','verify','--out',str(out/'upstream')],
                       cwd=root,capture_output=True,text=True,env=env)
    (out/'upstream.log').write_text(old.stdout+old.stderr,encoding='utf-8')
    if old.returncode:raise RuntimeError('upstream tests failed; see upstream.log')
    cmd=[sys.executable,'-m','unittest','discover','-s','experiments/ontological_constitution_v4_training/tests','-v']
    tests=subprocess.run(cmd,cwd=root,capture_output=True,text=True,env=env)
    text=tests.stdout+tests.stderr;(out/'integration_tests.log').write_text(text,encoding='utf-8')
    if tests.returncode:raise RuntimeError('integration tests failed; see integration_tests.log')
    count=int(re.search(r'Ran (\d+) tests',text).group(1))
    skip=re.search(r'skipped=(\d+)',text)
    if skip:raise RuntimeError('integration test skips require review')
    import torch
    from .tests.test_training import FixtureTokenizer,TinyPair
    torch.set_num_threads(1)
    export(out/'corpus');rows,manifest=load_corpus(out/'corpus');schedule=make_schedule(rows)
    write_json(out/'schedule.json',schedule)
    token=measure(FixtureTokenizer(),rows,schedule)
    token.update(tokenizer_evidence='DETERMINISTIC_TEST_TOKENIZER_NOT_QWEN',weights_loaded=False,GPU_jobs=0)
    write_json(out/'fixture_tokenizer.json',token)
    model=TinyPair();copy_initialization(model)
    training=train_pair(model,FixtureTokenizer(),schedule,out/'tiny_training',time.monotonic()+40)
    if training['status']!='COMPLETE':raise RuntimeError('tiny training incomplete')
    from experiments.ontological_constitution_v4.dilemmas import scripted
    def generate(arm,messages):return scripted('dutiful')(arm,messages[-1]['content'])
    score=evaluation.run(evaluation.make_plan(),generate,out/'synthetic_evaluation',1,clock=lambda:0)
    upstream=json.loads((out/'upstream/cpu_receipt.json').read_text())
    receipt={'status':'CPU_VERIFIED','evidence':'SOURCE_CHECKS_TINY_TORCH_OPTIMIZATION_AND_SCRIPTED_EVALUATION',
        'new_tests':count,'existing_tests':upstream['tests_total'],'tests_total':count+upstream['tests_total'],
        'skipped_total':0,'python':platform.python_version(),'torch':torch.__version__,
        'source_sha256':source_hashes(),'test_log_sha256':file_hash(out/'integration_tests.log'),
        'upstream_receipt_sha256':file_hash(out/'upstream/cpu_receipt.json'),
        'admitted_lesson_rows':len(rows),'conditions_measured_with_fixture':len(token['all_conditions']),
        'schedule_sha256':schedule['sha256'],'proof_groups_per_arm':20,'common_practice_per_arm':16,
        'tiny_steps_per_arm':training['steps'],'tiny_initial_adapters_identical':len(set(training['initial_adapter_sha256'].values()))==1,
        'tiny_adapters_changed':{a:training['initial_adapter_sha256'][a]!=training['final_adapter_sha256'][a] for a in ARMS},
        'synthetic_assigned_evaluation_records':score['records'],
        'native_student_tokenizer':'NOT_AVAILABLE_IN_SANDBOX','pretrained_training':'NOT_RUN',
        'HF_PEFT_CUDA_backend':'PREPARED_NOT_EXECUTED','GPU_jobs':0,'HF_uploads':0,'remote_commit':'NOT_PUSHED',
        'final_test_access':False,'legacy_gates_modified':False}
    write_json(out/'cpu_receipt.json',receipt)
    return receipt

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);args=p.parse_args()
    print(json.dumps(verify(args.out),indent=2))
