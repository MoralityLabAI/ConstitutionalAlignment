"""Standalone CPU or approved-worker entry points for selective repair."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from ..data import FixtureTeacher
from .generator import produce_adaptive,export_v31
from .compare import compare


def main(argv=None):
    p=argparse.ArgumentParser(prog='python -m experiments.constitutional_reasoning_gym_v3.v31')
    subs=p.add_subparsers(dest='command',required=True)
    g=subs.add_parser('generate',help='adaptive reasoning with optional legacy import')
    g.add_argument('--backend',choices=('fixture','local'),default='fixture')
    g.add_argument('--model',type=Path);g.add_argument('--revision');g.add_argument('--approved',action='store_true')
    g.add_argument('--legacy',type=Path,help='read-only v3.0 generation directory with manifest and optional journal')
    g.add_argument('--out',type=Path,required=True);g.add_argument('--groups',type=int,default=32)
    g.add_argument('--seed',type=int,default=41);g.add_argument('--start-group',type=int,default=0)
    g.add_argument('--batch-size',type=int,default=4)
    g.add_argument('--max-seconds',type=int,default=900);g.add_argument('--max-output-tokens',type=int,default=500000)
    g.add_argument('--max-new-tokens',type=int,default=768);g.add_argument('--max-repairs',type=int,default=2)
    e=subs.add_parser('export',help='recheck polarity and create matched SFT variants')
    e.add_argument('--source',type=Path,required=True);e.add_argument('--out',type=Path,required=True)
    e.add_argument('--allow-fixture',action='store_true')
    c=subs.add_parser('compare',help='compare matched old v3.0 and new v3.1 acceptance')
    c.add_argument('--old',type=Path,required=True);c.add_argument('--new',type=Path,required=True)
    c.add_argument('--out',type=Path,required=True)
    a=p.parse_args(argv)
    if a.command=='generate':
        teacher=FixtureTeacher()
        if a.backend=='local':
            if not a.model or not a.revision:p.error('local requires a mounted model path and 40-hex revision')
            from ..runtime import HFTeacher
            teacher=HFTeacher(a.model,a.revision,a.approved,a.max_new_tokens,seed=a.seed)
        result=produce_adaptive(teacher,a.out,groups=a.groups,seed=a.seed,
                               batch_size=a.batch_size,seconds=a.max_seconds,
                               token_cap=a.max_output_tokens,max_new_tokens=a.max_new_tokens,
                               max_repairs=a.max_repairs,legacy_root=a.legacy,start_group=a.start_group)
    elif a.command=='export':result=export_v31(a.source,a.out,allow_fixture=a.allow_fixture)
    else:result=compare(a.old,a.new,a.out)
    print(json.dumps(result,sort_keys=True,indent=2))
    if a.command=='generate' and result['status']=='ABORTED':
        raise SystemExit(1)

if __name__=='__main__':main()
