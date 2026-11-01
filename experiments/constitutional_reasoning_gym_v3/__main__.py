"""Explicit, bounded entry points; CPU fixture is the default generation backend."""
from pathlib import Path
import argparse
import json
from .core import write_json


def main():
    p=argparse.ArgumentParser();s=p.add_subparsers(dest='cmd',required=True)
    g=s.add_parser('generate');g.add_argument('--out',type=Path,required=True)
    g.add_argument('--backend',choices=['fixture','local'],default='fixture')
    g.add_argument('--model');g.add_argument('--revision');g.add_argument('--approved',action='store_true')
    g.add_argument('--groups',type=int,default=32);g.add_argument('--seed',type=int,default=41);g.add_argument('--rounds',type=int,default=2)
    g.add_argument('--batch-size',type=int,default=4);g.add_argument('--max-seconds',type=int,default=1200)
    g.add_argument('--max-output-tokens',type=int,default=1000000);g.add_argument('--max-new-tokens',type=int,default=768)
    e=s.add_parser('export');e.add_argument('--source',type=Path,required=True);e.add_argument('--out',type=Path,required=True)
    e.add_argument('--allow-fixture',action='store_true')
    t=s.add_parser('train');t.add_argument('--model',required=True);t.add_argument('--revision',required=True)
    t.add_argument('--dataset',type=Path,required=True);t.add_argument('--out',type=Path,required=True)
    t.add_argument('--steps',type=int,default=200);t.add_argument('--seed',type=int,default=11)
    t.add_argument('--max-seconds',type=int,default=1200);t.add_argument('--approved',action='store_true')
    d=s.add_parser('demo');d.add_argument('--out',type=Path,required=True)
    h=s.add_parser('hub-bundle');h.add_argument('--source',type=Path,required=True);h.add_argument('--out',type=Path,required=True);h.add_argument('--generation',type=Path,required=True)
    u=s.add_parser('hub-upload');u.add_argument('--bundle',type=Path,required=True);u.add_argument('--repo-id',required=True);u.add_argument('--approved',action='store_true')
    v=s.add_parser('evaluate');v.add_argument('--model',required=True);v.add_argument('--revision',required=True)
    v.add_argument('--adapter-s1',required=True);v.add_argument('--adapter-o1',required=True)
    v.add_argument('--groups',type=int,default=8);v.add_argument('--out',type=Path,required=True)
    v.add_argument('--max-seconds',type=int,default=1200);v.add_argument('--approved',action='store_true')
    a=p.parse_args()
    if a.cmd=='generate':
        from .data import FixtureTeacher,produce
        teacher=FixtureTeacher()
        if a.backend=='local':
            if not a.model or not a.revision:p.error('local backend requires model and revision')
            from .runtime import HFTeacher
            teacher=HFTeacher(a.model,a.revision,a.approved,a.max_new_tokens,seed=a.seed)
        result=produce(teacher,a.out,a.groups,a.seed,a.batch_size,a.max_seconds,a.max_output_tokens,a.max_new_tokens,a.rounds)
    elif a.cmd=='export':
        from .data import export_sft
        result=export_sft(a.source,a.out,a.allow_fixture)
    elif a.cmd=='train':
        from .runtime import train_local
        result=train_local(a.model,a.revision,a.dataset,a.out,a.approved,a.steps,a.max_seconds,a.seed)
    elif a.cmd=='demo':
        from .data import FixtureTeacher,produce,export_sft
        from .evaluate import plan,run_scripted
        result={'generation':produce(FixtureTeacher(),a.out/'generation',groups=32),
                'sft':export_sft(a.out/'generation',a.out/'sft',allow_fixture=True),
                'evaluation':run_scripted(plan(),a.out/'evaluation')}
        write_json(a.out/'summary.json',result)
    elif a.cmd=='evaluate':
        from .runtime import HFActor
        from .evaluate import plan,run_agent
        actor=HFActor(a.model,a.revision,{'S1':a.adapter_s1,'O1':a.adapter_o1},a.approved)
        result=run_agent(plan(groups=a.groups),actor,a.out,a.max_seconds,actor.describe())
    elif a.cmd=='hub-bundle':
        from .publishing import prepare_bundle
        result=prepare_bundle(a.source,a.out,a.generation)
    else:
        from .publishing import publish_private
        result=publish_private(a.bundle,a.repo_id,a.approved)
    print(json.dumps(result,indent=2,sort_keys=True))

if __name__=='__main__':main()
