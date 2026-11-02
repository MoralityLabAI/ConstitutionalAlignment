"""Semantic QA software tests. Model rationale quality is not established here."""
from __future__ import annotations
import copy
from pathlib import Path
import json
import tempfile
import shutil
import unittest
from experiments.constitutional_reasoning_gym_v3.core import canon,make_twins,case_from
from experiments.constitutional_reasoning_gym_v3.data import FixtureTeacher
from experiments.constitutional_reasoning_gym_v3.v31.generator import produce_adaptive,export_v31
from experiments.constitutional_reasoning_gym_v3.semantic_review_v1.checks import text_flags,similarity_flags
from experiments.constitutional_reasoning_gym_v3.semantic_review_v1.review import (
    RUBRIC, build_audit,compile_reviews,validate_reviews,kappa,safe_manifest,verify_sft,_load_jsonl,
)

class TextRules(unittest.TestCase):
    def setUp(self):self.case=make_twins('delegation',0,0)[0]
    def test_false_called_unauthenticated(self):
        negative=next(k for k,v in self.case.facts.items() if v is False)
        f=text_flags(self.case,f'{negative} is unauthenticated evidence even though it is listed.')
        self.assertIn('authenticated_fact_described_as_unverified',{x['code'] for x in f})
    def test_untrusted_hint_not_flagged(self):
        self.assertEqual(text_flags(self.case,'An unauthenticated visitor hint may be ignored.'),[])
    def test_wrong_truth_value(self):
        negative=next(k for k,v in self.case.facts.items() if v is False)
        f=text_flags(self.case,f'{negative} is true and so the administrator may transfer.')
        self.assertIn('contradictory_fact_polarity',{x['code'] for x in f})
    def test_conditional_qualifier(self):
        negative=next(k for k,v in self.case.facts.items() if v is False)
        f=text_flags(self.case,f'If {negative} is true the authorization would change.')
        self.assertIn('counterfactual_truth_claim_requires_review',{x['code'] for x in f})
    def test_missing_evidence_id(self):
        f=text_flags(self.case,'e409 shows the release was permitted.')
        self.assertIn('unsupported_evidence_id',{x['code'] for x in f})
    def test_source_reference(self):
        f=text_flags(self.case,'Qur\'an 4:135 requires care in the ledger.')
        self.assertIn('source_reference_needs_validation',{x['code'] for x in f})
    def test_no_flags_for_signed_negative(self):
        negative=next(k for k,v in self.case.facts.items() if v is False)
        self.assertEqual(text_flags(self.case,f'{negative} is false in an authenticated record.'),[])
    def test_no_false_certification(self):
        flags=text_flags(self.case,'Correctness is automatic when the model says so.')
        self.assertEqual(flags,[]) # text scanner does not claim semantic completeness
    def test_near_repeats(self):
        class Dummy:
            pass
        self.assertEqual(similarity_flags([]),[])

class CorpusPreparation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        cls.base=Path(cls.tmp.name)
        produce_adaptive(FixtureTeacher(),cls.base/'generation',groups=4,max_repairs=0)
        export_v31(cls.base/'generation',cls.base/'sft',allow_fixture=True)
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def prepare(self,suffix='audit'):
        return build_audit(self.base/'generation',self.base/suffix,self.base/'sft',allow_fixture=True)
    def test_fixture_blocked_by_default(self):
        with self.assertRaises(ValueError):build_audit(self.base/'generation',self.base/'blocked')
    def test_pairs_and_source_audit(self):
        m=self.prepare('audit-pairs')
        self.assertEqual(m['review_queue_rows'],16)
        self.assertEqual(m['exportable_quartets'],4)
        self.assertEqual(m['generation_complete_records'],16)
        self.assertFalse(m['review_completed'])
        self.assertEqual(m['reporting_by_frame'],{'secular':8,'jinn':8})
        self.assertEqual(m['SFT_verified']['jinn_masked']['base_rows'],8)
    def test_reviewer_blinding(self):
        self.prepare('audit-blind')
        q=_load_jsonl(self.base/'audit-blind'/'review_queue.jsonl')
        self.assertEqual(len(q),16)
        self.assertNotIn('frame',q[0]);self.assertNotIn('group_id',q[0]);self.assertNotIn('authorized',q[0])
        self.assertIn('rationale',q[0]['candidate'])
        self.assertIn('charter',q[0]['context'])
        self.assertIn('invert_authenticated_record',q[0]['counterfactual_operation'])
        self.assertEqual(len({x['item_id'] for x in q}),16)
        self.assertEqual(len(_load_jsonl(self.base/'audit-blind'/'blind_key.jsonl')),16)
    def test_generation_remains_unchanged(self):
        before=(self.base/'generation'/'manifest.json').read_bytes()
        self.prepare('audit-readonly')
        self.assertEqual(before,(self.base/'generation'/'manifest.json').read_bytes())
    def test_no_overwrite(self):
        self.prepare('audit-dupe')
        with self.assertRaises(FileExistsError):self.prepare('audit-dupe')
    def test_bad_source_shard(self):
        dest=self.base/'badgen';dest.mkdir(exist_ok=True)
        manifest=json.loads((self.base/'generation'/'manifest.json').read_text())
        manifest['shards'][0]['path']='../raw-outside.jsonl.gz'
        (dest/'manifest.json').write_text(json.dumps(manifest));(dest/'contract.json').write_bytes((self.base/'generation'/'contract.json').read_bytes())
        with self.assertRaises(ValueError):safe_manifest(dest)
    def test_sft_tamper_refused(self):
        dest=self.base/'mutatedsft';dest.mkdir(exist_ok=True)
        for p in (self.base/'sft').iterdir():(dest/p.name).write_bytes(p.read_bytes())
        f=dest/'jinn_supervised.jsonl';f.write_text(f.read_text()+'{}\n')
        with self.assertRaises(ValueError):build_audit(self.base/'generation',self.base/'audit-tamper',dest,allow_fixture=True)
    def test_flags_do_not_approve_training(self):
        m=self.prepare('audit-claims')
        self.assertFalse(m['real_model_generated_corpus']);self.assertFalse(m['review_completed'])
        self.assertIsNone(m['tokenizer_counted_unique_rationale_tokens'])

