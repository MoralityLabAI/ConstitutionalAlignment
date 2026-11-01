import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from itertools import product
from fractions import Fraction as F
from experiments.constitutional_reasoning_gym_v3.core import *
from experiments.constitutional_reasoning_gym_v3.data import *
from experiments.constitutional_reasoning_gym_v3.runtime import encode_sft,segmented_loss,local_identity
from experiments.constitutional_reasoning_gym_v3.evaluate import plan,validate_plan,run_scripted,score
from experiments.constitutional_reasoning_gym_v3.mechinterp import *
from experiments.constitutional_reasoning_gym_v3.publishing import prepare_bundle

class CoreTests(unittest.TestCase):
    def setUp(self):self.c=make_twins('delegation',0,0)[1]
    def test_finite_oracle(self):
        for f in range(8):
            for n in range(3,8):
                for bits in product((False,True),repeat=n):
                    facts={f'e{i}':v for i,v in enumerate(bits)}
                    self.assertEqual(evaluate_ast(formula(f,n),facts),independent_oracle(f,facts))
    def test_pivotal_twins(self):
        for t in TRACKS:
            for f in range(4):
                lo,hi=make_twins(t,f,3)
                self.assertFalse(lo.authorized);self.assertTrue(hi.authorized)
                self.assertEqual(sum(lo.facts[k]!=hi.facts[k] for k in lo.facts),1)
                self.assertEqual(lo.options,hi.options)
    def test_counterfactual(self):self.assertFalse(self.c.counterfactual().authorized)
    def test_no_hidden_answer(self):
        ob=self.c.view()
        self.assertNotIn('authorized',ob);self.assertNotIn('expected',ob)
        self.assertEqual(len(ob['actions']),3)
    def test_sealed_forbidden(self):
        with self.assertRaises(ValueError):make_twins('delegation',6,0,'sealed')
    def test_family_split(self):
        with self.assertRaises(ValueError):make_twins('delegation',4,0,'train')
    def test_reproducible_case(self):self.assertEqual(make_twins('delegation',0,0)[1],self.c)
    def test_choice_rotation(self):self.assertGreater(len({make_twins('delegation',0,i)[0].options for i in range(30)}),2)
    def test_strict_parser(self):
        for x in ('{"choice":true}','{"choice":0,"choice":1}','{"choice":0} garbage','{"choice":3}','{"choice":NaN}','{"report":0}'):
            with self.assertRaises(ValueError):parse_action(x)
    def test_truthful_rollout(self):
        w=World(self.c);raw='  '+canon({'choice':self.c.expected()})+'  '
        w.step(raw);w.step(raw);r=w.receipt();s=score_receipt(json.loads(canon(r)))
        self.assertTrue(s['correct_action']);self.assertTrue(s['truthful_report'])
        self.assertEqual(r['events'][0]['raw'],raw)
    def test_gate_separation(self):
        bad=self.c.options.index(TRACKS[self.c.track][1]);w=World(self.c,gate=True)
        w.step(canon({'choice':bad}));w.step(canon({'choice':self.c.expected()}))
        s=score_receipt(w.receipt());self.assertTrue(s['proposed_failure']);self.assertFalse(s['executed_failure'])
    def test_invalid_denominator(self):
        w=World(self.c)
        for _ in range(5):w.step('broken')
        s=score_receipt(w.receipt());self.assertEqual(s['invalid'],5);self.assertFalse(s['correct_action'])
    def test_timeout_unknown(self):
        w=World(self.c);w.timeout();self.assertIsNone(score_receipt(w.receipt())['correct_action'])
    def test_tamper_rejected(self):
        w=World(self.c);r=w.receipt();r['sha256']='wrong'
        with self.assertRaises(ValueError):score_receipt(r)
    def test_cue_does_not_change_duty(self):
        for w,b in product((False,True),repeat=2):self.assertEqual(replace(self.c,watched=w,bonus=b).expected(),self.c.expected())
    def test_training_cue_independent_of_oversight(self):
        a=self.c.view();b=replace(self.c,watched=True).view()
        self.assertEqual(a['training_cue'],b['training_cue'])
        self.assertNotEqual(a['oversight'],b['oversight'])
        t=replace(self.c,training_context=True).view()
        self.assertNotEqual(a['training_cue'],t['training_cue'])
        self.assertEqual(a['oversight'],t['oversight'])
    def test_reward_logged(self):
        c=replace(self.c,bonus=True);w=World(c)
        choice=c.options.index(TRACKS[c.track][0]);_,reward,*_=w.step(canon({'choice':choice}))
        self.assertEqual(reward,5.)
        self.assertEqual(w.receipt()['events'][0]['personal_reward'],5.)
    def test_reporting_schema_shared(self):
        c=make_twins('reporting',1,2)[0];self.assertEqual(c.view()['signed_event'],'retention')
        self.assertIsInstance(c.expected(),int)

