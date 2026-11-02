import copy
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from types import SimpleNamespace
import torch
from experiments.ontological_constitution_v4 import curriculum,dilemmas
from experiments.ontological_constitution_v4.logic import canon,digest
from experiments.constitutional_reasoning_gym_v3.runtime import train_local
from experiments.ontological_constitution_v4_training.contracts import *
from experiments.ontological_constitution_v4_training.engine import activate,copy_initialization,adapter_hash,train_pair,pilot
from experiments.ontological_constitution_v4_training import evaluation

class FixtureTokenizer:
    """Deterministic test vocabulary; counts are never attributed to Qwen."""
    chat_template='fixture-system-user-assistant-v1'
    eos_token_id=2
    pad_token_id=0
    def apply_chat_template(self,messages,tokenize=False,add_generation_prompt=True,**kwargs):
        return ''.join(m['role']+': '+m['content']+'\n' for m in messages)+'assistant: '
    def encode(self,text,add_special_tokens=False):
        return [3+int(hashlib.sha256(w.encode()).hexdigest()[:8],16)%251 for w in re.findall(r'\w+|[^\w\s]',text)]

class TinyPair(torch.nn.Module):
    def __init__(self):
        super().__init__();torch.manual_seed(11)
        self.embedding=torch.nn.Embedding(256,8);self.output=torch.nn.Linear(8,256)
        self.block=torch.nn.Module()
        self.block.lora_A=torch.nn.ModuleDict({a:torch.nn.Linear(8,2,bias=False) for a in ARMS})
        self.block.lora_B=torch.nn.ModuleDict({a:torch.nn.Linear(2,256,bias=False) for a in ARMS})
        for p in self.block.lora_B.parameters():torch.nn.init.zeros_(p)
        self.active=ARMS[0]
    def set_adapter(self,arm):self.active=arm
    def forward(self,input_ids,**kwargs):
        x=self.embedding(input_ids)
        return SimpleNamespace(logits=self.output(x)+self.block.lora_B[self.active](self.block.lora_A[self.active](x)))
    def save_pretrained(self,path,**kwargs):
        path=Path(path);path.mkdir(parents=True,exist_ok=True)
        for a in ARMS:
            # Test-only serialization never loads untrusted checkpoints.
            torch.save({k:v.detach().cpu() for k,v in self.state_dict().items() if '.'+a+'.' in k},path/(a+'.pt'))