class ReviewCompilation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.base=Path(cls.tmp.name)
        produce_adaptive(FixtureTeacher(),cls.base/'gen',groups=2,max_repairs=0)
        export_v31(cls.base/'gen',cls.base/'sft',allow_fixture=True)
        build_audit(cls.base/'gen',cls.base/'audit',cls.base/'sft',allow_fixture=True)
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def full_ratings(self,reviewer):
        rows=_load_jsonl(self.base/'audit'/'reviewer_A_template.jsonl')
        for r in rows:
            r.update(reviewer_id=reviewer,reviewer_kind='human',submitted=True)
            r['ratings']={k:2 for k in RUBRIC}
        return rows
    def write(self,root,rows):
        p=self.base/root;p.write_text(''.join(canon(x)+'\n' for x in rows));return p
    def test_two_reviewer_agreement(self):
        a=self.write('a.jsonl',self.full_ratings('A'));b=self.write('b.jsonl',self.full_ratings('B'))
        m=compile_reviews(self.base/'audit',a,b,self.base/'result0')
        self.assertEqual(m['reviewed_records'],8);self.assertEqual(m['records_for_adjudication'],0)
        self.assertIsNone(m['agreement_by_dimension']['fact_polarity']['kappa'])
        self.assertFalse(m['public_release_approved']);self.assertTrue(m['two_human_reviewers'])
    def test_reviewer_disagreement_requires_adjudication(self):
        a=self.write('c.jsonl',self.full_ratings('A'));brows=self.full_ratings('B')
        brows[0]['ratings']['fact_polarity']=0
        q=_load_jsonl(self.base/'audit'/'review_queue.jsonl')[0]
        brows[0]['evidence_quotes']={'fact_polarity':q['candidate']['rationale'][:30]}
        b=self.write('d.jsonl',brows)
        m=compile_reviews(self.base/'audit',a,b,self.base/'result1')
        self.assertEqual(m['records_for_adjudication'],1)
        self.assertEqual(len(m['motifs_requiring_adjudication']),1)
        self.assertEqual(len(_load_jsonl(self.base/'result1'/'adjudication_queue.jsonl')),1)
    def test_missing_rubric_refused(self):
        rows=self.full_ratings('A');rows[0]['ratings']['fact_polarity']=None
        with self.assertRaises(ValueError):validate_reviews(_load_jsonl(self.base/'audit'/'review_queue.jsonl'),rows)
    def test_missing_evidence_for_failure_refused(self):
        rows=self.full_ratings('A');rows[0]['ratings']['fact_polarity']=0
        with self.assertRaises(ValueError):validate_reviews(_load_jsonl(self.base/'audit'/'review_queue.jsonl'),rows)
    def test_same_reviewer_refused(self):
        a=self.write('same_a.jsonl',self.full_ratings('A'));b=self.write('same_b.jsonl',self.full_ratings('A'))
        with self.assertRaises(ValueError):compile_reviews(self.base/'audit',a,b,self.base/'result2')
    def test_model_ratings_not_called_human(self):
        arows=self.full_ratings('A');brows=self.full_ratings('B')
        for x in arows:x['reviewer_kind']='llm'
        for x in brows:x['reviewer_kind']='llm'
        a=self.write('la.jsonl',arows);b=self.write('lb.jsonl',brows)
        m=compile_reviews(self.base/'audit',a,b,self.base/'result3')
        self.assertFalse(m['two_human_reviewers']);self.assertFalse(m['public_release_approved'])
    def test_modified_audit_queue_rejected(self):
        copied=self.base/'audit_tampered'
        shutil.copytree(self.base/'audit',copied)
        q=copied/'review_queue.jsonl'
        q.write_text(q.read_text(encoding='utf-8')+'\n',encoding='utf-8')
        a=self.write('tamper_a.jsonl',self.full_ratings('A'))
        b=self.write('tamper_b.jsonl',self.full_ratings('B'))
        with self.assertRaises(ValueError):compile_reviews(copied,a,b,self.base/'result_tampered')
    def test_kappa_math(self):
        self.assertEqual(kappa([0,1,2],[0,1,2])['kappa'],'1')
        self.assertEqual(kappa([0,0],[0,0])['kappa'],None)

if __name__=='__main__':unittest.main()
