"""CPU preflight and explicitly approved paired model integration."""
from pathlib import Path
import argparse
import json
from .admission import DEFAULT_ARMS


def main(argv=None):
    p=argparse.ArgumentParser();s=p.add_subparsers(dest='command',required=True)
    v=s.add_parser('verify');v.add_argument('--out',type=Path,required=True)
    q=s.add_parser('preflight');q.add_argument('--corpus',type=Path,required=True)
    q.add_argument('--tokenizer',type=Path,required=True);q.add_argument('--revision',required=True)
    q.add_argument('--out',type=Path,required=True);q.add_argument('--arms',nargs=2,default=list(DEFAULT_ARMS))
    q.add_argument('--view',choices=('derivation','exposition'),default='derivation')
    q.add_argument('--steps-per-arm',type=int,default=20);q.add_argument('--seed',type=int,default=11)
    q.add_argument('--max-length',type=int,default=4096)
    r=s.add_parser('pilot');r.add_argument('--corpus',type=Path,required=True)
    r.add_argument('--base',type=Path,required=True);r.add_argument('--revision',required=True)
    r.add_argument('--preflight',type=Path,required=True);r.add_argument('--out',type=Path,required=True)
    r.add_argument('--max-seconds',type=int,default=1080);r.add_argument('--eval-reserve',type=int,default=240)
    r.add_argument('--motifs',type=int,default=4);r.add_argument('--source-revision');r.add_argument('--approved',action='store_true')
    a=p.parse_args(argv)
    if a.command=='verify':
        from .verify import verify
        result=verify(a.out)
    elif a.command=='preflight':
        from .preflight import load_tokenizer,tokenizer_identity,preflight
        result,_=preflight(a.corpus,load_tokenizer(a.tokenizer),tokenizer_identity(a.tokenizer,a.revision),a.out,
            a.arms,a.steps_per_arm,a.seed,a.max_length,a.view)
    else:
        from .pilot import run_pilot
        result=run_pilot(a.corpus,a.base,a.revision,a.preflight,a.out,a.approved,
            a.max_seconds,a.eval_reserve,a.motifs,a.source_revision)
    print(json.dumps({k:result[k] for k in ('status','sha256','tests_total','steps_requested_per_arm','peak_cuda_allocated_bytes') if k in result},indent=2))
    if result['status'] in ('PREFLIGHT_FAIL','FAILED'):raise SystemExit(1)

if __name__=='__main__':main()
