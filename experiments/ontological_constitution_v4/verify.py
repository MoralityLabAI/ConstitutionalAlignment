"""Reproduce finite audits, proof corpus and model-free transfer controls."""
from pathlib import Path
from itertools import product
import argparse
import gzip
import hashlib
import json
import platform
import re
import subprocess
import sys
from .logic import canon, digest, models, holds, truth_set
from .semantics import graph_facts, graph_reference, bayes, anderson_two_worlds, scott_grounding_witness
from .certificates import fixtures, verify as verify_certificate
from .curriculum import export, build_rows
from .dilemmas import build_plan, evaluate, score, scripted
from .sources import SOURCES, BASE


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True)+'\n', encoding='utf-8')


def finite_audit():
    graphs = eligible = 0
    for n in range(1,4):
        pairs = list(product(range(n), repeat=2))
        for mask in range(1 << len(pairs)):
            edges = [list(e) for i,e in enumerate(pairs) if mask >> i & 1]
            a = graph_facts(n, edges); b = graph_reference(n, edges)
            if any(a[k] != v for k,v in b.items()): raise AssertionError('graph oracles disagree')
            if a['theorem_applicable']:
                eligible += 1
                if not a['unique_first_principle']: raise AssertionError('finite root theorem counterexample')
            graphs += 1
    checks = 0
    fs = ['p', ('not','p'), ('and','p','q'), ('or','p','q'), ('box','p'), ('dia','p'),
          ('implies',('dia',('box','p')),('box','p'))]
    for model in models(['p','q'], 2, 'K'):
        for f in fs:
            if {w for w in range(2) if holds(f,model,w)} != truth_set(f,model): raise AssertionError('modal oracle mismatch')
            checks += 1
    updates = 0
    from fractions import Fraction as F
    for p in ('1/4','1/2','3/4'):
        for h,f in product([F(i,4) for i in range(5)],repeat=2):
            if h == f == 0: continue
            if not bayes(p,h,f)['increase_iff_likelihood_favors_claim']: raise AssertionError('Bayes criterion')
            updates += 1
    for _, c in fixtures(): verify_certificate(c)
    return {'evidence_class':'EXACT_FINITE_AUDIT', 'grounding_relations_checked':graphs,
            'satisfying_grounding_relations':eligible, 'root_theorem_failures':0,
            'modal_differential_checks':checks,'rational_guidance_updates':updates,
            'anderson_singleton_two_worlds':anderson_two_worlds(),
            'scott_grounding_without_A6':scott_grounding_witness(1),
            'scott_grounding_with_A6':scott_grounding_witness(0),
            'unbounded_lean_proof_rebuilt':False}


def verify_all(out):
    out = Path(out)
    if out.exists(): raise FileExistsError('fresh verification directory required')
    out.mkdir(parents=True)
    package = Path(__file__).resolve().parent; root = package.parents[1]
    commands = [
        [sys.executable,'-m','unittest','discover','-s',str(package/'tests'),'-v'],
        [sys.executable,'-m','unittest','discover','-s','experiments/constitutional_reasoning_gym_v3/tests','-v'],
        [sys.executable,'-m','unittest','discover','-s','experiments/constitutional_reasoning_gym_v3/v31/tests','-v'],
        [sys.executable,'-m','unittest','discover','-s','experiments/constitutional_reasoning_gym_v3/semantic_review_v1/tests','-v']]
    results=[]
    import os
    for i,cmd in enumerate(commands):
        proc=subprocess.run(cmd,cwd=root,capture_output=True,text=True,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})
        text=proc.stdout+proc.stderr;(out/f'tests_{i}.log').write_text(text,encoding='utf-8')
        if proc.returncode: raise RuntimeError(f'test suite {i} failed: '+text[-2500:])
        count=int(re.search(r'Ran (\d+) tests',text).group(1))
        skipped=re.search(r'skipped=(\d+)',text)
        results.append({'suite':i,'command':' '.join(cmd[1:]),'tests':count,
                        'skipped':int(skipped.group(1)) if skipped else 0,'exit_code':proc.returncode,
                        'log_sha256':hashlib.sha256(text.encode()).hexdigest()})
    audits=finite_audit();write(out/'finite_audit.json',audits)
    corpus=export(out/'curriculum');write(out/'curriculum_manifest.json',corpus)
    plan=build_plan();write(out/'development_plan.json',plan)
    controls={}
    for policy in ('dutiful','always_positive','abandon','reward_sensitive','ontology_dependent','timeout'):
        rows=evaluate(plan,scripted(policy));controls[policy]=score(plan,rows)
        controls[policy]['evidence_class']='SYNTHETIC_SCRIPTED_POLICY'
        (out/(policy+'_rollouts.jsonl.gz')).write_bytes(gzip.compress((''.join(canon(r)+'\n' for r in rows)).encode(),mtime=0))
    write(out/'scripted_controls.json',controls)
    # Source hashes intentionally omit generated results to avoid a circular receipt.
    source={p.relative_to(package).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(package.rglob('*.py')) if '__pycache__' not in p.parts}
    proof_rows=build_rows(1)
    examples=[r for r in proof_rows if r['label']=='complete_bridge' and r['view']=='derivation']
    write(out/'examples.json',examples)
    receipt={'status':'CPU_VERIFIED','version':'ontology-constitution-v4.0.0','python':platform.python_version(),
             'base_repository_revision':BASE,'tests':results,'tests_total':sum(x['tests'] for x in results),
             'skipped_total':sum(x['skipped'] for x in results),'source_sha256':source,
             'new_tests':results[0]['tests'],'finite_audit':audits,
             'curriculum_records':corpus['records'],'semantic_groups':corpus['unique_semantic_groups'],
             'development_motifs':plan['motifs'],'records_per_synthetic_control':controls['dutiful']['records'],
             'proof_sources':SOURCES,'pretrained_model_calls':0,'GPU_jobs':0,'HF_uploads':0,
             'old_rationales_imported':0,'lean_rebuilt':False,'final_test_access':False,
             'evidence':'CPU_CERTIFICATES_AND_SYNTHETIC_CONTROLS'}
    write(out/'cpu_receipt.json',receipt)
    return receipt


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    result=verify_all(a.out)
    print(json.dumps({k:result[k] for k in ('status','tests_total','new_tests','curriculum_records','semantic_groups','GPU_jobs')},indent=2))

if __name__=='__main__':main()
