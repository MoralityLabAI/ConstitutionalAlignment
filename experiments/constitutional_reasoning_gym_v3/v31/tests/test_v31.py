"""CPU-only regression and adversarial fixtures for the v3.1 repair pipeline."""
from __future__ import annotations
import json
import tempfile
import unittest
from pathlib import Path
from experiments.constitutional_reasoning_gym_v3.v31.audit import audit_candidate,polarity_errors,correction_targets
from experiments.constitutional_reasoning_gym_v3.v31.generator import (LegacySource, build_request,produce_adaptive,export_v31,planned_jobs)
from experiments.constitutional_reasoning_gym_v3.v31.compare import compare
from experiments.constitutional_reasoning_gym_v3.core import Case,make_twins,canon,FRAMES,sha,case_from
from experiments.constitutional_reasoning_gym_v3.data import FixtureTeacher,produce,read_records,training_cases,request,validate_candidate


class WrongCounterfactual(FixtureTeacher):
    def generate_many(self,requests):
        rows=super().generate_many(requests)
        for req,row in zip(requests,rows):
            if req['stage']=='draft':
                obj=json.loads(row['text']); obj['counterfactual_choice']=obj['choice']
                row['text']=canon(obj)
        return rows

class WrongPolarity(FixtureTeacher):
    def generate_many(self,requests):
        rows=super().generate_many(requests)
        for req,row in zip(requests,rows):
            if req['stage'] in ('draft','rewrite'):
                c=case_from(req['case']);false=[k for k,v in c.facts.items() if not v]
                if false:
                    obj=json.loads(row['text'])
                    obj['rationale']='The authenticated record '+c.pivot+' is pivotal. Record '+false[0]+' authenticated_value:false is unauthenticated. '+obj['rationale']
                    row['text']=canon(obj)
        return rows

class DoNotRepair(FixtureTeacher):
    def generate_many(self,requests):
        rows=super().generate_many(requests)
        for req,row in zip(requests,rows):
            if req['stage'] in ('draft','targeted_repair'):
                obj=json.loads(row['text']);obj['counterfactual_choice']=obj['choice'];row['text']=canon(obj)
        return rows

class DeadlineAfterCalls(FixtureTeacher):
    def __init__(self,fail_after=6):self.n=0;self.fail_after=fail_after
    def generate_many(self,requests):
        if self.n>=self.fail_after:raise TimeoutError('synthetic worker cutoff')
        self.n+=1
        return super().generate_many(requests)

class FaultyLegacyFinal(FixtureTeacher):
    def generate_many(self,requests):
        rows=super().generate_many(requests)
        for req,row in zip(requests,rows):
            if req['stage']=='rewrite' and req['frame']=='jinn':
                o=json.loads(row['text']);o['counterfactual_choice']=o['choice'];row['text']=canon(o)
        return rows

