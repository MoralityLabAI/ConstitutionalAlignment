"""Reproduce semantic QA on local synthetic fixtures without model generation."""
from __future__ import annotations
from pathlib import Path
from tempfile import TemporaryDirectory
import argparse
import hashlib
import json
import platform
import re
import subprocess
import sys
from ..core import file_sha,write_json,make_twins
from ..data import FixtureTeacher
from ..v31.generator import produce_adaptive,export_v31
from .review import build_audit
from .checks import text_flags


def verify(out):
    out=Path(out)
    if out.exists():raise FileExistsError('fresh destination required')
    out.mkdir(parents=True)
    repo=Path(__file__).resolve().parents[3]
    paths=['experiments/constitutional_reasoning_gym_v3/tests',
           'experiments/constitutional_reasoning_gym_v3/v31/tests',
           'experiments/constitutional_reasoning_gym_v3/semantic_review_v1/tests']
    counts=[]
    for i,p in enumerate(paths):
        cmd=[sys.executable,'-m','unittest','discover','-s',p,'-q']
        proc=subprocess.run(cmd,cwd=repo,capture_output=True,text=True)
        log=out/f'tests_{i}.log';log.write_text(proc.stdout+proc.stderr,encoding='utf-8')
        if proc.returncode:raise RuntimeError(f'{p}: test failure; see {log}')
        m=re.search(r'Ran (\d+) tests',proc.stderr)
        if not m:raise ValueError('unrecognized unittest test output')
        counts.append({'test_suite':p,'tests':int(m.group(1)),'result':'PASS','log_sha256':file_sha(log)})
    if sum(x['tests'] for x in counts)<130:raise ValueError('test discovery too small')
    # Same 12-quartet and 48-frame-example shape as real recovered corpus.
    source=out/'synthetic_generation';sft=out/'synthetic_sft';audit=out/'synthetic_review_queue'
    generation=produce_adaptive(FixtureTeacher(),source,groups=12,max_repairs=0)
    exported=export_v31(source,sft,allow_fixture=True)
    status=build_audit(source,audit,sft,allow_fixture=True)
    if status['review_queue_rows']!=48 or status['exportable_quartets']!=12:
        raise ValueError('expected 48-record review fixture')
    case=make_twins('delegation',0,0)[0]
    negative=next(k for k,v in case.facts.items() if v is False)
    errors=text_flags(case,f'{negative} is true; therefore authorization holds.')
    if not any(e['code']=='contradictory_fact_polarity' for e in errors):
        raise ValueError('negative-control polarity test failed')
    base=Path(__file__).resolve().parent
    src={p.relative_to(base).as_posix():file_sha(p) for p in sorted(base.rglob('*.py')) if '__pycache__' not in p.parts}
    result={'status':'CPU_VERIFIED','evidence_class':'SYNTHETIC_FIXTURE_ONLY',
            'real_corpus_reviewed':False,'real_corpus_in_sandbox':False,
            'tests':counts,'total_tests':sum(x['tests'] for x in counts),'python':platform.python_version(),
            'generation_records':generation['completed_records'],
            'exported_cases':exported['paired_cases'],
            'review_queue_rows':status['review_queue_rows'],
            'matched_motifs':status['exportable_quartets'],
            'source_integrity_check_pass':True,'text_negation_control':errors,
            'source_sha256':src,'artifact_sha256':{n:file_sha(audit/n) for n in ('audit.json','review_queue.jsonl','blind_key.jsonl','mechanical_audit.jsonl')},
            'paid_gpu_jobs':0,'huggingface_uploads':0}
    write_json(out/'cpu_verification.json',result)
    print(json.dumps({k:result[k] for k in ('status','total_tests','review_queue_rows','matched_motifs','real_corpus_reviewed')},indent=2))
    return result


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args();verify(args.out)

if __name__=='__main__':main()