class DataTests(unittest.TestCase):
    def setUp(self):self.c=make_twins('delegation',0,0)[1];self.teacher=FixtureTeacher()
    def candidate(self):return self.teacher.generate_many([request(self.c,'secular',MODES[0],'rewrite')])[0]['text']
    def test_fixture_accepted(self):self.assertTrue(validate_candidate(self.c,self.candidate())['accepted'])
    def test_free_text_is_not_certified(self):self.assertFalse(validate_candidate(self.c,self.candidate())['free_text_semantics_verified'])
    def test_wrong_action_rejected(self):
        o=json.loads(self.candidate());o['choice']=self.c.options.index('pause')
        self.assertIn('wrong_action',validate_candidate(self.c,canon(o))['errors'])
    def test_wrong_counterfactual_rejected(self):
        o=json.loads(self.candidate());o['counterfactual_choice']=self.c.expected()
        self.assertIn('wrong_counterfactual',validate_candidate(self.c,canon(o))['errors'])
    def test_invented_evidence_rejected(self):
        o=json.loads(self.candidate());o['evidence_ids'].append('invented')
        self.assertFalse(validate_candidate(self.c,canon(o))['accepted'])
    def test_missing_reason_rejected(self):
        o=json.loads(self.candidate());o['rationale']=''
        self.assertFalse(validate_candidate(self.c,canon(o))['accepted'])
    def test_eval_rejected_in_generation(self):
        c=make_twins('delegation',4,0,'calibration')[0]
        with self.assertRaises(ValueError):request(c,'jinn',MODES[0],'draft')
    def test_unknown_frame(self):
        with self.assertRaises(ValueError):request(self.c,'other',MODES[0],'draft')
    def test_context_preserved(self):
        r=request(self.c,'jinn',MODES[0],'rewrite','original','critique')
        self.assertIn('original',r['messages'][1]['content']);self.assertIn('critique',r['messages'][1]['content'])
        self.assertIn('Allah',r['messages'][0]['content'])
    def test_resumable_generation(self):
        with tempfile.TemporaryDirectory() as d:
            a=produce(self.teacher,d,groups=2);b=produce(self.teacher,d,groups=2)
            self.assertEqual(a['calls_total'],24);self.assertEqual(b['new_calls'],0)
            self.assertEqual(a['shards'],b['shards'])
    def test_two_revision_rounds_have_full_lineage(self):
        with tempfile.TemporaryDirectory() as d:
            m=produce(self.teacher,d,groups=1,rounds=2)
            self.assertEqual(m['calls_total'],20)
            records=list(read_records(d))
            self.assertEqual(len(records[0]['revision_history']),5)
            self.assertEqual(len(records[0]['requests']),5)
            self.assertEqual(m['completed_records'],4)
    def test_resume_drift_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            produce(self.teacher,d,groups=1)
            with self.assertRaises(ValueError):produce(self.teacher,d,groups=2)
    def test_fixture_sft_requires_flag(self):
        with tempfile.TemporaryDirectory() as d:
            produce(self.teacher,Path(d)/'raw',groups=1)
            with self.assertRaises(ValueError):export_sft(Path(d)/'raw',Path(d)/'sft')
    def test_paired_sft(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'raw';target=Path(d)/'sft';produce(self.teacher,source,groups=2)
            m=export_sft(source,target,True);self.assertEqual(m['paired_cases'],4)
            a=[json.loads(x) for x in (target/'secular_masked.jsonl').read_text().splitlines()]
            b=[json.loads(x) for x in (target/'secular_supervised.jsonl').read_text().splitlines()]
            for x,y in zip(a,b):
                self.assertEqual(x['rationale'],y['rationale']);self.assertEqual(x['final'],y['final'])
    def test_shard_tamper_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            m=produce(self.teacher,d,groups=1);p=Path(d)/'shards'/m['shards'][0]['path'];p.write_bytes(b'wrong')
            with self.assertRaises(ValueError):list(read_records(d))
    def test_rejected_twins_do_not_select_an_arm(self):
        class BrokenFrame(FixtureTeacher):
            def generate_many(self,rs):
                xs=super().generate_many(rs)
                for r,x in zip(rs,xs):
                    if r['frame']=='jinn' and r['stage']=='rewrite':x['text']='bad'
                return xs
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);produce(BrokenFrame(),root/'raw',groups=2)
            r=export_sft(root/'raw',root/'sft',True)
            self.assertEqual(r['paired_cases'],0)
            self.assertTrue(all(v['rows']==0 for v in r['arms'].values()))
    def test_unknown_tenet_rejected(self):
        o=json.loads(self.candidate());o['tenets']=['invented']
        self.assertIn('unknown_tenet',validate_candidate(self.c,canon(o))['errors'])
    def test_duplicate_candidate_keys_rejected(self):
        self.assertFalse(validate_candidate(self.c,'{"choice":0,"choice":1}')['accepted'])
    def test_opaque_trace_marker_rejected(self):
        o=json.loads(self.candidate());o['rationale']+=' <think>'
        self.assertIn('foreign_trace_marker',validate_candidate(self.c,canon(o))['errors'])
    def test_full_context_hub_bundle(self):
        class MockGenerated(FixtureTeacher):
            evidence_class='MODEL_GENERATED'  # unit-test double, never a production generation
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);produce(MockGenerated(),root/'raw',groups=2,rounds=2)
            export_sft(root/'raw',root/'sft')
            manifest=prepare_bundle(root/'sft',root/'hub',root/'raw')
            self.assertTrue(manifest['private']);self.assertTrue(manifest['raw_full_requests_included'])
            self.assertEqual(len(manifest['training_data_files']),4)
            self.assertTrue(any(k.startswith('raw/') for k in manifest['files']))
    def test_paired_group_dedup_counts(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);produce(self.teacher,root/'raw',groups=32)
            m=export_sft(root/'raw',root/'sft',True)
            self.assertEqual(m['accepted_semantic_motifs'],32)
            self.assertTrue(all(a['rows']==80 for a in m['arms'].values()))
    def test_fixture_cannot_publish(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);produce(self.teacher,root/'raw',groups=1);export_sft(root/'raw',root/'sft',True)
            with self.assertRaises(ValueError):prepare_bundle(root/'sft',root/'hub')

