"""Offline build/preflight; the pilot requires a separately approved GPU lease."""
import argparse
import json
from pathlib import Path


def main():
    p=argparse.ArgumentParser();s=p.add_subparsers(dest='cmd',required=True)
    b=s.add_parser('prepare');b.add_argument('--out',type=Path,required=True)
    v=s.add_parser('verify');v.add_argument('--out',type=Path,required=True)
    f=s.add_parser('preflight');f.add_argument('--corpus',type=Path,required=True)
    f.add_argument('--tokenizer',type=Path,required=True);f.add_argument('--revision',required=True)
    f.add_argument('--out',type=Path,required=True)
    r=s.add_parser('pilot');r.add_argument('--corpus',type=Path,required=True)
    r.add_argument('--base',type=Path,required=True);r.add_argument('--revision',required=True)
    r.add_argument('--preflight',type=Path,required=True);r.add_argument('--out',type=Path,required=True)
    r.add_argument('--approved',action='store_true');r.add_argument('--max-seconds',type=int,default=1160)
    a=p.parse_args()
    if a.cmd=='prepare':
        from experiments.ontological_constitution_v4.curriculum import export
        from .contracts import load_corpus,make_schedule,write_json
        if a.out.exists():raise FileExistsError('fresh directory required')
        a.out.mkdir(parents=True)
        export(a.out/'corpus');rows,_=load_corpus(a.out/'corpus')
        plan=make_schedule(rows);write_json(a.out/'schedule.json',plan)
        result={'status':'CPU_PREPARED','rows':len(rows),'schedule_sha256':plan['sha256'],'updates_per_arm':36,'weights_loaded':False}
    elif a.cmd=='verify':
        from .verify import verify
        result=verify(a.out)
    elif a.cmd=='preflight':
        from .contracts import preflight
        result=preflight(a.corpus,a.tokenizer,a.revision,a.out)
    else:
        from .engine import pilot
        result=pilot(a.base,a.revision,a.corpus,a.preflight,a.out,a.approved,a.max_seconds)
    print(json.dumps(result,indent=2,sort_keys=True))
    if result.get('status') in ('FAILED','TOKENIZER_FAIL'):raise SystemExit(1)

if __name__=='__main__':main()
