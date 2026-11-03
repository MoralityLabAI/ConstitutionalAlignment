"""CPU-first creation, scoring and optional explicit model inference."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from .plan import make_plan,verify_plan,public_cases
from .cases import canon
from .run import write_json,read_records,run_fixture,run_endpoint,run_hf,run_hf_group,preflight_hf_tokenizer
from .score import score


def main(argv=None):
    p=argparse.ArgumentParser(prog='python -m experiments.ontological_transfer_bench_v1')
    sub=p.add_subparsers(dest='cmd',required=True)
    b=sub.add_parser('build')
    b.add_argument('--mode',choices=('smoke','paired_smoke','paired_balanced','full'),default='smoke');b.add_argument('--motifs-per-family',type=int)
    b.add_argument('--seed',type=int,default=20261102);b.add_argument('--out',type=Path,required=True)
    v=sub.add_parser('verify');v.add_argument('--out',type=Path,required=True)
    diag=sub.add_parser('posthoc');diag.add_argument('--plan',type=Path,required=True);diag.add_argument('--records',type=Path,nargs='+',required=True);diag.add_argument('--out',type=Path,required=True);diag.add_argument('--terminal-map',type=Path)
    au=sub.add_parser('audit');au.add_argument('--plan',type=Path,required=True);au.add_argument('--out',type=Path,required=True)
    tm=sub.add_parser('terminal-map');tm.add_argument('--tokenizer-dir',type=Path,required=True);tm.add_argument('--out',type=Path,required=True)
    tm.add_argument('--label',required=True,help='tokenizer identity claim, e.g. repo id and revision')
    im=sub.add_parser('import-records');im.add_argument('--plan',type=Path,required=True);im.add_argument('--src',type=Path,required=True)
    im.add_argument('--out-dir',type=Path,required=True);im.add_argument('--expect-original-strict',action='store_true')
    es=sub.add_parser('estimate');es.add_argument('--plan',type=Path,required=True);es.add_argument('--protocol',required=True)
    es.add_argument('--tokens-per-second',type=float,required=True);es.add_argument('--load-minutes',type=float,default=10)
    e=sub.add_parser('score');e.add_argument('--plan',type=Path,required=True);e.add_argument('--records',type=Path,nargs='+',required=True);e.add_argument('--out',type=Path,required=True)
    f=sub.add_parser('fixture');f.add_argument('--plan',type=Path,required=True);f.add_argument('--out',type=Path,required=True)
    f.add_argument('--arm',default='platonic_grounding');f.add_argument('--policy',default='oracle')
    pre=sub.add_parser('tokenizer-preflight');pre.add_argument('--plan',type=Path,required=True);pre.add_argument('--out',type=Path,required=True)
    pre.add_argument('--base',required=True);pre.add_argument('--revision',required=True);pre.add_argument('--thinking',action='store_true')
    h=sub.add_parser('hf');h.add_argument('--plan',type=Path,required=True);h.add_argument('--out',type=Path,required=True)
    h.add_argument('--arm',required=True);h.add_argument('--base',required=True);h.add_argument('--revision',required=True)
    h.add_argument('--adapter');h.add_argument('--approved',action='store_true');h.add_argument('--max-requests',type=int,default=64)
    h.add_argument('--max-new-tokens',type=int,default=2048);h.add_argument('--no-thinking',action='store_true')
    all_hf=sub.add_parser('hf-group');all_hf.add_argument('--plan',type=Path,required=True);all_hf.add_argument('--out',type=Path,required=True)
    all_hf.add_argument('--base',required=True);all_hf.add_argument('--revision',required=True)
    all_hf.add_argument('--formal-adapter',required=True);all_hf.add_argument('--platonic-adapter',required=True)
    all_hf.add_argument('--approved',action='store_true');all_hf.add_argument('--max-assignments',type=int,required=True)
    all_hf.add_argument('--max-new-tokens',type=int,default=1024);all_hf.add_argument('--max-wall-seconds',type=int,default=900)
    all_hf.add_argument('--thinking',action='store_true');all_hf.add_argument('--protocol');all_hf.add_argument('--arms',nargs='+')
    m=sub.add_parser('endpoint');m.add_argument('--plan',type=Path,required=True);m.add_argument('--out',type=Path,required=True)
    m.add_argument('--arm',required=True);m.add_argument('--model-id',required=True);m.add_argument('--url',required=True)
    m.add_argument('--api-key-env',default='BENCH_API_KEY');m.add_argument('--approved',action='store_true')
    m.add_argument('--max-requests',type=int,required=True);m.add_argument('--total-output-cap',type=int,required=True)
    m.add_argument('--max-new-tokens',type=int,default=2048);m.add_argument('--timeout',type=int,default=120)
    m.add_argument('--reasoning-effort',choices=('low','medium','high'))
    args=p.parse_args(argv)
    if args.cmd=='terminal-map':
        from transformers import AutoTokenizer
        from .generation import terminal_map
        tok=AutoTokenizer.from_pretrained(args.tokenizer_dir,local_files_only=True)
        result={'tokenizer_label':args.label,'map':{str(k):v for k,v in terminal_map(tok).items()},
                'eos_token_id':tok.eos_token_id}
        write_json(args.out,result);print(json.dumps(result,indent=2,sort_keys=True));return result
    if args.cmd=='build':
        plan=make_plan(args.mode,args.motifs_per_family,args.seed)
        if args.out.exists():raise FileExistsError('fresh benchmark export required')
        args.out.mkdir(parents=True)
        write_json(args.out/'plan.json',plan)
        with (args.out/'public_cases.jsonl').open('x',encoding='utf-8') as f:
            for r in public_cases(plan):f.write(canon(r)+'\n')
        result={'status':'GENERATED_PROSPECTIVE_DEV_NOT_SEALED','sha256':plan['sha256'],
                'families':8,'motifs':len(plan['blocks']),'records_per_arm':plan['records_per_arm']}
        write_json(args.out/'manifest.json',result)
    elif args.cmd=='verify':
        from .verify import verify
        result=verify(args.out)
    else:
        plan=json.loads(args.plan.read_text(encoding='utf-8'));verify_plan(plan)
        if args.cmd=='tokenizer-preflight':result=preflight_hf_tokenizer(plan,base_model=args.base,model_revision=args.revision,out=args.out,thinking=args.thinking)
        elif args.cmd=='audit':
            from .audit import audit
            result=audit(plan);write_json(args.out,result)
        elif args.cmd=='estimate':
            from .generation import budget_estimate
            from .plan import assignments
            calls={}
            for a in assignments(plan,['base','formal_control','platonic_grounding']):calls[a['arm']]=calls.get(a['arm'],0)+1
            result=budget_estimate(args.protocol,calls,args.tokens_per_second,load_minutes=args.load_minutes)
        elif args.cmd=='import-records':
            from .posthoc import import_records
            expect={'observed':0,'malformed':65,'unattempted':127} if args.expect_original_strict else None
            imp=import_records(plan,args.src,expect)
            if args.out_dir.exists():raise FileExistsError('fresh import directory required')
            args.out_dir.mkdir(parents=True)
            with (args.out_dir/'records.jsonl').open('x',encoding='utf-8') as f:
                for r in imp.pop('rows'):f.write(canon(r)+chr(10))
            result=imp;write_json(args.out_dir/'import_receipt.json',result)
        elif args.cmd=='posthoc':
            from .posthoc import diagnose,diagnose_tokens,load_terminal_map
            rows=[r for src in args.records for r in read_records(src)]
            if args.terminal_map:
                tmap,doc=load_terminal_map(args.terminal_map)
                result=diagnose_tokens(plan,rows,tmap);result['terminal_map_source']=doc.get('tokenizer_label')
            else:result=diagnose(plan,rows)
            write_json(args.out,result)
        elif args.cmd=='score':
            rows=[r for src in args.records for r in read_records(src)]
            result=score(plan,rows)
            write_json(args.out,result)
        elif args.cmd=='fixture':result=run_fixture(plan,args.out,args.arm,args.policy)
        elif args.cmd=='hf':result=run_hf(plan,args.out,arm=args.arm,base_model=args.base,model_revision=args.revision,
                                          adapter_path=args.adapter,approval=args.approved,max_requests=args.max_requests,
                                          max_new_tokens=args.max_new_tokens,thinking=not args.no_thinking)
        elif args.cmd=='hf-group':result=run_hf_group(plan,args.out,base_model=args.base,
                  model_revision=args.revision,formal_adapter=args.formal_adapter,platonic_adapter=args.platonic_adapter,
                  approval=args.approved,max_assignments=args.max_assignments,max_new_tokens=args.max_new_tokens,
                  max_wall_seconds=args.max_wall_seconds,thinking=args.thinking,protocol=args.protocol,arms=args.arms)
        elif args.cmd=='endpoint':result=run_endpoint(plan,args.out,args.arm,model_id=args.model_id,base_url=args.url,
                      approval=args.approved,max_requests=args.max_requests,total_output_cap=args.total_output_cap,
                      output_tokens_per_request=args.max_new_tokens,per_request_timeout=args.timeout,
                      api_key_env=args.api_key_env,reasoning_effort=args.reasoning_effort)
        else:raise AssertionError('unreachable')
    print(json.dumps(result,indent=2,sort_keys=True))

if __name__=='__main__':main()