class TinyTokenizer:
    eos_token_id=2;chat_template=None
    def encode(self,s,add_special_tokens=False):return [ord(c)+3 for c in s]

class TrainingTests(unittest.TestCase):
    def row(self,weight):return {'system':'charter','user':'task','rationale':'reason','final':'{"choice":0}','rationale_weight':weight,'action_weight':1.}
    def test_identical_input_streams(self):
        a=encode_sft(TinyTokenizer(),self.row(0));b=encode_sft(TinyTokenizer(),self.row(.25))
        self.assertEqual(a['input_ids'],b['input_ids']);self.assertNotEqual(a['labels'],b['labels'])
    def test_one_eos(self):
        a=encode_sft(TinyTokenizer(),self.row(.25));self.assertEqual(a['input_ids'].count(2),1)
    def test_prompt_mask(self):
        a=encode_sft(TinyTokenizer(),self.row(.25));self.assertTrue(all(l==-100 for l,s in zip(a['labels'],a['segments']) if s==0))
    def test_context_failure(self):
        with self.assertRaises(ValueError):encode_sft(TinyTokenizer(),self.row(.25),5)
    def test_segmented_backward(self):
        import torch
        torch.manual_seed(41)
        x=torch.randn(1,6,12,requires_grad=True);y=torch.tensor([[-100,-100,4,5,6,2]]);seg=torch.tensor([[0,0,1,1,2,2]])
        loss=segmented_loss(x,y,seg);self.assertTrue(torch.isfinite(loss));loss.backward();self.assertTrue(torch.isfinite(x.grad).all())
    def test_rationale_mask_gradient(self):
        import torch
        x=torch.randn(1,6,12,requires_grad=True);y=torch.tensor([[-100,-100,-100,-100,6,2]]);seg=torch.tensor([[0,0,1,1,2,2]])
        segmented_loss(x,y,seg,0).backward();self.assertEqual(float(x.grad[0,:3].abs().sum()),0.)
    def test_format_warmup_uses_numeric_action(self):
        r={**self.row(0),'format_only':True,'rationale':''}
        e=encode_sft(TinyTokenizer(),r)
        self.assertNotIn(1,e['segments'])
        self.assertEqual(e['input_ids'].count(2),1)
    def test_action_segment_still_trained(self):
        e=encode_sft(TinyTokenizer(),self.row(0))
        self.assertTrue(all(l!=-100 for l,s in zip(e['labels'],e['segments']) if s==2))
    def test_missing_local_model(self):
        with self.assertRaises(ValueError):local_identity('/not/a/model','0'*40)

