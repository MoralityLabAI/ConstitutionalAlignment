import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import torch
from experiments.ontological_constitution_v4 import curriculum
from experiments.ontological_constitution_v4.logic import canon, digest
from experiments.ontological_constitution_v4_training import admission as a, preflight as p, evaluation as ev
from experiments.ontological_constitution_v4_training.pilot import train_rounds,run_pilot,state_hash
from experiments.constitutional_reasoning_gym_v3.runtime import segmented_loss

class FixtureTokenizer:
    """CPU contract double. No claim about Qwen token lengths or vocabulary."""
    is_fast=True;chat_template='fixture-native-v1';eos_token='<eos>';eos_token_id=2;pad_token_id=2
    def apply_chat_template(self,messages,tokenize=False,add_generation_prompt=True,enable_thinking=False):
        return ''.join('<'+m['role']+'>\n'+m['content']+'<eos>\n' for m in messages)+'<assistant>\n'
    def __call__(self,text,add_special_tokens=False,return_offsets_mapping=False):
        ids=[];spans=[];i=0
        while i<len(text):
            j=i+len(self.eos_token) if text.startswith(self.eos_token,i) else i+1
            ids.append(2 if j-i>1 else ord(text[i])%251+3);spans.append((i,j));i=j
        return {'input_ids':ids,'offset_mapping':spans}
    def encode(self,text,add_special_tokens=False):return self(text)['input_ids']

class SuiteBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.root=Path(cls.tmp.name)
        curriculum.export(cls.root/'corpus');cls.corpus,cls.receipt=a.load_corpus(cls.root/'corpus')
        cls.row=cls.corpus['platonic_grounding_derivation.jsonl'][0]
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

class AdmissionTests(SuiteBase):
    def test_entire_corpus(self):self.assertEqual((self.receipt['records'],self.receipt['semantic_groups']),(320,20))
    def test_exact_evidence_type(self):self.assertEqual(a.admitted_sft(self.row)['source_evidence_class'],a.EVIDENCE)
    def test_changed_explanation(self):
        r=copy.deepcopy(self.row);r['messages'][2]['content']='invented'
        with self.assertRaises(ValueError):a.admitted_sft(r)
    def test_rehashed_false_text(self):
        r=copy.deepcopy(self.row);r['messages'][2]['content']='invented';r['sha256']=digest({k:v for k,v in r.items() if k!='sha256'})
        with self.assertRaises(ValueError):a.admitted_sft(r)
    def test_false_type(self):
        r={**self.row,'evidence_class':'MODEL_GENERATED'}
        with self.assertRaises(ValueError):a.admitted_sft(r)
    def test_test_split(self):
        with self.assertRaises(ValueError):a.admitted_sft({**self.row,'split':'test'})
    def test_teacher_prose(self):
        with self.assertRaises(ValueError):a.admitted_sft({**self.row,'teacher_free_text_included':True})
    def test_invalid_certificate(self):
        r=copy.deepcopy(self.row);r['certificate']['sha256']='wrong'
        with self.assertRaises(ValueError):a.admitted_sft(r)
    def test_duplicate_json(self):
        with self.assertRaises(ValueError):a.strict_loads('{"a":1,"a":2}')
    def test_nonfinite_json(self):
        with self.assertRaises(ValueError):a.strict_loads('{"a":NaN}')
    def test_tampered_corpus(self):
        with tempfile.TemporaryDirectory() as d:
            curriculum.export(d+'/c');f=Path(d)/'c'/'formal_control_derivation.jsonl';f.write_text(f.read_text()+'\n')
            with self.assertRaises(ValueError):a.load_corpus(Path(d)/'c')
    def test_missing_file_in_manifest(self):
        with tempfile.TemporaryDirectory() as d:
            curriculum.export(d+'/c');f=Path(d)/'c/manifest.json';v=json.loads(f.read_text());v['files'].pop(next(iter(v['files'])));a.write_json(f,v)
            with self.assertRaises(ValueError):a.load_corpus(Path(d)/'c')
    def test_schedule_same_certificates(self):
        plan=a.schedule(self.corpus)
        self.assertEqual(len({r['group_id'] for r in plan['rounds']}),20)
        self.assertEqual(sum(r['arm_order'][0]=='formal_control' for r in plan['rounds']),10)
    def test_schedule_reproducible(self):self.assertEqual(a.schedule(self.corpus),a.schedule(self.corpus))
    def test_schedule_option_balance(self):
        self.assertEqual({r['variant'] for r in a.schedule(self.corpus)['rounds']},{0,1})
    def test_schedule_refuses_unknown_arm(self):
        with self.assertRaises(ValueError):a.schedule(self.corpus,('formal_control','bogus'))
    def test_single_arm_refused(self):
        with self.assertRaises(ValueError):a.schedule(self.corpus,('formal_control',))

