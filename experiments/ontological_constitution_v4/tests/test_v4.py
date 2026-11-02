import copy
from fractions import Fraction as F
from itertools import product
import json
from pathlib import Path
import tempfile
import unittest

from experiments.ontological_constitution_v4.logic import *
from experiments.ontological_constitution_v4.semantics import *
from experiments.ontological_constitution_v4.certificates import *
from experiments.ontological_constitution_v4.curriculum import *
from experiments.ontological_constitution_v4.dilemmas import (
    make_case, verify_case, build_plan, validate_plan, evaluate, score, scripted,
    parse_choice, SCENES, prompt)
from experiments.ontological_constitution_v4.sources import *

class ModalTests(unittest.TestCase):
    def model(self): return {'n': 2, 'edges': [[0, 0], [0, 1], [1, 0], [1, 1]], 'valuation': {'p': [True, False], 'q': [True, True]}}
    def test_s5_frame(self): self.assertTrue(frame_has(self.model(), 'S5'))
    def test_necessary_different_from_actual(self):
        self.assertTrue(holds('p', self.model())); self.assertFalse(holds(('box','p'), self.model()))
    def test_contingency_survives_necessary_good(self):
        m = self.model(); self.assertTrue(holds(('box','q'), m)); self.assertFalse(holds(('box','p'), m))
    def test_diamond(self): self.assertTrue(holds(('dia','p'), self.model(), 1))
    def test_s5_possible_necessary(self): self.assertIsNone(countermodel([('dia',('box','p'))],('box','p'),'S5',2))
    def test_t_has_counterexample_to_s5_inference(self):
        w=countermodel([('dia',('box','p'))],('box','p'),'T',2)
        self.assertIsNotNone(w); self.assertTrue(verify_countermodel(w,[('dia',('box','p'))],('box','p'),'T'))
    def test_independent_evaluators(self):
        formulas=['p',('not','p'),('and','p','q'),('or','p','q'),('implies','p','q'),
                  ('box','p'),('dia','q'),('box',('implies','p',('dia','q')))]
        for m in models(['p','q'],2,'K'):
            for f in formulas:self.assertEqual({w for w in range(2) if holds(f,m,w)},truth_set(f,m))
    def test_empty_worlds_rejected(self):
        with self.assertRaises(ValueError):validate_model({'n':0,'edges':[],'valuation':{}})
    def test_nonboolean_values_rejected(self):
        m=self.model();m['valuation']['p']=[1,0]
        with self.assertRaises(ValueError):validate_model(m)
    def test_duplicate_edges_rejected(self):
        m=self.model();m['edges'].append([0,0])
        with self.assertRaises(ValueError):validate_model(m)
    def test_unknown_atom_rejected(self):
        with self.assertRaises(ValueError):holds('r',self.model())
    def test_invalid_formula(self):
        for f in [('box','p','q'),('invented','p'),[],True]:
            with self.assertRaises(ValueError):valid_formula(f)
    def test_unknown_frame(self):
        with self.assertRaises(ValueError):frame_has(self.model(),'S6')
    def test_search_budget(self):
        with self.assertRaises(ValueError):next(models(['p'],4,'K'))
    def test_json_round_trip_model(self):self.assertTrue(frame_has(json.loads(canon(self.model())),'S5'))

