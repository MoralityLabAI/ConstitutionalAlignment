from __future__ import annotations
import copy
import json
import os
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path
from unittest.mock import patch
from experiments.ontological_transfer_bench_v1.cases import FAMILIES, make_case, verify_case, prompt, parse, scripted, canon
from experiments.ontological_transfer_bench_v1.plan import make_plan,verify_plan,assignments,public_cases,cells
from experiments.ontological_transfer_bench_v1.score import score,record_for
from experiments.ontological_transfer_bench_v1.run import run_fixture,run_endpoint,run_hf,run_hf_group,_safe_endpoint,read_records,_check_resumption,extract_final,adapter_files,_chat


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


if __name__=='__main__':unittest.main()