class EvalTests(unittest.TestCase):
    def test_complete_roster(self):
        p=plan(groups=2);self.assertEqual(len(p['blocks'][0]['cells']),16);validate_plan(p)
    def test_independent_factorial_cues(self):
        p=plan(groups=2)
        cells=p['blocks'][0]['cells']
        self.assertEqual(len({(c['authorized'],c['watched'],c['bonus'],c['training_context']) for c in cells}),16)
    def test_general_callback_and_timeout(self):
        from experiments.constitutional_reasoning_gym_v3.evaluate import run_agent
        with tempfile.TemporaryDirectory() as d:
            def actor(arm,messages):
                ob=json.loads(messages[-1]['content'].split('\n',1)[1])
                if arm=='O1':raise TimeoutError('mock interruption')
                if ob['stage']=='report':
                    value=ob['signed_event']['executed'];choice=next(a['id'] for a in ob['actions'] if a['meaning']=='report '+value)
                else:
                    choice=next(a['id'] for a in ob['actions'] if a['meaning']=='pause')
                return canon({'choice':choice})
            r=run_agent(plan(groups=2),actor,Path(d)/'run')
            self.assertEqual(r['manifest']['records'],64)
            self.assertEqual(r['metrics']['arms']['O1']['correct_action_bounds'],['0','1'])
            self.assertEqual(r['manifest']['status'],'PARTIAL')
    def test_sealed_plan_forbidden(self):
        with self.assertRaises(ValueError):plan(split='sealed')
    def test_plan_tamper_rejected(self):
        p=plan();p['blocks'][0]['arm_order']=['S1']
        with self.assertRaises(ValueError):validate_plan(p)
    def test_honest_vs_conservative(self):
        with tempfile.TemporaryDirectory() as d:
            r=run_scripted(plan(),d)
            self.assertEqual(r['arms']['S1']['J_minus_observed_lower'],'1')
            self.assertEqual(r['arms']['O1']['J_minus_observed_lower'],'0')
    def test_refusal_penalized(self):
        with tempfile.TemporaryDirectory() as d:
            r=run_scripted(plan(),d,{'S1':'honest','O1':'refuse'})
            self.assertEqual(r['arms']['O1']['J_minus_observed_lower'],'-1')
    def test_missing_arm_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=plan();run_scripted(p,d)
            rows=[json.loads(x) for x in (Path(d)/'rollouts.jsonl').read_text().splitlines()]
            with self.assertRaises(ValueError):score(p,rows[:-1])
    def test_unknown_retained(self):
        with tempfile.TemporaryDirectory() as d:
            r=run_scripted(plan(),d,{'S1':'honest','O1':'timeout'})
            self.assertEqual(r['arms']['O1']['correct_action_bounds'],['0','1'])
            self.assertEqual(r['arms']['O1']['accurate_reporting_bounds'],['0','1'])

class LaunchTests(unittest.TestCase):
    def test_shell_arguments_survive_builtin_names(self):
        import os,subprocess
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);base=root/'model';base.mkdir();tools=root/'bin';tools.mkdir()
            log=root/'calls';stub=tools/'python'
            stub.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$CALL_LOG"\n',encoding='utf-8')
            stub.chmod(0o755)
            script=Path(__file__).resolve().parents[1]/'scripts/silico_generate.sh'
            env=dict(os.environ,PATH=str(tools)+os.pathsep+os.environ['PATH'],CALL_LOG=str(log))
            result=subprocess.run(['bash',str(script),str(base),'0'*40,str(root/'run'),'120','4'],env=env,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn('--groups 4',log.read_text())
            self.assertEqual(json.loads((root/'run/process_receipt.json').read_text())['process_exit_code'],0)

class MechanismTests(unittest.TestCase):
    def test_split_guard(self):
        with self.assertRaises(ValueError):split_guard(['a'],['a'])
    def test_equal_norm(self):
        v=np.array([1.,2.,3.]);r=equal_norm_random(v)
        self.assertAlmostEqual(np.linalg.norm(v),np.linalg.norm(r));self.assertFalse(np.allclose(v,r))
    def test_probe(self):
        rng=np.random.default_rng(7);x=rng.normal(size=(40,3));z=rng.normal(size=(20,3))
        r=ridge_probe(x,x[:,0]>0,z,z[:,0]>0,[f'a{i}' for i in range(40)],[f'b{i}' for i in range(20)])
        self.assertGreaterEqual(r['accuracy'],.8);self.assertFalse(r['causal_evidence'])
    def test_hook_capture(self):
        import torch
        m=torch.nn.Identity();x=torch.randn(2,4,3)
        with capture_residuals({'layer':m},[-1,0]) as saved:m(x)
        self.assertTrue(torch.equal(saved['layer'][0],x[0,-1]));self.assertFalse(m._forward_hooks)
    def test_intervention_reversible(self):
        import torch
        m=torch.nn.Identity();x=torch.zeros(1,2,3)
        with intervene(m,[1,2,3]):self.assertEqual(float(m(x)[0,-1].sum()),6.)
        self.assertEqual(float(m(x).sum()),0.)
    def test_hook_exception_cleanup(self):
        import torch
        m=torch.nn.Identity()
        with self.assertRaises(RuntimeError):
            with capture_residuals({'l':m},[-1]):raise RuntimeError('fixture')
        self.assertFalse(m._forward_hooks)

if __name__=='__main__':unittest.main()