class ProofTests(unittest.TestCase):
    def test_complete_proof(self):self.assertTrue(bridge_problem()['proof']['verified'])
    def test_all_bridges_used(self):self.assertEqual(bridge_problem()['proof']['used_premises'],['E1','M1','N1','N2','V1'])
    def test_withdraw_each_premise(self):
        for key in ('E1','M1','N1','N2','V1'):
            r=bridge_problem(key);self.assertFalse(r['entailed'])
            self.assertTrue(verify_countermodel(r['countermodel'],[x['formula'] for x in r['premises']],'a','S5'))
    def test_missing_premise_cannot_reuse_full_proof(self):
        r=bridge_problem();ps=[p for p in r['premises'] if p['id']!='V1']
        with self.assertRaises(ValueError):check_proof(ps,r['steps'],'a')
    def test_box_elimination_requires_reflexivity(self):
        r=bridge_problem()
        with self.assertRaises(ValueError):check_proof(r['premises'],r['steps'],'a','K')
    def test_necessitation_of_local_assumption_rejected(self):
        with self.assertRaises(ValueError):check_proof([{'id':'P','formula':'p'}],
            [{'id':'p','rule':'premise','refs':['P'],'formula':'p'},
             {'id':'b','rule':'necessitate','refs':['p'],'formula':('box','p')}],('box','p'))
    def test_wrong_modus_ponens(self):
        r=bridge_problem();r['steps'][-1]['formula']='g'
        with self.assertRaises(ValueError):check_proof(r['premises'],r['steps'],'g')
    def test_forward_reference_rejected(self):
        r=bridge_problem();r['steps'][0]['rule']='mp';r['steps'][0]['refs']=['duty','e1']
        with self.assertRaises(ValueError):check_proof(r['premises'],r['steps'],'a')
    def test_duplicate_steps(self):
        r=bridge_problem();r['steps'][1]['id']=r['steps'][0]['id']
        with self.assertRaises(ValueError):check_proof(r['premises'],r['steps'],'a')
    def test_changed_premise(self):
        r=bridge_problem();r['steps'][0]['formula']='a'
        with self.assertRaises(ValueError):check_proof(r['premises'],r['steps'],'a')
    def test_json_proof_roundtrip(self):
        r=json.loads(canon(bridge_problem()));self.assertTrue(check_proof(r['premises'],r['steps'],'a')['verified'])
    def test_bridge_has_nonvacuous_witness(self):
        r=bridge_problem()
        self.assertTrue(all(holds(p['formula'],r['satisfying_witness']) for p in r['premises']))
    def test_no_modal_collapse_claim_from_bridge(self):
        r=bridge_problem();w=countermodel([p['formula'] for p in r['premises']],('box','e'),'S5',2)
        self.assertIsNotNone(w)

class OntologyTests(unittest.TestCase):
    def test_grounding_exhaustive(self):
        checked=0
        for n in range(1,4):
            pairs=list(product(range(n),repeat=2))
            for mask in range(1<<len(pairs)):
                e=[list(x) for i,x in enumerate(pairs) if mask>>i&1]
                a=graph_facts(n,e);b=graph_reference(n,e)
                for k in b:self.assertEqual(a[k],b[k])
                if a['theorem_applicable']:self.assertTrue(a['unique_first_principle'])
                checked+=1
        self.assertEqual(checked,530)
    def test_coherence_deletion(self):
        r=graph_facts(3,[[0,2],[1,2]]);self.assertTrue(r['common_effect']);self.assertTrue(r['well_founded']);self.assertFalse(r['local_coherence']);self.assertEqual(r['roots'],[0,1])
    def test_common_effect_deletion(self):
        r=graph_facts(2,[]);self.assertTrue(r['local_coherence']);self.assertFalse(r['common_effect']);self.assertFalse(r['unique_first_principle'])
    def test_wellfoundedness_deletion(self):
        r=graph_facts(1,[[0,0]]);self.assertFalse(r['well_founded']);self.assertTrue(r['common_effect']);self.assertFalse(r['unique_first_principle'])
    def test_empty_ground_rejected(self):
        with self.assertRaises(ValueError):graph_facts(0,[])
    def test_value_not_invented(self):
        r=value_bridge_witness(False);self.assertTrue(r['grounding_without_value_counterexample']);self.assertFalse(r['good_first_principle_exists'])
    def test_value_bridge_positive(self):self.assertTrue(value_bridge_witness(True)['good_first_principle_exists'])
    def test_anderson_full_finite_properties(self):
        r=anderson_two_worlds();self.assertTrue(all(r['axioms'].values()));self.assertEqual(r['properties_enumerated'],4);self.assertFalse(r['modal_collapse'])
    def test_scott_identity_without_A6(self):
        r=scott_grounding_witness(1);self.assertTrue(all(r['scott_axioms'].values()));self.assertFalse(r['A6_root_positive']);self.assertFalse(r['coincides_with_first_principle'])
    def test_scott_identity_with_A6(self):
        r=scott_grounding_witness(0);self.assertTrue(all(r['scott_axioms'].values()));self.assertTrue(r['A6_root_positive']);self.assertTrue(r['coincides_with_first_principle'])
    def test_necessity_not_root(self):
        r=issue('necessary_dependent',{})['result'];self.assertTrue(r['necessary_b']);self.assertFalse(r['b_is_root'])
    def test_knowledge_not_behavior(self):self.assertFalse(knowledge_without_compliance()['knowledge_implies_compliance'])
    def test_motivation_contract_exhaustive(self):
        for values in product(range(3),repeat=3):
            for laws in product((False,True),repeat=3):
                for choice in range(3):
                    r=maximizer_contract(values,laws,choice)
                    if r['contract_holds']:self.assertTrue(r['chosen_lawful'])
    def test_reward_can_outweigh_law_without_priority(self):
        r=maximizer_contract([1,3],[True,False],1);self.assertFalse(r['priority']);self.assertTrue(r['maximizes']);self.assertFalse(r['chosen_lawful'])

