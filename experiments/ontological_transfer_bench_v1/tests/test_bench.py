from __future__ import annotations
import copy
import json
import os
import sys
import types
from contextlib import nullcontext
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path
from unittest.mock import patch
from experiments.ontological_transfer_bench_v1.cases import FAMILIES, make_case, verify_case, prompt, parse, scripted, canon
from experiments.ontological_transfer_bench_v1.plan import make_plan,verify_plan,assignments,spread_assignments,public_cases,cells
from experiments.ontological_transfer_bench_v1.score import score,record_for
from experiments.ontological_transfer_bench_v1.run import run_fixture,run_endpoint,run_hf,run_hf_group,_safe_endpoint,read_records,_check_resumption,extract_final,adapter_files,_chat,decode_hf_final,_prepare_generation_inputs,preflight_hf_tokenizer


class CaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.smoke=make_plan('smoke')
        cls.full=make_plan('full')

    def test_eight_distinct_untrained_families(self):
        self.assertEqual(len(FAMILIES),8)
        self.assertTrue({'confluence','modal_identity','value_bridge','authenticated_guidance','unjust_command'}<=set(FAMILIES))
    def test_prescribed_roster_counts(self):
        self.assertEqual(self.smoke['records_per_arm'],64)
        self.assertEqual(self.full['records_per_arm'],512)
        self.assertEqual(len(self.full['blocks']),16)
        self.assertEqual(self.full['assigned_records_all_arms'],2048)
    def test_smoke_strength_2_pairwise_orthogonal(self):
        a=cells('smoke')
        for i in range(5):
            for j in range(i+1,5):
                self.assertEqual({(x[i],x[j]) for x in a},{(False,False),(False,True),(True,False),(True,True)})
    def test_paired_smoke_has_true_one_factor_interventions(self):
        p=make_plan('paired_smoke')
        self.assertEqual(p['records_per_arm'],48)
        self.assertEqual(p['assigned_records_all_arms'],192)
        self.assertNotEqual(p['sha256'],self.smoke['sha256'])
        for block in p['blocks']:
            by_flags={tuple(c['flags'].values()) for c in block['cells']}
            origin=(False,)*5
            self.assertIn(origin,by_flags)
            for factor in range(5):
                self.assertIn(tuple(i==factor for i in range(5)),by_flags)
        self.assertEqual(len(cells('smoke')),8)
        self.assertEqual(make_plan('smoke'),self.smoke)

    def test_nonempty_factorial(self):
        self.assertEqual(len(set(cells('full'))),32)
        self.assertEqual(len(set(cells('smoke'))),8)
    def test_same_plan_is_deterministic(self):
        self.assertEqual(make_plan('smoke'),self.smoke)
        self.assertEqual(make_plan('full'),self.full)
        self.assertNotEqual(self.smoke['sha256'],self.full['sha256'])
    def test_seeds_are_distinct(self):
        self.assertNotEqual(make_plan('smoke',seed=3)['sha256'],self.smoke['sha256'])
    def test_invalid_seed_and_motif_count(self):
        for n in (-1,2**63,'3'):
            with self.subTest(n=n),self.assertRaises(ValueError):make_plan(seed=n)
        with self.assertRaises(ValueError):make_plan(motifs_per_family=0)
    def test_case_sha_fails_tampering(self):
        for field in ('public','answer','flags'):
            c=copy.deepcopy(self.full['blocks'][0]['cells'][0]);c[field]['forged']='yes'
            with self.subTest(field=field),self.assertRaises(ValueError):verify_case(c)
    def test_plan_rejects_reordered_cases(self):
        p=copy.deepcopy(self.full);p['blocks'][0]['cells'][0],p['blocks'][0]['cells'][1]=p['blocks'][0]['cells'][1],p['blocks'][0]['cells'][0]
        with self.assertRaises(ValueError):verify_plan(p)
    def test_plan_rejects_arm_injection(self):
        p=copy.deepcopy(self.full);p['arms'].append('new_teacher')
        with self.assertRaises(ValueError):verify_plan(p)
    def test_prompt_has_no_private_oracle_fields(self):
        c=self.smoke['blocks'][0]['cells'][0]
        s=prompt(c)
        self.assertNotIn('"answer":',s)
        self.assertNotIn('"expected_choice":',s)
        self.assertIn('"choice"',s)
        self.assertIn('"reason_code"',s)
    def test_budgeted_schedule_spreads_all_families_and_three_qwen_arms(self):
        arms=['base','formal_control','platonic_grounding']
        spread=list(spread_assignments(self.smoke,arms))
        ordinary=list(assignments(self.smoke,arms))
        self.assertEqual({a['assignment_id'] for a in spread},{a['assignment_id'] for a in ordinary})
        self.assertEqual(len(spread),192)
        self.assertEqual({a['family'] for a in spread[:24]},set(FAMILIES))
        self.assertEqual({a['arm'] for a in spread[:24]},set(arms))
    def test_public_export_excludes_answers(self):
        data=public_cases(self.smoke)
        self.assertEqual(len(data),64)
        self.assertNotIn('answer',data[0])
        self.assertNotIn('sha256',data[0])
    def test_all_case_combinations_have_valid_oracle(self):
        for family in FAMILIES:
            for truth in (False,True):
                for ontology in (False,True):
                    for m in (0,1):
                        c=make_case(family,m,truth,False,False,False,ontology)
                        with self.subTest(family=family,truth=truth,ontology=ontology,m=m):
                            self.assertTrue(verify_case(c))
                            self.assertEqual(parse(scripted(c)),c['answer'])
    def test_answer_ids_vary_across_motifs(self):
        values=set()
        for m in range(16):
            c=make_case('victim_claim',m,True,False,False,False,False)
            values.add(c['answer']['choice'])
        self.assertGreater(len(values),2)
    def test_true_and_false_give_different_action_somewhere(self):
        for family in FAMILIES:
            c=make_case(family,0,False,False,False,False,False)
            d=make_case(family,0,True,False,False,False,False)
            self.assertNotEqual(c['answer'],d['answer'],family)
    def test_cue_invariance_in_non_theological_families(self):
        for family in set(FAMILIES)-{'modal_identity','value_bridge'}:
            c=make_case(family,0,True,False,False,False,False)
            d=make_case(family,0,True,True,True,True,True)
            self.assertEqual(c['answer'],d['answer'],family)
    def test_value_bridge_truth_table(self):
        a={}
        for truth in (False,True):
            for ontology in (False,True):
                c=make_case('value_bridge',0,truth,False,False,False,ontology)
                a[(truth,ontology)]=c['public']['actions'][c['answer']['choice']]['text']
        self.assertEqual(len(set(a.values())),4)
    def test_modal_inconsistency_with_A6(self):
        c=make_case('modal_identity',0,False,False,False,False,True)
        self.assertIn('conflict',c['public']['actions'][c['answer']['choice']]['text'])
        d=make_case('modal_identity',0,False,False,False,False,False)
        self.assertIn('grounded',d['public']['actions'][d['answer']['choice']]['text'])
    def test_confluence_two_origins_countermodel(self):
        c=make_case('confluence',0,False,False,False,False,False)
        self.assertIn('Two distinct',c['public']['actions'][c['answer']['choice']]['text'])
    def test_guidance_authentication_not_double_count(self):
        c=make_case('authenticated_guidance',0,True,False,False,False,False)
        self.assertIn('3/5',c['public']['actions'][c['answer']['choice']]['text'])
        d=make_case('authenticated_guidance',0,False,False,False,False,False)
        self.assertIn('1/3',d['public']['actions'][d['answer']['choice']]['text'])
    def test_justice_capability_changes_construction(self):
        a=make_case('victim_claim',0,True,False,False,False,False)
        b=make_case('victim_claim',1,True,False,False,False,False)
        self.assertIn('now',a['public']['actions'][a['answer']['choice']]['text'])
        self.assertIn('arrange',b['public']['actions'][b['answer']['choice']]['text'])
    def test_signed_false_is_authenticated(self):
        c=make_case('signed_correction',0,False,False,False,False,False)
        self.assertIs(c['public']['scenario']['signed_report']['authenticated'],True)
        self.assertIs(c['public']['scenario']['signed_report']['value'],False)
    def test_parse_rejects_malformed(self):
        invalid=['{"choice":0}', '{"choice":true,"reason_code":0}', '{"choice":0,"reason_code":0,"reason_code":1}',
                 '{"choice":0,"reason_code":0,"extra":1}', 'not json', '[]', '{"choice":4,"reason_code":0}',
                 '{"choice":1.0,"reason_code":2}','```json\n{"choice":1,"reason_code":1}\n```']
        for raw in invalid:
            with self.subTest(raw=raw),self.assertRaises((ValueError,TypeError)):parse(raw)


class ScoringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.plan=make_plan('smoke')
    def records(self, arm='platonic_grounding',policy='oracle'):
        lookup={c['case_id']:c for b in self.plan['blocks'] for c in b['cells']}
        return [record_for(self.plan,a,scripted(lookup[a['case_id']],policy),model_id='fixture')
                for a in assignments(self.plan,[arm])]
    def test_perfect_action_reason(self):
        report=score(self.plan,self.records(),['platonic_grounding'])['arms']['platonic_grounding']
        self.assertEqual((report['assigned'],report['joint_correct'],report['reason_correct']), (64,64,64))
        self.assertEqual(report['joint_accuracy_bounds'],['1','1'])
    def test_motif_reported_as_unit(self):
        r=score(self.plan,self.records(),['platonic_grounding'])
        self.assertEqual(len(r['arms']['platonic_grounding']['by_motif']),8)
        self.assertFalse(r['independent_test_claimed'])
    def test_reason_bypass_is_observed_failure(self):
        r=score(self.plan,self.records(policy='reason_bypass'),['platonic_grounding'])['arms']['platonic_grounding']
        self.assertEqual((r['choice_correct'],r['reason_correct'],r['joint_correct']),(64,0,0))
    def test_bonus_actor_fails_incentive_invariance(self):
        r=score(self.plan,self.records(policy='bonus_sensitive'),['platonic_grounding'])['arms']['platonic_grounding']
        self.assertLess(r['joint_correct'],64)
    def test_truth_sensitivity(self):
        r=score(self.plan,self.records(),['platonic_grounding'])['arms']['platonic_grounding']
        self.assertEqual(r['paired_cue_diagnostics']['bonus']['spurious_flips'],0)
    def test_full_factorial_has_counterbalanced_flips(self):
        p=make_plan('full',motifs_per_family=1)
        lookup={c['case_id']:c for b in p['blocks'] for c in b['cells']}
        rows=[record_for(p,a,scripted(lookup[a['case_id']])) for a in assignments(p,['platonic_grounding'])]
        r=score(p,rows,['platonic_grounding'])['arms']['platonic_grounding']
        for cue in ('watched','bonus','training'):
            self.assertEqual(r['paired_cue_diagnostics'][cue]['spurious_flips'],0)
            self.assertEqual(r['paired_cue_diagnostics'][cue]['observed_pairs'],128)
        self.assertGreater(r['paired_cue_diagnostics']['ontology']['expected_changing_pairs'],0)
        self.assertEqual(r['paired_cue_diagnostics']['ontology']['missed_expected_flips'],0)
    def test_missing_assignment_bounds(self):
        r=score(self.plan,self.records()[:-1],['platonic_grounding'])['arms']['platonic_grounding']
        self.assertEqual(r['unknown'],1)
        self.assertEqual(r['joint_accuracy_bounds'],['63/64','1'])
    def test_malformed_output_preserved(self):
        rows=self.records();rows[-1]=record_for(self.plan,{k:rows[-1][k] for k in ('assignment_id','arm','case_id','case_sha256','motif_id','family','prompt')},'{}')
        r=score(self.plan,rows,['platonic_grounding'])['arms']['platonic_grounding']
        self.assertEqual((r['malformed'],r['joint_correct']),(1,63))
    def test_bad_parse_claim_rejected(self):
        rows=self.records();rows[0]['status']='malformed'
        with self.assertRaises(ValueError):score(self.plan,rows,['platonic_grounding'])
    def test_response_integrity_rejects_metadata_edit(self):
        rows=self.records();rows[0]['metadata']['tampered']=1
        with self.assertRaisesRegex(ValueError,'integrity'):score(self.plan,rows,['platonic_grounding'])
    def test_response_integrity_rejects_answer_edit(self):
        rows=self.records();rows[0]['raw']='{"choice":0,"reason_code":0}'
        with self.assertRaisesRegex(ValueError,'integrity'):score(self.plan,rows,['platonic_grounding'])
    def test_duplicate_response_rejected(self):
        rows=self.records();rows.append(rows[0])
        with self.assertRaises(ValueError):score(self.plan,rows,['platonic_grounding'])
    def test_unknown_response_with_fake_raw_rejected(self):
        rows=self.records();rows[0]['status']='unknown'
        with self.assertRaises(ValueError):score(self.plan,rows,['platonic_grounding'])
    def test_prompt_substitution_fails_closed(self):
        rows=self.records();rows[0]['prompt']='a new prompt'
        with self.assertRaises(ValueError):score(self.plan,rows,['platonic_grounding'])
    def test_id_substitution_fails_closed(self):
        rows=self.records();rows[0]['assignment_id']='unknown'
        with self.assertRaises(ValueError):score(self.plan,rows,['platonic_grounding'])
    def test_other_plan_fails_closed(self):
        p=make_plan(seed=5);rows=self.records()
        with self.assertRaises(ValueError):score(p,rows,['platonic_grounding'])
    def test_unrun_arms_are_not_incorrect_baselines(self):
        r=score(self.plan,self.records())
        self.assertEqual(list(r['arms']),['platonic_grounding'])
        self.assertIn('intellect3',r['unrun_arms'])
        self.assertEqual(r['paired_motif_comparisons'],[])
    def test_no_model_records_does_not_create_fake_scores(self):
        with self.assertRaises(ValueError):score(self.plan,[])
    def test_unknown_model_comparison_suppresses_bootstrap(self):
        a=self.records('platonic_grounding')
        b=self.records('intellect3')[:-1]
        r=score(self.plan,a+b)
        cmp=r['paired_motif_comparisons']
        self.assertEqual(cmp[0]['status'],'INSUFFICIENT_COMPARABLE_RESPONSES')
    def test_all_arms_perfect_matched_delta_zero(self):
        rows=[]
        for arm in self.plan['arms']:rows.extend(self.records(arm))
        r=score(self.plan,rows)
        self.assertEqual(len(r['paired_motif_comparisons']),3)
        self.assertTrue(all(c['mean_difference']==0 for c in r['paired_motif_comparisons']))
    def test_fixture_files_and_resumption(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'fixture.jsonl'
            r=run_fixture(self.plan,p)
            self.assertEqual(r['arms']['platonic_grounding']['joint_correct'],64)
            self.assertEqual(len(read_records(p)),64)
            run_fixture(self.plan,p)
            self.assertEqual(len(read_records(p)),64)
            with self.assertRaises(ValueError):_check_resumption(p,self.plan,'base')
    def test_error_becomes_unknown(self):
        rows=[]
        for a in assignments(self.plan,['intellect3']):
            rows.append(record_for(self.plan,a,None,error='simulated timeout'))
        r=score(self.plan,rows,['intellect3'])['arms']['intellect3']
        self.assertEqual(r['unknown'],64)
        self.assertEqual(r['joint_accuracy_bounds'],['0','1'])


class GatewayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.plan=make_plan('smoke')
    def test_final_extraction_after_reasoning_marker(self):
        self.assertEqual(extract_final('<think>analysis</think> {"choice":2,"reason_code":1}'),'{"choice":2,"reason_code":1}')
        self.assertEqual(extract_final('  {"choice":2,"reason_code":1}  '),'{"choice":2,"reason_code":1}')
        self.assertNotEqual(extract_final('<think>unfinished'),'{"choice":2,"reason_code":1}')
    def test_token_level_terminal_marker_decoding_preserves_raw(self):
        class Tokenizer:
            eos_token_id=99
            unk_token_id=-1
            def convert_tokens_to_ids(self, name):
                return {'<|im_end|>':99,'<|endoftext|>':98}.get(name,-1)
            def decode(self, ids, skip_special_tokens=False):
                return ''.join({1:'{"choice":3,"reason_code":2}',2:' extra',99:'<|im_end|>',98:'<|endoftext|>'}[x] for x in ids)
        t=Tokenizer()
        cleaned, full, ends=decode_hf_final(t,[1,99])
        self.assertEqual(cleaned,'{"choice":3,"reason_code":2}')
        self.assertEqual(full,'{"choice":3,"reason_code":2}<|im_end|>')
        self.assertEqual(ends,[99])
        self.assertEqual(decode_hf_final(t,[1,99,98])[2],[99,98])
        self.assertEqual(decode_hf_final(t,[1,99,2])[0],full+' extra')
        self.assertEqual(decode_hf_final(t,[1,2,99])[0],'{"choice":3,"reason_code":2} extra')
        with self.assertRaises(TypeError):decode_hf_final(t,['not-a-token'])
    def test_different_terminal_token_renders_are_not_scrubbed(self):
        class Tokenizer:
            eos_token_id=99
            unk_token_id=-1
            def convert_tokens_to_ids(self, name):return -1
            def decode(self, ids, skip_special_tokens=False):
                return ''.join({1:'{"choice":0,"reason_code":0}',42:'<|unrecognized|>',99:'<|im_end|>'}[x] for x in ids)
        t=Tokenizer()
        self.assertEqual(decode_hf_final(t,[1,42])[0],'{"choice":0,"reason_code":0}<|unrecognized|>')
        self.assertEqual(decode_hf_final(t,[1,99])[0],'{"choice":0,"reason_code":0}')

    def test_adapters_require_real_safetensors(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)
            with self.assertRaises(ValueError):adapter_files(p)
            (p/'adapter_config.json').write_text('{}')
            (p/'adapter_model.safetensors').write_bytes(b'canary')
            self.assertEqual(len(adapter_files(p)['adapter_model.safetensors']),64)
    def test_joint_hf_requires_explicit_approval_before_weights(self):
        with self.assertRaises(PermissionError):run_hf_group(self.plan,Path('/tmp/unused'),base_model='x',model_revision='a'*40,
                             formal_adapter='/not/mounted',platonic_adapter='/not/mounted')
    def test_endpoint_chat_preserves_original_reasoning_and_parses_final(self):
        class FakeResponse:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,*args):return self.payload
        obj={'id':'response-1','choices':[{'message':{'content':'<think>model generated analysis</think> {"choice":1,"reason_code":2}',
                            'reasoning_content':'separate reasoning'},'finish_reason':'stop'}],
             'usage':{'prompt_tokens':12,'completion_tokens':22,'completion_tokens_details':{'reasoning_tokens':9}}}
        class FakeURL:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self):return json.dumps(obj).encode()
        with patch('experiments.ontological_transfer_bench_v1.run.request.urlopen',return_value=FakeURL()):
            raw,meta=_chat('https://example.org/chat/completions','dummy','model','prompt',100,15)
        self.assertEqual(parse(raw),{'choice':1,'reason_code':2})
        self.assertIn('<think>',meta['raw_assistant_content'])
        self.assertEqual(meta['reasoning_tokens'],9)
    def test_endpoint_requires_approval(self):
        with self.assertRaises(PermissionError):run_endpoint(self.plan,Path('/dev/null'),'intellect3',model_id='PrimeIntellect/INTELLECT-3',base_url='https://example.org/v1/chat/completions',approval=False,max_requests=1,total_output_cap=2000)
    def test_hf_requires_approval_before_importing_torch(self):
        with self.assertRaises(PermissionError):run_hf(self.plan,Path('/dev/null'),arm='base',base_model='dummy',model_revision='a'*40)
    def test_https_boundary(self):
        for url in ('http://api.example.org/v1/chat/completions','file:///etc/passwd','http://127.0.0.2/v1/chat/completions','https://admin:pass@example.org/v1/chat/completions'):
            with self.subTest(url=url),self.assertRaises(ValueError):_safe_endpoint(url)
        self.assertEqual(_safe_endpoint('http://localhost:8000/v1/chat/completions'),'http://localhost:8000/v1/chat/completions')
    def test_endpoint_caps_and_missing_key_fail_before_network(self):
        with patch.dict(os.environ,{},clear=True):
            with self.assertRaises(ValueError):run_endpoint(self.plan,Path('/tmp/unused'),'intellect3',model_id='PrimeIntellect/INTELLECT-3',base_url='https://example.org/v1/chat/completions',approval=True,max_requests=1,total_output_cap=2000)
    def test_endpoint_never_exceeds_assignment_count(self):
        with self.assertRaises(ValueError):run_endpoint(self.plan,Path('/tmp/unused'),'intellect3',model_id='X',base_url='https://example.org/v1/chat/completions',approval=True,max_requests=1000,total_output_cap=2048)
    def test_nonpositive_token_budget_is_rejected(self):
        with self.assertRaises(ValueError):run_endpoint(self.plan,Path('/tmp/unused'),'intellect3',model_id='X',base_url='https://example.org/v1/chat/completions',approval=True,max_requests=1,total_output_cap=0)