class StrictBudgetTeacher(FixtureTeacher):
    evidence_class='MODEL_GENERATED'
    def generate_many(self,requests):
        rows=super().generate_many(requests)
        for row in rows:row['output_tokens']=20
        return rows


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.c=make_twins('delegation',0,0)[0]
        self.raw=FixtureTeacher().generate_many([request(self.c,'secular','difficult_advice','draft')])[0]['text']
    def test_valid_draft(self):self.assertTrue(audit_candidate(self.c,self.raw)['accepted'])
    def test_bad_cf_rejected(self):
        o=json.loads(self.raw);o['counterfactual_choice']=o['choice']
        self.assertIn('wrong_counterfactual',audit_candidate(self.c,canon(o))['errors'])
    def test_false_is_auth_negative(self):
        o=json.loads(self.raw);false=next(k for k,v in self.c.facts.items() if not v)
        o['rationale']='Record '+false+' authenticated_value:false is an authenticated negative. '+o['rationale']
        self.assertTrue(audit_candidate(self.c,canon(o))['accepted'])
    def test_false_vs_unauthenticated(self):
        o=json.loads(self.raw);false=next(k for k,v in self.c.facts.items() if not v)
        o['rationale']='Record '+false+' authenticated_value:false is unauthenticated. '+o['rationale']
        self.assertIn('authenticated_false_called_unauthenticated:'+false,audit_candidate(self.c,canon(o))['errors'])
    def test_false_record_not_verified(self):
        false=next(k for k,v in self.c.facts.items() if not v)
        self.assertIn('authenticated_false_called_unauthenticated:'+false,polarity_errors(self.c,'The '+false+' record is not verified.'))
    def test_untrusted_hint_exception(self):
        self.assertEqual(polarity_errors(self.c,'The untrusted visitor hint is not authenticated.'),[])
    def test_ambiguous_record_unauthenticated(self):
        self.assertIn('ambiguous_authentication_status',polarity_errors(self.c,'The record is unauthenticated.'))
    def test_wrong_pivot_missing(self):
        o=json.loads(self.raw);o['rationale']=o['rationale'].replace(self.c.pivot,'this thing')
        self.assertIn('pivotal_evidence_not_discussed',audit_candidate(self.c,canon(o))['errors'])
    def test_invalid_json(self):self.assertFalse(audit_candidate(self.c,'{"choice":0,"choice":1}')['accepted'])
    def test_semantic_scope(self):
        audit=audit_candidate(self.c,self.raw)
        self.assertFalse(audit['free_text_semantics_verified']);self.assertTrue(audit['human_semantic_review_required'])
    def test_targeted_feedback_truth(self):
        bad=json.loads(self.raw);bad['counterfactual_choice']=bad['choice']
        targets=correction_targets(self.c,audit_candidate(self.c,canon(bad)))
        self.assertEqual(targets['verified_choice_original'],self.c.expected())
        self.assertEqual(targets['verified_choice_counterfactual'],self.c.counterfactual().expected())
        self.assertEqual(targets['actual_pivotal_record']['authenticated'],True)
        self.assertEqual(targets['actual_pivotal_record']['truth_value'],self.c.facts[self.c.pivot])
    def test_initial_request_no_answer_key(self):
        prompt=build_request(self.c,'secular','difficult_advice','draft')['messages'][-1]['content']
        self.assertNotIn('verified_choice_original',prompt)
        self.assertNotIn('DETERMINISTIC_VERIFIER_FEEDBACK',prompt)
    def test_repair_request_contains_feedback(self):
        audit=audit_candidate(self.c,'bad')
        prompt=build_request(self.c,'secular','difficult_advice','targeted_repair','bad',audit,1)['messages'][-1]['content']
        self.assertIn('verified_choice_counterfactual',prompt)
        self.assertIn('authenticated negative',prompt)
    def test_eval_rejected(self):
        c=make_twins('delegation',4,0,'calibration')[0]
        with self.assertRaises(ValueError):build_request(c,'jinn','difficult_advice','draft')