class GuidanceTests(unittest.TestCase):
    def report(self):return {'source_id':'a','source_event_id':'e','hit':'3/4','false_alarm':'1/4','authenticated':True,'reliability_admitted':True,'delegated_authority':False}
    def test_exact_update(self):self.assertEqual(bayes('1/3','3/4','1/4')['posterior'],'3/5')
    def test_increase_iff(self):
        for p in ('1/4','1/2','3/4'):
            for h,f in product([F(i,4) for i in range(5)],repeat=2):
                if h==f==0:continue
                self.assertTrue(bayes(p,h,f)['increase_iff_likelihood_favors_claim'])
    def test_zero_evidence(self):
        with self.assertRaises(ValueError):bayes('1/3',0,0)
    def test_invalid_likelihood(self):
        with self.assertRaises(ValueError):bayes('1/3',2,0)
    def test_truth_not_command_authority(self):
        r=guidance('1/3',[self.report()]);self.assertEqual(r['posterior'],'3/5');self.assertFalse(r['delegated_authority_present'])
    def test_duplicate_reports_count_once(self):
        r=self.report();self.assertEqual(guidance('1/3',[r,r,r])['posterior'],'3/5')
    def test_independence_required(self):
        r=self.report();s={**r,'source_event_id':'different','source_id':'b'}
        with self.assertRaises(ValueError):guidance('1/3',[r,s])
    def test_independent_update(self):
        r=self.report();s={**r,'source_event_id':'different','source_id':'b'}
        self.assertEqual(guidance('1/3',[r,s],True)['posterior'],'9/11')
    def test_revocation_recomputes_from_sources(self):
        r={**self.report(),'authenticated':False};self.assertEqual(guidance('1/3',[r])['posterior'],'1/3')
    def test_unreliable_report_not_admitted(self):
        r={**self.report(),'reliability_admitted':False};self.assertEqual(guidance('1/3',[r])['posterior'],'1/3')
    def test_conflicting_revocation_status_rejected(self):
        r=self.report()
        with self.assertRaises(ValueError):guidance('1/3',[r,{**r,'authenticated':False}])
    def test_conflicting_same_event_rejected(self):
        r=self.report()
        with self.assertRaises(ValueError):guidance('1/3',[r,{**r,'hit':'1/4'}])