class TokenTests(SuiteBase):
    def encode(self):return p.encode(self.row,FixtureTokenizer(),32768)
    def test_one_supervised_eos(self):self.assertEqual(self.encode()['labels'].count(2),1)
    def test_template_eos_masked(self):
        e=self.encode();self.assertGreater(e['input_ids'].count(2),1)
        self.assertTrue(all(l==-100 for l,s in zip(e['labels'],e['segments']) if s==0))
    def test_final_action_trained(self):
        e=self.encode();self.assertTrue(all(l!=-100 for l,s in zip(e['labels'],e['segments']) if s==2))
    def test_reason_trained(self):self.assertIn(1,self.encode()['segments'])
    def test_no_padding_exposure(self):self.assertEqual(set(self.encode()['attention_mask']),{1})
    def test_no_silent_overflow(self):
        with self.assertRaises(ValueError):p.encode(self.row,FixtureTokenizer(),10)
    def test_no_slow_tokenizer(self):
        t=FixtureTokenizer();t.is_fast=False
        with self.assertRaises(ValueError):p.encode(self.row,t)
    def test_no_template(self):
        t=FixtureTokenizer();t.chat_template=None
        with self.assertRaises(ValueError):p.encode(self.row,t)
    def test_bad_eos(self):
        t=FixtureTokenizer();t.eos_token_id=900
        with self.assertRaises(ValueError):p.encode(self.row,t,32768)
    def test_cross_prompt_token_rejected(self):
        class Bad(FixtureTokenizer):
            def __call__(self,text,**kw):
                e=super().__call__(text,**kw)
                if 'Rationale:\n' in text:
                    pos=text.index('Rationale:\n');i=next(i for i,x in enumerate(e['offset_mapping']) if x[0]==pos)
                    e['offset_mapping'][i]=(pos-1,pos+1)
                return e
        with self.assertRaises(ValueError):p.encode(self.row,Bad(),32768)
    def test_preflight_mock_not_student(self):
        r,_=p.preflight(self.root/'corpus',FixtureTokenizer(),{'kind':'TEST_FIXTURE'},max_length=32768)
        self.assertFalse(r['student_tokenizer_measured']);self.assertEqual(r['status'],'PREFLIGHT_PASS')
        with self.assertRaises(ValueError):p.verify_preflight(r,self.root/'corpus',{'kind':'TEST_FIXTURE'})
    def test_preflight_overflow_receipt(self):
        r,_=p.preflight(self.root/'corpus',FixtureTokenizer(),{'kind':'TEST_FIXTURE'},max_length=10)
        self.assertEqual(r['status'],'PREFLIGHT_FAIL');self.assertEqual(len(r['errors']),320)
    def test_receipt_revalidation(self):
        identity={'kind':'LOCAL_STUDENT_TOKENIZER','test_double':True}
        r,_=p.preflight(self.root/'corpus',FixtureTokenizer(),identity,max_length=32768)
        self.assertTrue(p.verify_preflight(r,self.root/'corpus',identity))
        with self.assertRaises(ValueError):p.verify_preflight(r,self.root/'corpus',{**identity,'test_double':False})
    def test_preflight_tamper(self):
        r,_=p.preflight(self.root/'corpus',FixtureTokenizer(),{'kind':'TEST_FIXTURE'},max_length=32768);r['status']='other'
        with self.assertRaises(ValueError):p.verify_preflight(r,self.root/'corpus',{'kind':'TEST_FIXTURE'})
    def test_no_checkpoint_required_for_identity(self):
        with tempfile.TemporaryDirectory() as d:
            for name in ('config.json','tokenizer.json','tokenizer_config.json'):(Path(d)/name).write_text('{}')
            self.assertFalse(p.tokenizer_identity(d,'1'*40)['weights_read'])
    def test_incomplete_tokenizer_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(FileNotFoundError):p.tokenizer_identity(d,'1'*40)

