"""Produce a CPU receipt; independently identifies synthetic fixtures as such."""
from pathlib import Path
import argparse
import hashlib
import json
import platform
import subprocess
import sys
from .core import write_json,file_sha
from .data import FixtureTeacher,produce,export_sft
from .evaluate import plan,run_scripted


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    root=Path(__file__).resolve().parent;repo=root.parents[1]
    a.out.mkdir(parents=True,exist_ok=True)
    cmd=[sys.executable,'-m','unittest','discover','-s',str(root/'tests'),'-v']
    proc=subprocess.run(cmd,cwd=repo,text=True,capture_output=True)
    (a.out/'tests.log').write_text(proc.stdout+proc.stderr,encoding='utf-8')
    if proc.returncode:raise SystemExit(proc.returncode)
    generation=produce(FixtureTeacher(),a.out/'fixture_generation',groups=32,rounds=2)
    export=export_sft(a.out/'fixture_generation',a.out/'fixture_sft',allow_fixture=True)
    eval_result=run_scripted(plan(),a.out/'scripted_evaluation')
    source={x.relative_to(root).as_posix():file_sha(x) for x in sorted(root.rglob('*.py')) if '__pycache__' not in x.parts}
    try:
        import torch
        torch_version=torch.__version__
    except ImportError:torch_version=None
    receipt={'status':'CPU_VERIFIED','evidence_class':'SYNTHETIC_FIXTURES_AND_TORCH_OPERATOR_TESTS',
        'python':platform.python_version(),'tests_run':int(__import__('re').search(r'Ran (\d+) tests',proc.stderr).group(1)),
        'skipped_tests':0 if 'skipped=' not in proc.stderr else int(__import__('re').search(r'skipped=(\d+)',proc.stderr).group(1)),'torch':torch_version,'test_exit_code':proc.returncode,
        'test_log_sha256':file_sha(a.out/'tests.log'),'source_sha256':source,
        'generation':generation,'sft_export':export,'evaluation':eval_result,
        'pretrained_teacher_run':False,'SFT_model_training':False,'real_model_activations':False,
        'gymnasium_check':'NOT_RUN_IN_SANDBOX','huggingface_upload':False,
        'paid_compute_jobs':0,'final_test_access':False}
    write_json(a.out/'cpu_receipt.json',receipt)
    print(json.dumps({'status':receipt['status'],'calls':generation['calls_total'],
        'records':generation['completed_records'],'paired_cases':export['paired_cases'],
        'evaluation_records':eval_result['records']},indent=2))

if __name__=='__main__':main()
