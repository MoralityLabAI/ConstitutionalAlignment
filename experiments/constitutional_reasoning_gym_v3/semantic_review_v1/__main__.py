"""CPU-only semantic QA entry point for v3.1 retained corpus."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from .review import build_audit,compile_reviews


def main(argv=None):
    ap=argparse.ArgumentParser(prog='python -m experiments.constitutional_reasoning_gym_v3.semantic_review_v1')
    cmds=ap.add_subparsers(dest='command',required=True)
    qa=cmds.add_parser('prepare',help='audit complete v3.1 corpus and prepare blinded review cards')
    qa.add_argument('--generation',type=Path,required=True)
    qa.add_argument('--sft',type=Path)
    qa.add_argument('--tokenizer',type=Path,help='already-mounted local tokenizer for exact unique-token totals')
    qa.add_argument('--out',type=Path,required=True)
    qa.add_argument('--seed',type=int,default=73)
    qa.add_argument('--allow-fixture',action='store_true',help='only for synthetic CPU tests')
    cs=cmds.add_parser('compile',help='compare two independently completed review sheets')
    cs.add_argument('--audit',type=Path,required=True)
    cs.add_argument('--review-a',type=Path,required=True)
    cs.add_argument('--review-b',type=Path,required=True)
    cs.add_argument('--out',type=Path,required=True)
    a=ap.parse_args(argv)
    if a.command=='prepare':
        result=build_audit(a.generation,a.out,a.sft,a.tokenizer,a.seed,a.allow_fixture)
        print(json.dumps({'status':result['status'],'records':result['review_queue_rows'],
           'paired_motifs':result['exportable_quartets'],
           'review_complete':result['review_completed'],'flags':result['text_review_flags']},indent=2))
    else:
        result=compile_reviews(a.audit,a.review_a,a.review_b,a.out)
        print(json.dumps({'status':result['status'],'records':result['reviewed_records'],
                          'disputes':result['records_for_adjudication']},indent=2))

if __name__=='__main__':main()