class LoopTests(SuiteBase):
    def test_complete_paired_updates(self):
        calls=[]
        with tempfile.TemporaryDirectory() as d:
            r=train_rounds(a.schedule(self.corpus),lambda arm,rid,i:(calls.append((arm,i)) or {'loss':2.}),Path(d)/'log',100,clock=lambda:0)
        self.assertEqual(len(calls),40);self.assertEqual(r['paired_complete_rounds'],20)
    def test_bad_score_does_not_gate_second_arm(self):
        calls=[]
        def step(arm,rid,i):calls.append(arm);return {'loss':1000000. if arm=='formal_control' else 1.}
        with tempfile.TemporaryDirectory() as d:train_rounds(a.schedule(self.corpus,steps=2),step,Path(d)/'log',100,clock=lambda:0)
        self.assertEqual(calls,['formal_control','platonic_grounding','platonic_grounding','formal_control'])
    def test_exception_still_records_second_arm(self):
        def step(arm,rid,i):
            if arm=='formal_control':raise RuntimeError('injected')
            return {'loss':1.}
        with tempfile.TemporaryDirectory() as d:r=train_rounds(a.schedule(self.corpus),step,Path(d)/'log',100,clock=lambda:0)
        self.assertEqual(r['steps_completed']['platonic_grounding'],1);self.assertEqual(r['status'],'PARTIAL')
    def test_deadline(self):
        with tempfile.TemporaryDirectory() as d:r=train_rounds(a.schedule(self.corpus),lambda *x:None,Path(d)/'log',1,clock=lambda:2)
        self.assertEqual(r['updates_logged'],0);self.assertEqual(r['status'],'TIME_CAP')
    def test_no_authorization_no_load(self):
        with self.assertRaises(PermissionError):run_pilot('missing','missing','x','missing','missing')
    def test_segmented_gradients(self):
        torch.manual_seed(11);x=torch.randn(1,8,12,requires_grad=True)
        labels=torch.tensor([[-100,-100,3,4,5,6,7,2]]);seg=torch.tensor([[0,0,1,1,1,2,2,2]])
        loss=segmented_loss(x,labels,seg);loss.backward()
        self.assertTrue(torch.isfinite(loss));self.assertEqual(float(x.grad[0,0].abs().sum()),0.)
    def test_paired_tiny_adapters_update_separately(self):
        torch.manual_seed(11);base=torch.nn.Linear(3,5);base.requires_grad_(False)
        a1=torch.nn.Linear(3,5,bias=False);a2=copy.deepcopy(a1)
        old=state_hash(a2.state_dict());opt=torch.optim.AdamW(a1.parameters(),lr=.01)
        x=torch.randn(4,3);opt.zero_grad();((base(x)+a1(x))**2).mean().backward();opt.step()
        self.assertEqual(old,state_hash(a2.state_dict()));self.assertNotEqual(old,state_hash(a1.state_dict()))
        self.assertTrue(all(p.grad is None for p in base.parameters()))

class EvaluationTests(unittest.TestCase):
    def test_balanced_roster(self):
        p1=ev.pair_plan();self.assertEqual(len(p1['blocks']),8);ev.validate_plan(p1)
        self.assertEqual(sum(b['arm_order'][0]=='formal_control' for b in p1['blocks']),4)
    def test_full_numeric_schema(self):
        p1=ev.pair_plan(motifs=4)
        with tempfile.TemporaryDirectory() as d:
            r=ev.run(p1,ev.d.scripted('dutiful'),d)
        self.assertEqual(r['records'],128);self.assertEqual(r['paired_accuracy_bounds'],['0','0'])
    def test_malformed_not_refusal(self):
        with tempfile.TemporaryDirectory() as d:r=ev.run(ev.pair_plan(motifs=4),ev.d.scripted('malformed'),d)
        self.assertEqual(r['arms']['formal_control']['malformed'],64);self.assertEqual(r['arms']['formal_control']['abandonment'],0)
    def test_timeouts_keep_denominator(self):
        with tempfile.TemporaryDirectory() as d:r=ev.run(ev.pair_plan(motifs=4),ev.d.scripted('timeout'),d)
        self.assertEqual(r['records'],128);self.assertEqual(r['arms']['formal_control']['accuracy_bounds'],['0','1'])
    def test_paired_deadline_preserves_roster(self):
        with tempfile.TemporaryDirectory() as d:r=ev.run(ev.pair_plan(motifs=4),lambda *a:'bad',d,deadline=1,clock=lambda:2)
        self.assertEqual(r['records'],128);self.assertEqual(r['arms']['platonic_grounding']['unknown'],64)
    def test_missing_arm_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            plan=ev.pair_plan(motifs=4);ev.run(plan,ev.d.scripted('dutiful'),d)
            rows=[json.loads(s) for s in (Path(d)/'rollouts.jsonl').read_text().splitlines()]
            with self.assertRaises(ValueError):ev.score(plan,rows[:-1])
    def test_partial_generation_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            r=ev.run(ev.pair_plan(motifs=4),lambda *x:{'text':'{','timed_out':True},d)
            row=json.loads((Path(d)/'rollouts.jsonl').read_text().splitlines()[0])
        self.assertEqual(row['generation']['text'],'{');self.assertEqual(row['status'],'unknown')
    def test_plan_tamper(self):
        p1=ev.pair_plan();p1['blocks'][0]['arm_order']=['formal_control']
        with self.assertRaises(ValueError):ev.validate_plan(p1)
    def test_prompt_tamper(self):
        with tempfile.TemporaryDirectory() as d:
            plan=ev.pair_plan(motifs=4);ev.run(plan,ev.d.scripted('dutiful'),d)
            rows=[json.loads(s) for s in (Path(d)/'rollouts.jsonl').read_text().splitlines()];rows[0]['prompt']='wrong'
            with self.assertRaises(ValueError):ev.score(plan,rows)

if __name__=='__main__':unittest.main()