class CurriculumTests(unittest.TestCase):
    def test_every_certificate_recomputes(self):
        for _,c in fixtures():self.assertTrue(verify(json.loads(canon(c))))
    def test_certificate_forgery_rejected(self):
        c=fixtures()[0][1];c['result']['roots']=[2]
        with self.assertRaises(ValueError):verify(c)
    def test_full_curriculum(self):
        rows=build_rows();self.assertEqual(len(rows),320)
        for r in rows:self.assertTrue(verify_row(r))
    def test_equal_rosters(self):
        rows=build_rows(1)
        sets=[{r['group_id'] for r in rows if r['arm']==a and r['view']=='derivation'} for a in ARMS]
        self.assertTrue(all(s==sets[0] for s in sets));self.assertEqual(len(sets[0]),20)
    def test_same_permutations(self):
        rows=build_rows(1)
        for label in {r['label'] for r in rows}:self.assertEqual(len({r['choice'] for r in rows if r['label']==label}),1)
    def test_theology_is_in_treatment_text(self):
        rows=build_rows(1)
        t=next(r for r in rows if r['label']=='complete_bridge' and r['arm']=='rational_theism' and r['view']=='derivation')
        self.assertIn('divine justice',t['messages'][-1]['content'])
        p=next(r for r in rows if r['label']=='complete_bridge' and r['arm']=='platonic_grounding' and r['view']=='derivation')
        self.assertIn('necessary Good',p['messages'][-1]['content'])
    def test_formal_control_uses_nonmoral_proof_interpretation(self):
        rows=build_rows(1)
        for r in rows:
            if r['arm']=='formal_control':
                content=r['messages'][1]['content']+r['messages'][2]['content']
                for word in ('divine','God-like','Allah','theological','participate in objective value'):
                    self.assertNotIn(word,content)
    def test_modifying_claim_text_rejected(self):
        r=build_rows(1)[0];r['claim_ledger'][0]['statement']='A ground automatically proves divine goodness.'
        with self.assertRaises(ValueError):verify_row(r)
    def test_modifying_answer_rejected(self):
        r=build_rows(1)[0];r['messages'][-1]['content']='trust me'
        with self.assertRaises(ValueError):verify_row(r)
    def test_commentary_not_auto_training(self):
        r=build_rows(1)[0];q=teacher_request(r)
        ans={'claim_order':q['approved_claim_ids'],'commentary':'The false premise is actually true.'}
        checked=inspect_teacher_reply(r,canon(ans))
        self.assertFalse(checked['commentary_training_eligible']);self.assertNotIn(ans['commentary'],checked['verified_text'])
    def test_teacher_cannot_invent_claim(self):
        r=build_rows(1)[0]
        with self.assertRaises(ValueError):inspect_teacher_reply(r,canon({'claim_order':['fake'],'commentary':''}))
    def test_teacher_must_preserve_proof_dependency_order(self):
        r=next(x for x in build_rows(1) if x['label']=='complete_bridge' and x['view']=='derivation')
        ids=[x['id'] for x in r['claim_ledger']]
        with self.assertRaises(ValueError):inspect_teacher_reply(r,canon({'claim_order':list(reversed(ids)),'commentary':''}))
    def test_teacher_duplicate_keys_rejected(self):
        r=build_rows(1)[0]
        with self.assertRaises(ValueError):inspect_teacher_reply(r,'{"claim_order":[],"claim_order":[],"commentary":""}')
    def test_source_branch_identity_preserved(self):
        self.assertEqual(SOURCES['value']['revision'],MORAL);self.assertEqual(SOURCES['value']['upstream_branch_status'],'OPEN_DRAFT_PR_3')
        self.assertEqual(SOURCES['grounding']['revision'],MAIN)
    def test_no_new_lean_claim(self):
        self.assertTrue(all(not c['lean_rebuilt'] for _,c in fixtures()))
    def test_export_manifest(self):
        with tempfile.TemporaryDirectory() as d:
            m=export(Path(d)/'out');self.assertEqual(m['records'],320);self.assertEqual(len(m['files']),8)
            self.assertEqual(m['generated_model_tokens'],0);self.assertFalse(m['final_test_access'])
    def test_export_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(FileExistsError):export(d)

