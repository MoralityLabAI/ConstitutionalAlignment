"""Independent post-hoc analysis: strict validator, token stripping, paired contingency, arm restriction."""
from __future__ import annotations
import unittest
from experiments.ontological_transfer_bench_v1 import generation
from experiments.ontological_transfer_bench_v1.analyze_posthoc import (analyze, final_text, lenient_json, paired,
                                                                        strict_json, wilson)
from experiments.ontological_transfer_bench_v1.cases import canon, scripted
from experiments.ontological_transfer_bench_v1.plan import make_plan, assignments
from experiments.ontological_transfer_bench_v1.run import run_hf_group
from experiments.ontological_transfer_bench_v1.score import record_for

TMAP = {248044: '<|endoftext|>', 248046: '<|im_end|>', 248069: '</think>'}


class ValidatorTests(unittest.TestCase):
    def test_strict_rules(self):
        self.assertEqual(strict_json('{"choice": 1, "reason_code": 3}'), {'choice': 1, 'reason_code': 3})
        for bad in ('{"choice": true, "reason_code": 1}', '{"choice": 4, "reason_code": 1}', '{"choice": 1}',
                    '{"choice": 1, "reason_code": 1, "x": 2}', '{"choice": 1, "choice": 2, "reason_code": 1}',
                    '```json\n{"choice": 1, "reason_code": 1}\n```', 'text {"choice": 1, "reason_code": 1}', ''):
            self.assertIsNone(strict_json(bad), bad)

    def test_lenient_takes_last_fence_only_as_exploratory(self):
        t = 'a\n```json\n{"choice": 0, "reason_code": 0}\n```\nb\n```json\n{"choice": 2, "reason_code": 1}\n```'
        self.assertEqual(lenient_json(t), {'choice': 2, 'reason_code': 1})
        self.assertIsNone(strict_json(t))
        self.assertIsNone(lenient_json('{"choice": 2, "reason_code": 1} trailing words'))

    def test_final_text_strips_only_matching_trailing_terminals(self):
        self.assertEqual(final_text('{"choice":1,"reason_code":1}<|im_end|>', [5, 248046], TMAP), ('{"choice":1,"reason_code":1}', 1))
        self.assertEqual(final_text('x<|im_end|>', [5, 6], TMAP), ('x<|im_end|>', 0))
        self.assertEqual(final_text('x<|im_end|>', [5, 248046], {248046: '<|endoftext|>'})[1], 0)

    def test_wilson_bounds(self):
        lo, hi = wilson(16, 21)
        self.assertTrue(0.5 < lo < 0.76 < hi < 0.95)
        self.assertIsNone(wilson(0, 0))


def rows_for(plan, arm, n, fence=False, wrong=False):
    cases = {c['case_id']: c for b in plan['blocks'] for c in b['cells']}
    out = []
    for a in list(assignments(plan, [arm]))[:n]:
        c = cases[a['case_id']]
        ans = dict(c['answer'])
        if wrong:ans['choice'] = (ans['choice'] + 1) % 4
        body = canon(ans)
        if fence:body = 'Reasoning...\n```json\n' + body + '\n```'
        text = body + '<|im_end|>'
        out.append(record_for(plan, a, text, metadata={'raw_model_text': text, 'raw_generated_token_ids': [7, 248046]}))
    return out


class AnalysisTests(unittest.TestCase):
    def setUp(self):
        self.plan = make_plan('smoke')

    def test_strict_zero_but_recovered_and_lenient_counts(self):
        rows = rows_for(self.plan, 'platonic_grounding', 5) + rows_for(self.plan, 'base', 4, fence=True)
        arms, _, _ = analyze(self.plan, rows, TMAP)
        p, b = arms['platonic_grounding'], arms['base']
        self.assertEqual((p['strict_valid_original'], p['recovered_valid_json'], p['observed_joint_correct']), (0, 5, 5))
        self.assertEqual((b['recovered_valid_json'], b['lenient_fence_diagnostic']['joint_correct']), (0, 4))
        self.assertEqual(p['bounds_over_all_assigned']['joint'], [5, 5 + 64 - 5])
        self.assertEqual(p['unattempted_unknown'], 59)

    def test_paired_contingency_and_disagreements(self):
        good = rows_for(self.plan, 'formal_control', 6);bad = rows_for(self.plan, 'platonic_grounding', 6, wrong=True)
        arms, pc, key = analyze(self.plan, good + bad, TMAP)
        r = paired(pc, key, 'formal_control', 'platonic_grounding', 'joint')
        self.assertEqual((r['formal_control_only'], r['platonic_grounding_only'], r['both_correct']), (6, 0, 0))
        self.assertEqual(len(r['disagreements']), 6)
        self.assertAlmostEqual(r['mcnemar_exact_p'], 0.0312)
        self.assertNotIn('prompt', r['disagreements'][0])

    def test_invalid_rows_are_excluded_from_pairs_not_counted_wrong(self):
        g = rows_for(self.plan, 'formal_control', 3)
        b = rows_for(self.plan, 'platonic_grounding', 3)
        b[0] = record_for(self.plan, {k: b[0][k] for k in ('assignment_id', 'arm', 'case_id', 'case_sha256', 'motif_id', 'family', 'prompt')},
                          'prose<|im_end|>', metadata={'raw_model_text': 'prose<|im_end|>', 'raw_generated_token_ids': [1, 248046]})
        _, pc, key = analyze(self.plan, g + b, TMAP)
        r = paired(pc, key, 'formal_control', 'platonic_grounding', 'joint')
        self.assertEqual((r['cases_attempted_by_both'], r['cases_valid_in_both']), (3, 2))


class ArmRestrictionTests(unittest.TestCase):
    def test_unknown_or_duplicate_arms_rejected_before_weights(self):
        plan = make_plan('paired_smoke')
        for arms in (['intellect3'], ['base', 'base'], []):
            with self.assertRaises(ValueError):
                run_hf_group(plan, '/nonexistent/out.jsonl', base_model='x', model_revision='a' * 40, formal_adapter='f',
                             platonic_adapter='p', approval=True, max_assignments=1, arms=arms)

    def test_cot_cap_protocol_is_pinned_and_direct(self):
        p = generation.protocol('cot_cap_v1')
        self.assertEqual((p['thinking'], p['reasoning_budget'], p['answer_budget']), (False, 0, 1024))
        self.assertNotEqual(p['sha256'], generation.protocol('direct_v1')['sha256'])


if __name__ == '__main__':unittest.main()