class GenerationTests(unittest.TestCase):
    def test_disjoint_generation_windows(self):
        left={c.group_id for c,f,m in planned_jobs(6,41,0)}
        right={c.group_id for c,f,m in planned_jobs(26,41,6)}
        self.assertEqual((len(left),len(right),len(left & right)),(6,26,0))
    def test_invalid_window_rejected(self):
        with self.assertRaises(ValueError):planned_jobs(4,41,-1)
        with self.assertRaises(ValueError):planned_jobs(2,41,99999)
    def test_one_call_when_valid(self):
        with tempfile.TemporaryDirectory() as d:
            r=produce_adaptive(FixtureTeacher(),d,groups=2)
            self.assertEqual((r['planned_records'],r['new_calls'],r['accepted_rewrites']),(8,8,8))
            self.assertEqual(r['paired_accepted_motifs'],2)
    def test_five_to_one_fixture_calls(self):
        with tempfile.TemporaryDirectory() as d:
            d=Path(d);v3=produce(FixtureTeacher(),d/'old',groups=2,rounds=2)
            new=produce_adaptive(FixtureTeacher(),d/'new',groups=2)
            self.assertEqual(v3['new_calls'],40);self.assertEqual(new['new_calls'],8)
            report=compare(d/'old',d/'new')
            self.assertEqual(report['matched_case_frame_records'],8)
            self.assertEqual(report['old']['v31_polarity_screen_accepted'],8)
            self.assertEqual(report['new']['v31_polarity_screen_accepted'],8)
    def test_exact_feedback_repair(self):
        with tempfile.TemporaryDirectory() as d:
            r=produce_adaptive(WrongCounterfactual(),d,groups=2)
            self.assertEqual(r['new_calls'],16)
            self.assertEqual(r['draft_accepted'],0)
            self.assertEqual(r['new_targeted_repair_successes'],8)
            self.assertEqual(r['paired_accepted_motifs'],2)
    def test_polarity_regeneration(self):
        with tempfile.TemporaryDirectory() as d:
            r=produce_adaptive(WrongPolarity(),d,groups=2)
            self.assertEqual(r['paired_accepted_motifs'],2)
            self.assertGreater(r['new_targeted_repair_successes'],0)
    def test_ending_at_failed_repair(self):
        with tempfile.TemporaryDirectory() as d:
            r=produce_adaptive(DoNotRepair(),d,groups=1,max_repairs=1)
            self.assertEqual(r['accepted_rewrites'],0)
            self.assertEqual(r['paired_accepted_motifs'],0)
            self.assertEqual(r['unresolved_error_codes']['wrong_counterfactual'],4)
    def test_no_repair_budget(self):
        with tempfile.TemporaryDirectory() as d:
            r=produce_adaptive(WrongCounterfactual(),d,groups=1,max_repairs=0)
            self.assertEqual(r['new_calls'],4);self.assertEqual(r['accepted_rewrites'],0)
    def test_resume_no_new_calls(self):
        with tempfile.TemporaryDirectory() as d:
            a=produce_adaptive(FixtureTeacher(),d,groups=2)
            b=produce_adaptive(FixtureTeacher(),d,groups=2)
            self.assertEqual(b['new_calls'],0)
            self.assertEqual(a['shards'],b['shards'])
            self.assertEqual(a['accepted_rewrites'],b['accepted_rewrites'])
    def test_resume_repair_idempotent(self):
        with tempfile.TemporaryDirectory() as d:
            a=produce_adaptive(WrongCounterfactual(),d,groups=2)
            b=produce_adaptive(WrongCounterfactual(),d,groups=2)
            self.assertEqual(b['new_calls'],0)
            self.assertEqual(a['shards'],b['shards'])
    def test_contract_drift(self):
        with tempfile.TemporaryDirectory() as d:
            produce_adaptive(FixtureTeacher(),d,groups=1)
            with self.assertRaises(ValueError):produce_adaptive(FixtureTeacher(),d,groups=2)
    def test_semantic_motif_coverage(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);produce_adaptive(FixtureTeacher(),root/'raw',groups=8)
            out=export_v31(root/'raw',root/'sft',allow_fixture=True)
            self.assertEqual(out['paired_cases'],16)
            self.assertEqual({v['rows'] for v in out['arms'].values()},{20})
            self.assertTrue(out['human_semantic_review_required'])
    def test_fixture_export_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            r=Path(d);produce_adaptive(FixtureTeacher(),r/'raw',groups=1)
            with self.assertRaises(ValueError):export_v31(r/'raw',r/'sft')
    def test_strict_output_tokens(self):
        with tempfile.TemporaryDirectory() as d:
            r=produce_adaptive(StrictBudgetTeacher(),d,groups=1,token_cap=4000,max_new_tokens=100)
            self.assertEqual(r['actual_output_tokens'],80)
            self.assertEqual(r['status'],'COMPLETE')
    def test_budget_stops_before_calls(self):
        with tempfile.TemporaryDirectory() as d:
            r=produce_adaptive(StrictBudgetTeacher(),d,groups=2,token_cap=100,max_new_tokens=100)
            self.assertEqual(r['status'],'PARTIAL')
            self.assertEqual(r['new_calls'],0)
            self.assertEqual(r['completed_records'],0)
    def test_failing_export_reaudit(self):
        with tempfile.TemporaryDirectory() as d:
            d=Path(d);produce_adaptive(FixtureTeacher(),d/'raw',groups=2)
            manifest=d/'raw'/'manifest.json';m=json.loads(manifest.read_text())
            m['shards'][0]['sha256']='bad';manifest.write_text(json.dumps(m))
            with self.assertRaises(ValueError):export_v31(d/'raw',d/'sft',True)
    def test_no_legacy_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);produce(FixtureTeacher(),root/'old',groups=1)
            with self.assertRaises(ValueError):produce_adaptive(FixtureTeacher(),root/'old',groups=1,legacy_root=root/'old')
    def test_source_manifest_rejects_eval(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);produce(FixtureTeacher(),root/'old',groups=1)
            p=root/'old'/'contract.json';c=json.loads(p.read_text());c['scenario_split']='calibration';p.write_text(json.dumps(c))
            with self.assertRaises(ValueError):produce_adaptive(FixtureTeacher(),root/'new',groups=1,legacy_root=root/'old')
    def test_source_shard_tamper_detected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);m=produce(FixtureTeacher(),root/'old',groups=1)
            (root/'old'/'shards'/m['shards'][0]['path']).write_bytes(b'evil')
            with self.assertRaises(ValueError):produce_adaptive(FixtureTeacher(),root/'new',groups=1,legacy_root=root/'old')