class GenerationInterfaceRegressionTests(unittest.TestCase):
    """Reproduce the BatchEncoding positional-generate failure without a GPU."""
    class FakeTensor:
        def __init__(self, seq):
            self.data=list(seq)
            self.shape=(1,len(seq))
        def to(self, device):
            self.device=device
            return self

    class FakeOutput:
        def __init__(self, tokens):
            self.tokens=list(tokens)
        def __getitem__(self, key):
            if not isinstance(key,tuple) or key[0]!=0 or not isinstance(key[1],slice):
                raise AssertionError('expected [0, prompt_length:] tensor slice')
            return GenerationInterfaceRegressionTests.FakeTokens(self.tokens[key[1]])

    class FakeTokens:
        def __init__(self, vals):self.vals=list(vals)
        def __len__(self):return len(self.vals)
        def detach(self):return self
        def cpu(self):return self
        def tolist(self):return list(self.vals)

    class FakeBatchEncoding(dict):
        def to(self, device):
            for v in self.values():v.to(device)
            return self

    class FakeTokenizer:
        is_fast=True
        chat_template='qwen-native-template'
        eos_token_id=99
        def __init__(self):self.calls=[]
        def apply_chat_template(self,messages,**kwargs):
            self.calls.append(kwargs)
            if kwargs.get('return_dict') is not True:
                raise AssertionError('tokenizer must return named tensors')
            return GenerationInterfaceRegressionTests.FakeBatchEncoding({
                'input_ids':GenerationInterfaceRegressionTests.FakeTensor([4,5,6]),
                'attention_mask':GenerationInterfaceRegressionTests.FakeTensor([1,1,1]),
            })
        def decode(self,tokens,skip_special_tokens=False):
            return '{"choice":0,"reason_code":0}'

    class FakeModel:
        device='cpu'
        def __init__(self):self.calls=[]
        def eval(self):return self
        def disable_adapter(self):return nullcontext()
        def set_adapter(self,name):self.current_adapter=name
        def load_adapter(self,*args,**kwargs):return None
        def generate(self,*args,**kwargs):
            if args:raise AssertionError('BatchEncoding was supplied positionally')
            if not {'input_ids','attention_mask','max_new_tokens','do_sample'}<=kwargs.keys():
                raise AssertionError('missing named inputs')
            ids=kwargs['input_ids']
            mask=kwargs['attention_mask']
            if ids.shape!=(1,3) or mask.shape!=(1,3):
                raise AssertionError('bad named tensor shape')
            self.calls.append(kwargs)
            return GenerationInterfaceRegressionTests.FakeOutput(ids.data+[7,8])

    def test_normalization_accepts_tensor_and_batch_encoding(self):
        ids=self.FakeTensor([1,2,3])
        inputs,length=_prepare_generation_inputs(ids,'cpu')
        self.assertEqual((set(inputs),length),({'input_ids'},3))
        encoded=self.FakeBatchEncoding({'input_ids':self.FakeTensor([1,2,3]),
                                        'attention_mask':self.FakeTensor([1,1,1])})
        result,length=_prepare_generation_inputs(encoded,'cuda:0')
        self.assertEqual(set(result),{'input_ids','attention_mask'})
        self.assertEqual(result['input_ids'].device,'cuda:0')
        self.assertEqual(length,3)

    def test_normalization_rejects_missing_invalid_and_mismatched_tensors(self):
        cases=[{},[],{'input_ids':[1,2,3]},
               {'input_ids':self.FakeTensor([])},
               {'input_ids':self.FakeTensor([1,2]),
                'attention_mask':self.FakeTensor([1])},
               {'input_ids':self.FakeTensor([1,2]),'unexpected':[1]}]
        for case in cases:
            with self.subTest(case=str(case)),self.assertRaises((TypeError,ValueError)):
                _prepare_generation_inputs(case,'cpu')

    def fake_backend(self):
        tokenizer=self.FakeTokenizer()
        model=self.FakeModel()
        hf=types.ModuleType('transformers')
        hf.AutoTokenizer=types.SimpleNamespace(from_pretrained=lambda *a,**kw:tokenizer)
        hf.AutoModelForCausalLM=types.SimpleNamespace(from_pretrained=lambda *a,**kw:model)
        peft=types.ModuleType('peft')
        peft.PeftModel=types.SimpleNamespace(from_pretrained=lambda m,*a,**kw:m)
        torch=types.ModuleType('torch')
        torch.bfloat16='bf16'
        torch.inference_mode=nullcontext
        torch.cuda=types.SimpleNamespace(is_available=lambda:False)
        return tokenizer,model,{'transformers':hf,'peft':peft,'torch':torch}

    def test_real_tokenizer_preflight_uses_batch_encoding_without_weights(self):
        plan=make_plan('smoke')
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            tokenizer,model,modules=self.fake_backend()
            def do_not_load_model(*args,**kwargs):
                raise AssertionError('preflight attempted to load weights')
            modules['transformers'].AutoModelForCausalLM.from_pretrained=do_not_load_model
            with patch.dict(sys.modules,modules):
                receipt=preflight_hf_tokenizer(plan,base_model=root/'retained',
                   model_revision='a'*40,out=root/'preflight.json',thinking=False)
            self.assertEqual(receipt['status'],'TOKENIZER_ONLY_PRE_GPU_PASS')
            self.assertFalse(receipt['model_weights_loaded'])
            self.assertFalse(receipt['GPU_allocated'])
            self.assertEqual(receipt['prompt_tokens'],3)
            self.assertEqual(receipt['input_tensor_names'],['attention_mask','input_ids'])
            self.assertEqual(json.loads((root/'preflight.json').read_text()),receipt)
            self.assertEqual(len(model.calls),0)
            self.assertTrue(tokenizer.calls[0]['return_dict'])
            with patch.dict(sys.modules,modules):
                with self.assertRaises(FileExistsError):
                    preflight_hf_tokenizer(plan,base_model=root/'retained',
                       model_revision='a'*40,out=root/'preflight.json')

    def test_grouped_hf_generation_receives_keyword_tensors_and_persists_rows(self):
        plan=make_plan('smoke')
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);paths=[]
            for name in ('formal','platonic'):
                d=root/name;d.mkdir()
                (d/'adapter_config.json').write_text('{}')
                (d/'adapter_model.safetensors').write_bytes(b'dummy')
                paths.append(d)
            tokenizer,model,modules=self.fake_backend()
            with patch.dict(sys.modules,modules):
                result=run_hf_group(plan,root/'qwen.jsonl',base_model=root/'base',
                   model_revision='a'*40,formal_adapter=paths[0],platonic_adapter=paths[1],
                   approval=True,max_assignments=3,max_new_tokens=16,max_wall_seconds=300)
            rows=read_records(root/'qwen.jsonl')
            self.assertEqual(len(rows),3)
            self.assertEqual(len(model.calls),3)
            self.assertTrue(all(x['status']!='unknown' for x in rows))
            self.assertTrue(all(x['metadata']['input_tokens']==3 for x in rows))
            self.assertTrue(all(x['metadata']['output_tokens']==2 for x in rows))
            self.assertTrue(all(x['metadata']['raw_generated_token_ids']==[7,8] for x in rows))
            self.assertEqual(result['reported_model_revision'],'a'*40)
            self.assertTrue(all(c['return_dict'] for c in tokenizer.calls))

    def test_single_hf_generation_uses_same_keyword_input_contract(self):
        plan=make_plan('smoke')
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);tokenizer,model,modules=self.fake_backend()
            with patch.dict(sys.modules,modules):
                run_hf(plan,root/'base.jsonl',arm='base',base_model=root/'base',
                       model_revision='a'*40,approval=True,max_requests=1,max_new_tokens=16)
            rows=read_records(root/'base.jsonl')
            self.assertEqual(len(rows),1)
            self.assertEqual(len(model.calls),1)
            self.assertEqual(rows[0]['metadata']['raw_generated_token_ids'],[7,8])
            self.assertTrue(tokenizer.calls[0]['return_dict'])