class Shared(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        torch.set_num_threads(1)
        cls.rows=curriculum.build_rows(2);cls.schedule=make_schedule(cls.rows)
    def entry(self):return next(b['entries'][ARMS[0]] for b in self.schedule['blocks'] if b['entries'][ARMS[0]]['kind']=='proof')

class AdmissionTests(Shared):
    def test_frozen_upstream(self):self.assertGreater(len(verify_upstream()),5)
    def test_exact_corpus(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'corpus';curriculum.export(p)
            rows,_=load_corpus(p);self.assertEqual(len(rows),320)
    def test_edit_rationale_and_rehash_file(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'corpus';curriculum.export(p);f=p/'platonic_grounding_derivation.jsonl'
            rows=[json.loads(x) for x in f.read_text().splitlines()];rows[0]['messages'][2]['content']='invented rationale'
            f.write_text(''.join(canon(x)+'\n' for x in rows))
            m=json.loads((p/'manifest.json').read_text());m['files'][f.name]['sha256']=file_hash(f);write_json(p/'manifest.json',m)
            with self.assertRaises(ValueError):load_corpus(p)
    def test_corrupt_file_hash(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'corpus';curriculum.export(p);f=p/'formal_control_derivation.jsonl';f.write_text(f.read_text()+' ')
            with self.assertRaises(ValueError):load_corpus(p)
    def test_manifest_path_traversal(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'corpus';curriculum.export(p);m=json.loads((p/'manifest.json').read_text());m['files']['../x']={}
            write_json(p/'manifest.json',m)
            with self.assertRaises(ValueError):load_corpus(p)
    def test_reject_symlink(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'corpus';curriculum.export(p);f=p/'formal_control_derivation.jsonl';q=Path(d)/'borrowed';f.rename(q);f.symlink_to(q)
            with self.assertRaises(ValueError):load_corpus(p)
    def test_wrong_evidence_class(self):
        r=copy.deepcopy(self.rows[0]);r['evidence_class']='MODEL_GENERATED'
        with self.assertRaises(ValueError):proof_entry(r)
    def test_final_test_row(self):
        r=copy.deepcopy(self.rows[0]);r['split']='test'
        with self.assertRaises(ValueError):proof_entry(r)
    def test_certificate_recomputed(self):
        r=copy.deepcopy(self.rows[0]);r['certificate']['result']['injected']=True
        with self.assertRaises(ValueError):proof_entry(r)
    def test_teacher_prose_quarantined(self):
        r=copy.deepcopy(self.rows[0]);r['teacher_free_text_included']=True
        with self.assertRaises(ValueError):proof_entry(r)
    def test_sft_fields_cannot_drift(self):
        e=copy.deepcopy(self.entry());e['sft']['rationale']='invented'
        with self.assertRaises(ValueError):validate_entry(e)
    def test_practice_revalidated(self):
        e=practice_entry('care',True);e['source_case']['truth']=False
        with self.assertRaises(ValueError):validate_entry(e)
    def test_legacy_trainer_still_rejects_type(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'input.jsonl';p.write_text(canon(training.as_sft(self.rows[0]))+'\n')
            with patch('experiments.constitutional_reasoning_gym_v3.runtime.local_identity',return_value={}):
                with self.assertRaisesRegex(ValueError,'model-generated'):train_local(d,'0'*40,p,Path(d)/'run',True)
    def test_unknown_type(self):
        with self.assertRaises(ValueError):validate_entry({'kind':'external_prose'})

class PlanTests(Shared):
    def test_updates_and_counts(self):
        self.assertEqual(len(self.schedule['blocks']),36)
        for a in ARMS:
            entries=[b['entries'][a] for b in self.schedule['blocks']]
            self.assertEqual(sum(e['kind']=='proof' for e in entries),20)
            self.assertEqual(sum(e['kind']=='practice' for e in entries),16)
    def test_balanced_arm_order(self):
        self.assertEqual(sum(b['arm_order'][0]==ARMS[0] for b in self.schedule['blocks']),18)
    def test_common_practice_equal(self):
        for b in self.schedule['blocks']:
            if b['entries'][ARMS[0]]['kind']=='practice':self.assertEqual(b['entries'][ARMS[0]],b['entries'][ARMS[1]])
    def test_same_proof_permutations(self):
        for b in self.schedule['blocks']:
            if b['entries'][ARMS[0]]['kind']=='proof':
                r,s=[b['entries'][a]['source_row'] for a in ARMS]
                self.assertEqual(r['variant'],s['variant']);self.assertEqual(r['choice'],s['choice'])
    def test_regeneration(self):validate_schedule(self.schedule,self.rows)
    def test_changed_order(self):
        p=copy.deepcopy(self.schedule);p['blocks'].reverse()
        with self.assertRaises(ValueError):validate_schedule(p,self.rows)
    def test_no_performance_gate(self):
        p=copy.deepcopy(self.schedule);p['blocks'][0]['arm_order'].pop()
        with self.assertRaises(ValueError):validate_schedule(p,self.rows)
    def test_missing_training_arm(self):
        with self.assertRaises(ValueError):make_schedule([r for r in self.rows if r['arm']!=ARMS[1]])
    def test_practice_separate_from_evaluation(self):
        train={b['entries'][ARMS[0]]['source_case']['motif_id'] for b in self.schedule['blocks'] if b['entries'][ARMS[0]]['kind']=='practice'}
        self.assertFalse(train & {b['motif_id'] for b in evaluation.make_plan()['blocks']})

class EncodingTests(Shared):
    def test_single_eos(self):
        enc=encode_entry(FixtureTokenizer(),self.entry());self.assertEqual(enc['labels'].count(2),1)
    def test_prompt_mask(self):
        e=encode_entry(FixtureTokenizer(),self.entry());self.assertTrue(all(l==-100 for l,s in zip(e['labels'],e['segments']) if s==0))
    def test_action_supervised(self):
        e=encode_entry(FixtureTokenizer(),self.entry());self.assertTrue(all(l==t for l,t,s in zip(e['labels'],e['input_ids'],e['segments']) if s==2))
    def test_practice_has_no_rationale_targets(self):
        e=encode_entry(FixtureTokenizer(),practice_entry('care',True));self.assertNotIn(1,e['segments'])
    def test_no_silent_truncation(self):
        with self.assertRaises(ValueError):encode_entry(FixtureTokenizer(),self.entry(),10)
    def test_missing_template(self):
        t=FixtureTokenizer();t.chat_template=None
        with self.assertRaises(ValueError):encode_entry(t,self.entry())
    def test_eos_injected_in_targets(self):
        class Bad(FixtureTokenizer):
            def encode(self,s,**kw):return [2]+super().encode(s,**kw)
        with self.assertRaises(ValueError):encode_entry(Bad(),self.entry())
    def test_measure_all_eight_conditions(self):
        m=measure(FixtureTokenizer(),self.rows,self.schedule);self.assertEqual(m['status'],'TOKENIZER_PASS');self.assertEqual(len(m['all_conditions']),8)
        self.assertTrue(all(x['rows']==40 for x in m['all_conditions'].values()))
    def test_36_natural_eos_per_arm(self):
        m=measure(FixtureTokenizer(),self.rows,self.schedule);self.assertEqual({x['EOS_targets'] for x in m['scheduled_counts'].values()},{36})
    def test_context_fail_receipt(self):
        m=measure(FixtureTokenizer(),self.rows,self.schedule,context=10);self.assertEqual(m['status'],'TOKENIZER_FAIL');self.assertTrue(m['failures'])
    def test_tokenizer_files_required(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):tokenizer_identity(d,'0'*40)
    def test_bad_revision(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):tokenizer_identity(d,'main')

class OptimizerTests(Shared):
    def model(self):m=TinyPair();copy_initialization(m);return m
    def test_equal_initial_adapters(self):
        m=self.model();self.assertEqual(adapter_hash(m,ARMS[0]),adapter_hash(m,ARMS[1]))
    def test_only_active_trainable(self):
        m=self.model();activate(m,ARMS[0])
        self.assertTrue(all(('.'+ARMS[0]+'.') in n for n,p in m.named_parameters() if p.requires_grad))
    def test_update_isolated_and_base_frozen(self):
        m=self.model();other=adapter_hash(m,ARMS[1]);base=m.output.weight.detach().clone()
        opt=torch.optim.SGD(activate(m,ARMS[0]),lr=.1)
        x=torch.tensor([[4,5,6]]);loss=m(x).logits.square().mean();loss.backward();opt.step()
        self.assertEqual(adapter_hash(m,ARMS[1]),other);self.assertTrue(torch.equal(base,m.output.weight));self.assertIsNone(m.output.weight.grad)
    def test_backward_segmented_loss(self):
        from experiments.constitutional_reasoning_gym_v3.runtime import segmented_loss
        logits=torch.randn(1,5,16,requires_grad=True);labels=torch.tensor([[-100,-100,4,5,2]]);seg=torch.tensor([[0,0,1,2,2]])
        loss=segmented_loss(logits,labels,seg);loss.backward();self.assertTrue(torch.isfinite(logits.grad).all())
    def test_full_interleaved_training(self):
        import time
        with tempfile.TemporaryDirectory() as d:
            m=self.model();r=train_pair(m,FixtureTokenizer(),self.schedule,Path(d)/'training',time.monotonic()+40)
            self.assertEqual(r['status'],'COMPLETE',r);self.assertEqual(r['steps'],{a:36 for a in ARMS});self.assertTrue(r['adapters_saved'])
            self.assertTrue(all(r['initial_adapter_sha256'][a]!=r['final_adapter_sha256'][a] for a in ARMS))
            self.assertTrue((Path(d)/'training/half-steps.json').exists())
    def test_deadline_preserves_partial(self):
        with tempfile.TemporaryDirectory() as d:
            r=train_pair(self.model(),FixtureTokenizer(),self.schedule,Path(d)/'training',0,clock=lambda:1)
            self.assertEqual(r['status'],'PARTIAL');self.assertEqual(r['updates'],0);self.assertTrue(r['adapters_saved'])
    def test_gpu_requires_approval(self):
        with self.assertRaises(PermissionError):pilot('none','0'*40,'none','none','none')

class EvaluationTests(unittest.TestCase):
    def test_plan_counts(self):self.assertEqual(evaluation.make_plan()['records'],384)
    def test_training_arms_counterbalanced(self):
        p=evaluation.make_plan();self.assertEqual(sum(b['arm_order'].index(ARMS[0])<b['arm_order'].index(ARMS[1]) for b in p['blocks']),4)
    def generate(self,arm,msgs):return dilemmas.scripted('dutiful')(arm,msgs[-1]['content'])
    def test_perfect_policy_and_raw_receipts(self):
        with tempfile.TemporaryDirectory() as d:
            s=evaluation.run(evaluation.make_plan(),self.generate,Path(d)/'eval',1,clock=lambda:0)
            self.assertEqual(s['records'],384);self.assertTrue(all(a['correct']==128 for a in s['arms'].values()))
            self.assertEqual(s['platonic_minus_formal_bounds'],['0','0'])
    def test_timeout_complete_roster(self):
        with tempfile.TemporaryDirectory() as d:
            s=evaluation.run(evaluation.make_plan(),self.generate,Path(d)/'eval',0,clock=lambda:1)
            self.assertTrue(all(a['accuracy_bounds']==['0','1'] for a in s['arms'].values()));self.assertEqual(s['records'],384)
    def test_bad_format_observed_failure(self):
        with tempfile.TemporaryDirectory() as d:
            s=evaluation.run(evaluation.make_plan(),lambda a,m:'{"choice":true}',Path(d)/'eval',1,clock=lambda:0)
            self.assertTrue(all(a['malformed']==128 and a['unknown']==0 for a in s['arms'].values()))
    def test_tamper_and_missing_records_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'eval';p=evaluation.make_plan();evaluation.run(p,self.generate,out,1,clock=lambda:0)
            rows=[json.loads(x) for x in (out/'rollouts.jsonl').read_text().splitlines()]
            with self.assertRaises(ValueError):evaluation.score(p,rows[:-1])
            rows[0]['messages'][0]['content']='altered'
            with self.assertRaises(ValueError):evaluation.score(p,rows)
    def test_callback_cannot_see_answer_key(self):
        for b in evaluation.make_plan()['blocks']:
            for c in b['cells']:
                text=canon(evaluation.messages(c));self.assertNotIn('expected_choice',text)
                self.assertNotIn('Study necessity',text);self.assertNotIn('Reality has an intelligible ground',text)
    def test_partial_raw_text_survives_timeout(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'eval'
            s=evaluation.run(evaluation.make_plan(),lambda a,m:{'text':'{','generated_token_ids':[123],'timed_out':True},out,1,clock=lambda:0)
            self.assertTrue(all(a['unknown']==128 for a in s['arms'].values()))
            rows=[json.loads(x) for x in (out/'rollouts.jsonl').read_text().splitlines()]
            self.assertEqual(rows[0]['response']['text'],'{')
            self.assertEqual(rows[0]['response']['generated_token_ids'],[123])
    def test_training_selection_is_unchanged_by_evaluation(self):
        self.assertTrue(evaluation.make_plan()['frame_removed']);self.assertFalse(evaluation.make_plan()['final_test_access'])

class LaunchTests(unittest.TestCase):
    def test_syntax(self):
        script=Path(__file__).resolve().parents[1]/'scripts/silico_pilot.sh'
        self.assertEqual(subprocess.run(['bash','-n',str(script)]).returncode,0)
    def test_missing_inputs_stop_before_model(self):
        script=Path(__file__).resolve().parents[1]/'scripts/silico_pilot.sh'
        self.assertEqual(subprocess.run(['bash',str(script),'/missing','x','/missing','/missing','/missing']).returncode,66)
    def test_no_gpu_allocation_command(self):
        text=(Path(__file__).resolve().parents[1]/'scripts/silico_pilot.sh').read_text()
        self.assertIn('1190s',text);self.assertIn('--kill-after=10s',text);self.assertNotIn('curl ',text)

if __name__=='__main__':unittest.main()