class LegacyTests(unittest.TestCase):
    def test_import_all_completed_records(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);old=produce(FixtureTeacher(),root/'old',groups=2,rounds=2)
            new=produce_adaptive(FixtureTeacher(),root/'new',groups=2,legacy_root=root/'old')
            self.assertEqual(old['completed_records'],8)
            self.assertEqual(new['new_calls'],0)
            self.assertEqual(new['origin_counts']['LEGACY_COMPLETED_ROW'],8)
            self.assertEqual(new['paired_accepted_motifs'],2)
            self.assertTrue(new['legacy_source']['journal_sha256'])
    def test_recovery_of_partial_journal_drafts(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            old=produce(DeadlineAfterCalls(6),root/'old',groups=2,rounds=2,batch_size=4)
            self.assertEqual((old['status'],old['completed_records'],old['calls_total']),('PARTIAL',4,24))
            new=produce_adaptive(FixtureTeacher(),root/'new',groups=2,legacy_root=root/'old')
            self.assertEqual(new['new_calls'],0)
            self.assertEqual(new['paired_accepted_motifs'],2)
            self.assertEqual(new['origin_counts']['LEGACY_PARTIAL_JOURNAL'],4)
            self.assertEqual(new['origin_counts']['LEGACY_COMPLETED_ROW'],4)
    def test_earlier_good_revision_beats_failed_final(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);old=produce(FaultyLegacyFinal(),root/'old',groups=2,rounds=2)
            self.assertLess(old['accepted_rewrites'],8)
            new=produce_adaptive(FixtureTeacher(),root/'new',groups=2,legacy_root=root/'old')
            self.assertEqual(new['new_calls'],0)
            self.assertEqual(new['paired_accepted_motifs'],2)
            self.assertGreater(new['origin_counts'].get('LEGACY_RECOVERED_EARLIER_STAGE',0),0)
    def test_polarity_failed_source_repaired_only_where_needed(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            old=produce(WrongPolarity(),root/'old',groups=2,rounds=2)
            new=produce_adaptive(FixtureTeacher(),root/'new',groups=2,legacy_root=root/'old')
            self.assertGreater(new['new_targeted_repair_successes'],0)
            self.assertLess(new['new_calls'],8)
            self.assertEqual(new['paired_accepted_motifs'],2)
    def test_archive_stays_unchanged(self):
        from experiments.constitutional_reasoning_gym_v3.core import file_sha
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);produce(FixtureTeacher(),root/'old',groups=1,rounds=2)
            original={p.relative_to(root/'old').as_posix():file_sha(p) for p in (root/'old').rglob('*') if p.is_file()}
            produce_adaptive(FixtureTeacher(),root/'new',groups=1,legacy_root=root/'old')
            after={p.relative_to(root/'old').as_posix():file_sha(p) for p in (root/'old').rglob('*') if p.is_file()}
            self.assertEqual(original,after)
    def test_mismatch_teacher_class(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);produce(FixtureTeacher(),root/'old',groups=1)
            with self.assertRaises(ValueError):produce_adaptive(StrictBudgetTeacher(),root/'new',groups=1,legacy_root=root/'old')
    def test_bad_case_assignment(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);produce(FixtureTeacher(),root/'old',groups=1,seed=41)
            with self.assertRaises(ValueError):produce_adaptive(FixtureTeacher(),root/'new',groups=1,seed=42,legacy_root=root/'old')

if __name__=='__main__':unittest.main()

class CanaryShapeTests(unittest.TestCase):
    def test_17_of_24_original_repair_7_with_7_calls(self):
        jobs=planned_jobs(6,41)
        bad={(jobs[i][0].case_id,jobs[i][1]) for i in (12,13,14,16,17,20,21)}
        class CanaryShape(FixtureTeacher):
            def generate_many(self,requests):
                result=super().generate_many(requests)
                for req,row in zip(requests,result):
                    if req['stage'] in ('draft','rewrite') and (req['case']['case_id'],req['frame']) in bad:
                        obj=json.loads(row['text']);obj['counterfactual_choice']=obj['choice']
                        row['text']=canon(obj)
                return result
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            old=produce(CanaryShape(),root/'v30',groups=6,rounds=2)
            self.assertEqual((old['completed_records'],old['accepted_rewrites']),(24,17))
            first=export_v31 if False else None
            from experiments.constitutional_reasoning_gym_v3.data import export_sft
            old_sft=export_sft(root/'v30',root/'v30_sft',True)
            self.assertEqual(old_sft['accepted_semantic_motifs'],3)
            new=produce_adaptive(FixtureTeacher(),root/'v31',groups=6,legacy_root=root/'v30')
            self.assertEqual((new['completed_records'],new['accepted_rewrites'],new['paired_accepted_motifs']),(24,24,6))
            self.assertEqual(new['new_calls'],7)
            self.assertEqual(new['new_targeted_repair_successes'],7)
            cmp=compare(root/'v30',root/'v31')
            self.assertEqual(cmp['old']['v31_polarity_screen_accepted'],17)
            self.assertEqual(cmp['new']['v31_polarity_screen_accepted'],24)

class ModelCallIntegrityTests(unittest.TestCase):
    def test_model_token_ids_are_verified(self):
        class BadIds(StrictBudgetTeacher):
            def generate_many(self,requests):
                out=super().generate_many(requests)
                for r in out:r['raw_generated_token_ids']=[4]
                return out
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):produce_adaptive(BadIds(),d,groups=1,token_cap=4000,max_new_tokens=100)

    def test_runtime_abort_preserves_journal_and_manifest(self):
        class BackendCrash(FixtureTeacher):
            def generate_many(self,requests):raise RuntimeError('mock GPU OOM')
        with tempfile.TemporaryDirectory() as d:
            m=produce_adaptive(BackendCrash(),d,groups=1)
            self.assertEqual(m['status'],'ABORTED')
            self.assertTrue((Path(d)/'journal.sqlite3').is_file())
            self.assertEqual(m['completed_records'],0)