if __name__=='__main__':unittest.main()
class PosthocDiagnosticTests(unittest.TestCase):
    def test_posthoc_is_separate_from_frozen_strict_score(self):
        from experiments.ontological_transfer_bench_v1.posthoc import diagnose
        plan=make_plan('paired_smoke')
        a=next(iter(assignments(plan,['formal_control'])))
        c=next(c for b in plan['blocks'] for c in b['cells'] if c['case_id']==a['case_id'])
        good=scripted(c)
        marked=good+'<|im_end|>'
        r=record_for(plan,a,marked,metadata={'raw_model_text':marked})
        d=diagnose(plan,[r]);self.assertEqual(d['original_strict_score']['arms']['formal_control']['malformed'],1)
        self.assertEqual(d['one_terminal_marker_diagnostic']['arms']['formal_control']['joint_correct'],1)
        self.assertEqual(d['audit']['valid_after_one_terminal_marker'],1)
        self.assertFalse(d['modifies_original_records'])
        self.assertEqual(r['raw'],marked)
    def test_posthoc_rejects_prose_after_suffix(self):
        from experiments.ontological_transfer_bench_v1.posthoc import diagnose
        plan=make_plan('paired_smoke')
        a=next(iter(assignments(plan,['formal_control'])))
        c=next(c for b in plan['blocks'] for c in b['cells'] if c['case_id']==a['case_id'])
        raw=scripted(c)+'<|im_end|> notes'
        r=record_for(plan,a,raw,metadata={'raw_model_text':raw})
        d=diagnose(plan,[r])
        self.assertEqual(d['audit']['valid_after_one_terminal_marker'],0)
        self.assertEqual(d['one_terminal_marker_diagnostic']['arms']['formal_control']['malformed'],1)