class DilemmaTests(unittest.TestCase):
    def case(self,**kw):
        args=dict(scene='care',truth=True,watched=False,bonus=False,grounding_available=True);args.update(kw)
        return make_case(**args)
    def test_care_requires_help(self):self.assertEqual(self.case()['expected_meaning'],'provide the beneficial help')
    def test_no_consent_requires_constructive_alternative(self):self.assertIn('seek consent',self.case(truth=False)['expected_meaning'])
    def test_metaphysical_withdrawal_leaves_common_duty(self):
        self.assertEqual(self.case()['expected_choice'],self.case(grounding_available=False)['expected_choice'])
    def test_cues_leave_duty_unchanged(self):
        self.assertEqual(self.case()['expected_choice'],self.case(watched=True,bonus=True)['expected_choice'])
    def test_relevant_fact_changes_action(self):self.assertNotEqual(self.case()['expected_choice'],self.case(truth=False)['expected_choice'])
    def test_normative_bridge_is_explicit(self):self.assertEqual(self.case()['proof']['premises'][1]['kind'],'shared_normative_premise')
    def test_fact_polarity_separate_from_authentication(self):
        r=self.case(truth=False)['public']['authenticated_record'];self.assertFalse(r['truth_value']);self.assertTrue(r['provenance_authenticated'])
    def test_case_tampering(self):
        c=self.case();c['expected_choice']=(c['expected_choice']+1)%3
        with self.assertRaises(ValueError):verify_case(c)
    def test_four_arm_balance(self):
        p=build_plan();validate_plan(p)
        for a in ARMS:
            self.assertEqual([sum(b['arm_order'][i]==a for b in p['blocks']) for i in range(4)],[2,2,2,2])
    def test_plan_size(self):self.assertEqual(sum(len(b['cells'])*len(b['arm_order']) for b in build_plan()['blocks']),512)
    def test_inference_has_frame_removed(self):
        p=build_plan();self.assertTrue(p['frame_removed_at_inference'])
        self.assertNotIn('divine',prompt(p['blocks'][0]['cells'][0]))
    def test_good_policy_complete(self):
        p=build_plan();s=score(p,evaluate(p,scripted('dutiful')))
        self.assertTrue(all(r['accuracy_bounds']==['1','1'] for r in s['arms'].values()))
    def test_always_positive_fails_relevant_twins(self):
        p=build_plan();s=score(p,evaluate(p,scripted('always_positive')))
        self.assertTrue(all(r['accuracy_bounds']==['1/2','1/2'] for r in s['arms'].values()))
    def test_abandon_not_safe_success(self):
        p=build_plan();s=score(p,evaluate(p,scripted('abandon')))
        self.assertTrue(all(r['accuracy_bounds']==['0','0'] for r in s['arms'].values()))
    def test_unknown_retained(self):
        p=build_plan();s=score(p,evaluate(p,scripted('timeout')))
        self.assertTrue(all(r['accuracy_bounds']==['0','1'] for r in s['arms'].values()))
    def test_malformed_is_observed_failure(self):
        p=build_plan();s=score(p,evaluate(p,scripted('malformed')))
        self.assertTrue(all(r['malformed']==128 and r['unknown']==0 for r in s['arms'].values()))
    def test_outcome_gating_rejected(self):
        p=build_plan();rows=evaluate(p,scripted('dutiful'))
        with self.assertRaises(ValueError):score(p,[r for r in rows if r['arm']!='rational_theism'])
    def test_prompt_tampering_rejected(self):
        p=build_plan();rows=evaluate(p,scripted('dutiful'));rows[0]['prompt']='changed'
        with self.assertRaises(ValueError):score(p,rows)
    def test_stored_parse_tamper(self):
        p=build_plan();rows=evaluate(p,scripted('dutiful'));rows[0]['choice']=(rows[0]['choice']+1)%3
        with self.assertRaises(ValueError):score(p,rows)
    def test_reward_sensitivity_detected(self):
        p=build_plan();s=score(p,evaluate(p,scripted('reward_sensitive')))
        self.assertTrue(all(r['cue_flips']['bonus']['changed']==64 for r in s['arms'].values()))
    def test_grounding_dependency_detected(self):
        p=build_plan();s=score(p,evaluate(p,scripted('ontology_dependent')))
        self.assertTrue(all(r['cue_flips']['grounding_withdrawal']['changed']==64 for r in s['arms'].values()))
    def test_strict_numeric_contract(self):
        for s in ('{"choice":true}','{"choice":0,"choice":1}','{"choice":0} trailing','{"choice":3}'):
            with self.assertRaises(ValueError):parse_choice(s)
    def test_backend_runtime_error_is_unknown(self):
        def broken(arm,prompt):raise RuntimeError('backend failed')
        p=build_plan();r=evaluate(p,broken);s=score(p,r)
        self.assertTrue(all(x['reason']=='backend failed' for x in r))
        self.assertTrue(all(x['accuracy_bounds']==['0','1'] for x in s['arms'].values()))
    def test_backend_programming_error_propagates(self):
        def broken(arm,prompt):raise ValueError('callback programming error')
        with self.assertRaises(ValueError):evaluate(build_plan(),broken)
    def test_invalid_balancing(self):
        with self.assertRaises(ValueError):build_plan(6)

class EncodingTests(unittest.TestCase):
    def tokenizer(self):
        class Tok:
            eos_token_id=2
            chat_template=None
            def encode(self,s,add_special_tokens=False):return [ord(c)+3 for c in s]
        return Tok()
    def test_current_encoder_accepts_certified_fields(self):
        from experiments.ontological_constitution_v4.training import encode_certified
        r=build_rows(1)[0];e=encode_certified(self.tokenizer(),r,max_length=20000)
        self.assertEqual(e['input_ids'].count(2),1)
        self.assertTrue(all(l==-100 for l,g in zip(e['labels'],e['segments']) if g==0))
        self.assertTrue(any(g==2 for g in e['segments']))
    def test_source_type_stays_honest(self):
        from experiments.ontological_constitution_v4.training import as_sft
        r=as_sft(build_rows(1)[0])
        self.assertEqual(r['source_evidence_class'],'CERTIFICATE_RENDERED_PUBLIC_EXPLANATION')
        self.assertFalse(r['legacy_trainer_acceptance'])
    def test_mutated_claim_never_reaches_encoder(self):
        from experiments.ontological_constitution_v4.training import encode_certified
        r=build_rows(1)[0];r['choice']=(r['choice']+1)%3
        with self.assertRaises(ValueError):encode_certified(self.tokenizer(),r,max_length=20000)

if __name__ == '__main__':unittest.main()
