"""Offline entry points. No paid inference, downloads or dataset uploads."""
import argparse
import json
from pathlib import Path


def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='cmd',required=True)
    b=sub.add_parser('build');b.add_argument('--out',type=Path,required=True);b.add_argument('--variants',type=int,default=2)
    v=sub.add_parser('verify');v.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    if a.cmd=='build':
        from .curriculum import export
        r=export(a.out,a.variants)
        print(json.dumps({k:r[k] for k in ('status','records','unique_semantic_groups')},indent=2))
    else:
        from .verify import verify_all
        r=verify_all(a.out)
        print(json.dumps({k:r[k] for k in ('status','tests_total','curriculum_records','GPU_jobs')},indent=2))

if __name__=='__main__':main()
