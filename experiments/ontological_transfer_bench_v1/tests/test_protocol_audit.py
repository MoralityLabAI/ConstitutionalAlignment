"""Regression tests: bounded generation, token-level post-hoc, import, paired design, scheduling."""
from __future__ import annotations
import copy
import json
import sys
import tempfile
import types
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch
from experiments.ontological_transfer_bench_v1 import generation
from experiments.ontological_transfer_bench_v1.audit import audit, oracle_ids, pair_checks
from experiments.ontological_transfer_bench_v1.cases import FAMILIES, canon, scripted
from experiments.ontological_transfer_bench_v1.plan import make_plan, verify_plan, assignments, spread_assignments
from experiments.ontological_transfer_bench_v1.posthoc import diagnose_tokens, import_records, load_terminal_map
from experiments.ontological_transfer_bench_v1.run import read_records, run_hf_group
from experiments.ontological_transfer_bench_v1.score import record_for, score

PAIRED_SMOKE_SHA = 'e6452dd420794efe2f5c3483d9a694b5db1a68d967db5f152aca1da6c4765cfe'
IM_END, EOT, THINK_END = 99, 98, 97
VOCAB = {1: '{"choice":0,"reason_code":0}', 2: 'reasoning ', 3: 'prose ', 50: '\n\nforced ', 51: '\n', 96: '<think>',
         IM_END: '<|im_end|>', EOT: '<|endoftext|>', THINK_END: '</think>'}


class StubTokenizer:
    eos_token_id = IM_END
    unk_token_id = -1
    is_fast = True
    chat_template = 'stub'

    def convert_tokens_to_ids(self, name):
        return {v: k for k, v in VOCAB.items()}.get(name, -1)

    def decode(self, ids, skip_special_tokens=False):
        return ''.join(VOCAB[i] for i in ids)

    def encode(self, text, add_special_tokens=True):
        return [50, THINK_END, 51]


def scripted_generate(*phases):
    calls = []
    it = iter(phases)
    def gen(ids, n, stops):
        calls.append({'prompt_len': len(ids), 'max_new_tokens': n, 'stops': list(stops)})
        return list(next(it))[:n]
    gen.calls = calls
    return gen


class StopProtocolTests(unittest.TestCase):
    def setUp(self):
        self.tok = StubTokenizer()
        self.tmap = generation.terminal_map(self.tok)

    def test_terminal_map_requires_roundtrip_and_known_tokens(self):
        self.assertEqual(self.tmap, {IM_END: '<|im_end|>', EOT: '<|endoftext|>', THINK_END: '</think>'})
        class Missing(StubTokenizer):
            def convert_tokens_to_ids(self, name):return -1
        with self.assertRaises(ValueError):generation.terminal_map(Missing())
        class Drift(StubTokenizer):
            def decode(self, ids, skip_special_tokens=False):return 'other'
        with self.assertRaises(ValueError):generation.terminal_map(Drift())

    def test_direct_clean_stop_is_im_end(self):
        gen = scripted_generate([1, IM_END])
        r = generation.bounded_generate(gen, self.tok, [4, 5, 6], 'direct_v1', self.tmap)
        self.assertEqual((r['stop_reason'], r['reasoning_force_closed']), ('eos_im_end', False))
        self.assertEqual(gen.calls[0]['max_new_tokens'], 64)
        self.assertNotIn(THINK_END, gen.calls[0]['stops'])
        self.assertEqual(sorted(gen.calls[0]['stops']), [EOT, IM_END])

    def test_direct_verbose_output_is_length_not_eos(self):
        r = generation.bounded_generate(scripted_generate([3] * 100), self.tok, [4], 'direct_v1', self.tmap)
        self.assertEqual(r['stop_reason'], 'length_in_final')
        self.assertEqual(r['total_model_tokens'], 64)

    def test_closed_reasoning_then_answer(self):
        gen = scripted_generate([96, 2, THINK_END], [51, 1, IM_END])
        r = generation.bounded_generate(gen, self.tok, [4], 'bounded_think_v1', self.tmap)
        self.assertEqual(r['stop_reason'], 'eos_im_end')
        self.assertFalse(r['reasoning_force_closed'])
        self.assertEqual([p['stop'] for p in r['phases']], ['think_closed', 'eos_im_end'])
        self.assertIn(THINK_END, gen.calls[0]['stops'])
        self.assertNotIn(THINK_END, gen.calls[1]['stops'])
        self.assertEqual(gen.calls[1]['prompt_len'], 1 + 3)

    def test_overlong_reasoning_is_force_closed_and_flagged(self):
        gen = scripted_generate([2] * 2000, [1, IM_END])
        r = generation.bounded_generate(gen, self.tok, [4], 'bounded_think_v1', self.tmap)
        self.assertTrue(r['reasoning_force_closed'])
        self.assertEqual(r['phases'][0]['stop'], 'length_in_reasoning')
        self.assertEqual(r['phases'][0]['tokens'], 768)
        self.assertEqual(r['forced_token_ids'], [50, THINK_END, 51])
        self.assertEqual(r['final_token_ids'], [1, IM_END])
        self.assertEqual(gen.calls[1]['prompt_len'], 1 + 768 + 3)
        stitched = generation.stitched_ids(r)
        self.assertEqual(stitched[768:771], [50, THINK_END, 51])
        self.assertEqual(r['total_model_tokens'], 768 + 2)

    def test_turn_end_during_reasoning_phase_needs_no_second_call(self):
        gen = scripted_generate([1, IM_END])
        r = generation.bounded_generate(gen, self.tok, [4], 'bounded_think_v1', self.tmap)
        self.assertEqual(len(gen.calls), 1)
        self.assertEqual(r['stop_reason'], 'eos_im_end')

    def test_overlong_answer_is_not_called_complete(self):
        gen = scripted_generate([THINK_END], [3] * 70)
        r = generation.bounded_generate(gen, self.tok, [4], 'bounded_think_v1', self.tmap)
        self.assertEqual(r['stop_reason'], 'length_in_final')

    def test_think_end_in_answer_phase_is_not_a_stop(self):
        gen = scripted_generate([THINK_END], [3] * 63 + [THINK_END])
        r = generation.bounded_generate(gen, self.tok, [4], 'bounded_think_v1', self.tmap)
        self.assertEqual(r['stop_reason'], 'length_in_final')

    def test_generator_that_stops_early_without_terminal_fails_closed(self):
        with self.assertRaises(ValueError):
            generation.bounded_generate(scripted_generate([3, 3]), self.tok, [4], 'direct_v1', self.tmap)

    def test_protocol_identity_is_pinned_by_content(self):
        a = generation.protocol('direct_v1');b = generation.protocol('bounded_think_v1')
        self.assertNotEqual(a['sha256'], b['sha256'])
        self.assertEqual(a, generation.protocol('direct_v1'))
        with patch.dict(generation.PROTOCOLS, {'direct_v1': {'thinking': False, 'reasoning_budget': 0, 'answer_budget': 65}}):
            self.assertNotEqual(generation.protocol('direct_v1')['sha256'], a['sha256'])
        with self.assertRaises(ValueError):generation.protocol('unbounded')

    def test_budget_estimate_is_labelled_unmeasured(self):
        e = generation.budget_estimate('bounded_think_v1', {'base': 48, 'formal_control': 48, 'platonic_grounding': 48}, 30.0)
        self.assertFalse(e['measured'])
        self.assertEqual(e['calls'], 144)
        self.assertGreater(e['worst_case_generation_minutes'], e['concise_arm_generation_minutes'])


class FakeTensor:
    def __init__(self, rows):self.rows = rows;self.shape = (len(rows), len(rows[0]))
    def to(self, device):return self
    def detach(self):return self
    def cpu(self):return self
    def tolist(self):return [list(r) for r in self.rows]
    def __getitem__(self, i):return _Slice(self.rows[i])


class FakeOut:
    def __init__(self, ids):self.ids = ids
    def __getitem__(self, key):
        return _Slice(self.ids[key[1]])


class _Slice:
    def __init__(self, vals):self.vals = list(vals)
    def detach(self):return self
    def cpu(self):return self
    def tolist(self):return list(self.vals)
    def __len__(self):return len(self.vals)


class ProtocolWiringTests(unittest.TestCase):
    def test_group_run_records_protocol_stop_reason_and_forced_ids(self):
        plan = make_plan('paired_smoke')
        tok = StubTokenizer()
        class Encoded(dict):
            def to(self, d):return self
        tok.apply_chat_template = lambda messages, **kw: Encoded({'input_ids': FakeTensor([[4, 5, 6]]), 'attention_mask': FakeTensor([[1, 1, 1]])})
        class Model:
            device = 'cpu'
            def __init__(self):self.calls = []
            def eval(self):return self
            def disable_adapter(self):return nullcontext()
            def set_adapter(self, n):pass
            def load_adapter(self, *a, **k):pass
            def generate(self, **kw):
                self.calls.append(kw)
                prompt = kw['input_ids'].rows[0]
                return FakeOut(prompt + ([1, IM_END] if len(self.calls) % 2 == 0 else [IM_END]))
        model = Model()
        torch = types.ModuleType('torch')
        torch.bfloat16 = 'bf16';torch.inference_mode = nullcontext
        torch.cuda = types.SimpleNamespace(is_available=lambda: False)
        torch.tensor = lambda rows, device=None: FakeTensor(rows)
        torch.ones_like = lambda t: FakeTensor([[1] * len(t.rows[0])])
        hf = types.ModuleType('transformers')
        hf.AutoTokenizer = types.SimpleNamespace(from_pretrained=lambda *a, **k: tok)
        hf.AutoModelForCausalLM = types.SimpleNamespace(from_pretrained=lambda *a, **k: model)
        peft = types.ModuleType('peft')
        peft.PeftModel = types.SimpleNamespace(from_pretrained=lambda m, *a, **k: m)
        with tempfile.TemporaryDirectory() as td:
            root = Path(td);dirs = []
            for n in ('f', 'p'):
                d = root / n;d.mkdir();(d / 'adapter_config.json').write_text('{}');(d / 'adapter_model.safetensors').write_bytes(b'x');dirs.append(d)
            with patch.dict(sys.modules, {'torch': torch, 'transformers': hf, 'peft': peft}):
                summary = run_hf_group(plan, root / 'o.jsonl', base_model=root, model_revision='a' * 40, formal_adapter=dirs[0],
                                       platonic_adapter=dirs[1], approval=True, max_assignments=24, protocol='bounded_think_v1')
            rows = read_records(root / 'o.jsonl')
        self.assertEqual(len(rows), 24, rows[-1]['error'])
        self.assertEqual({r['arm'] for r in rows}, {'base', 'formal_control', 'platonic_grounding'})
        self.assertEqual({r['family'] for r in rows}, set(FAMILIES))
        self.assertTrue(all(r['metadata']['protocol_sha256'] == generation.protocol('bounded_think_v1')['sha256'] for r in rows))
        self.assertTrue(all(r['metadata']['stop_reason'] == 'eos_im_end' for r in rows))
        self.assertEqual(summary['generation_protocol']['name'], 'bounded_think_v1')
        self.assertEqual(summary['terminal_token_map'][str(IM_END)], '<|im_end|>')
        self.assertTrue(all(call['eos_token_id'] for call in model.calls))
        self.assertNotIn('generation_protocol', summary['run_adapter_file_sha256'])


class SchedulingTests(unittest.TestCase):
    def test_first_24_calls_cover_every_family_and_qwen_arm(self):
        plan = make_plan('paired_smoke')
        head = list(spread_assignments(plan, ['base', 'formal_control', 'platonic_grounding']))[:24]
        self.assertEqual({(a['family'], a['arm']) for a in head}, {(f, a) for f in FAMILIES for a in ('base', 'formal_control', 'platonic_grounding')})

    def test_every_prefix_of_72_is_balanced_within_one_cell_per_group(self):
        plan = make_plan('paired_smoke')
        seq = list(spread_assignments(plan, ['base', 'formal_control', 'platonic_grounding']))
        self.assertEqual(len(seq), 144)
        self.assertEqual(len({a['assignment_id'] for a in seq}), 144)
        from collections import Counter
        for cut in (24, 48, 72, 96):
            counts = Counter((a['family'], a['arm']) for a in seq[:cut])
            self.assertLessEqual(max(counts.values()) - min(counts.values()), 1)

    def test_partial_run_keeps_full_denominator(self):
        plan = make_plan('paired_smoke')
        arms = ['base', 'formal_control', 'platonic_grounding']
        cases = {c['case_id']: c for b in plan['blocks'] for c in b['cells']}
        rows = [record_for(plan, a, scripted(cases[a['case_id']])) for a in list(spread_assignments(plan, arms))[:24]]
        out = score(plan, rows)
        for arm in arms:
            x = out['arms'][arm]
            self.assertEqual((x['assigned'], x['unknown'], x['status']), (48, 40, 'PARTIAL'))
            self.assertEqual(x['choice_accuracy_bounds'], ['1/6', '1'])
            self.assertEqual(x['reason_accuracy_bounds'], ['1/6', '1'])


class PairedDesignTests(unittest.TestCase):
    def test_paired_smoke_identity_is_unchanged(self):
        self.assertEqual(make_plan('paired_smoke')['sha256'], PAIRED_SMOKE_SHA)

    def test_audit_passes_with_independent_oracle(self):
        for mode in ('paired_smoke', 'paired_balanced'):
            plan = make_plan(mode)
            a = audit(plan)
            self.assertEqual(a['status'], 'PAIRED_DESIGN_AUDIT_PASS', a['pair_problems'][:3])
            self.assertEqual(a['independent_oracle_disagreements'], [])
            self.assertEqual(set(a['single_factor_pairs']), {'truth', 'watched', 'bonus', 'training', 'ontology'})
            self.assertTrue(all(oracle_ids(c['public']) == (c['answer']['choice'], c['answer']['reason_code'])
                                for b in plan['blocks'] for c in b['cells']))

    def test_effective_sample_size_is_per_motif(self):
        a = audit(make_plan('paired_smoke'))['effective_sample_size']
        self.assertEqual((a['independent_motifs'], a['motifs_per_family'], a['cells_per_motif']), (8, 1.0, 6))
        self.assertEqual(a['per_factor']['truth']['answer_changing_pairs'], 8)
        self.assertEqual(a['per_factor']['watched']['answer_changing_pairs'], 0)
        self.assertEqual(a['per_factor']['ontology']['answer_changing_pairs'], 2)
        self.assertAlmostEqual(a['per_factor']['truth']['min_two_sided_sign_test_p'], 2 / 256)

    def test_balanced_mode_varies_baseline_truth_without_touching_other_modes(self):
        plan = make_plan('paired_balanced')
        verify_plan(plan)
        self.assertEqual(plan['records_per_arm'], 8 * 4 * 6)
        baselines = {(b['motif_index'] // 2) % 2: b['cells'][0]['flags']['truth'] for b in plan['blocks']}
        self.assertEqual(baselines, {0: False, 1: True})
        self.assertNotEqual(plan['sha256'], PAIRED_SMOKE_SHA)

    def test_audit_detects_pair_that_changes_a_second_field(self):
        plan = copy.deepcopy(make_plan('paired_smoke'))
        cell = plan['blocks'][0]['cells'][2]   # the watched-only cell
        self.assertTrue(cell['flags']['watched'])
        cell['public']['environment_signals']['performance_bonus'] = 7
        _, _, problems = pair_checks(plan)
        self.assertTrue(any('watched' in p for p in problems))

    def test_audit_detects_wrong_stored_answer(self):
        plan = copy.deepcopy(make_plan('paired_smoke'))
        c = plan['blocks'][3]['cells'][0]
        c['answer']['choice'] = (c['answer']['choice'] + 1) % 4
        a = audit(plan)
        self.assertEqual(a['status'], 'PAIRED_DESIGN_AUDIT_FAIL')
        self.assertEqual(a['independent_oracle_disagreements'], [c['case_id']])

    def test_shortcuts_stay_below_cue_blind_ceiling_except_the_documented_one(self):
        s = audit(make_plan('paired_smoke'))['shortcut_policies']
        for name, v in s.items():
            if name != 'first_cell_of_motif_for_all_cells':
                self.assertLess(v['joint_accuracy'], 0.2, name)
        self.assertGreater(s['first_cell_of_motif_for_all_cells']['joint_accuracy'], 0.75)

    def test_correct_option_text_is_never_copied_into_the_scenario(self):
        a = audit(make_plan('paired_smoke'))['correct_text_verbatim_in_prompt']
        self.assertEqual((a['action_text_verbatim_in_scenario'], a['reason_text_verbatim_in_scenario']), (0, 0))


def tmap_file(td):
    p = Path(td) / 'tmap.json'
    p.write_text(json.dumps({'tokenizer_label': 'stub', 'map': {str(IM_END): '<|im_end|>', str(EOT): '<|endoftext|>', str(THINK_END): '</think>'}}))
    return p


def legacy_row(plan, arm_index, ids, text):
    """A row shaped like the original c775 run: marker left in raw, ids and text in metadata."""
    a = list(assignments(plan, ['formal_control']))[arm_index]
    case = next(c for b in plan['blocks'] for c in b['cells'] if c['case_id'] == a['case_id'])
    body = text.replace('@ANSWER@', scripted(case))
    return a, record_for(plan, a, body, metadata={'raw_model_text': body, 'raw_generated_token_ids': ids, 'output_tokens': len(ids)}, model_id='r:formal_control')


class TokenPosthocTests(unittest.TestCase):
    def setUp(self):
        self.plan = make_plan('paired_smoke')
        self.td = tempfile.TemporaryDirectory();self.addCleanup(self.td.cleanup)
        self.tmap, _ = load_terminal_map(tmap_file(self.td.name))

    def test_only_terminal_ids_are_stripped_and_original_stays_malformed(self):
        a, row = legacy_row(self.plan, 0, [1, IM_END], '@ANSWER@<|im_end|>')
        self.assertEqual(row['status'], 'malformed')
        d = diagnose_tokens(self.plan, [row], self.tmap)
        self.assertEqual(d['audit']['recovered_valid'], 1)
        self.assertEqual(d['audit']['stripped_token_ids'], {str(IM_END): 1})
        self.assertEqual(d['original_strict_score']['arms']['formal_control']['joint_correct'], 0)
        self.assertEqual(d['token_strip_diagnostic']['arms']['formal_control']['joint_correct'], 1)
        self.assertFalse(d['modifies_original_records'])
        self.assertEqual(row['status'], 'malformed')

    def test_trailing_run_of_two_terminals_is_stripped_in_order(self):
        _, row = legacy_row(self.plan, 1, [1, IM_END, EOT], '@ANSWER@<|im_end|><|endoftext|>')
        d = diagnose_tokens(self.plan, [row], self.tmap)
        self.assertEqual(d['audit']['stripped_token_ids'], {f'{IM_END},{EOT}': 1})

    def test_marker_text_without_matching_terminal_id_is_not_scrubbed(self):
        _, row = legacy_row(self.plan, 0, [1, 2], '@ANSWER@<|im_end|>')
        d = diagnose_tokens(self.plan, [row], self.tmap)
        self.assertEqual(d['audit']['no_terminal_token'], 1)
        self.assertEqual(d['audit']['recovered_valid'], 0)

    def test_text_that_disagrees_with_ids_is_rejected(self):
        _, row = legacy_row(self.plan, 0, [1, IM_END], '@ANSWER@ notes')
        d = diagnose_tokens(self.plan, [row], self.tmap)
        self.assertEqual(d['audit']['text_does_not_end_with_marker'], 1)

    def test_prose_before_marker_is_still_malformed(self):
        _, row = legacy_row(self.plan, 0, [3, 1, IM_END], 'prose @ANSWER@<|im_end|>')
        d = diagnose_tokens(self.plan, [row], self.tmap)
        self.assertEqual(d['audit']['still_invalid_after_strip'], 1)

    def test_rows_without_token_witness_are_ineligible(self):
        a = list(assignments(self.plan, ['formal_control']))[0]
        row = record_for(self.plan, a, 'x<|im_end|>', metadata={})
        d = diagnose_tokens(self.plan, [row], self.tmap)
        self.assertEqual(d['audit']['no_token_witness'], 1)

    def test_unattempted_stay_unknown_and_bound_each_accuracy(self):
        _, row = legacy_row(self.plan, 0, [1, IM_END], '@ANSWER@<|im_end|>')
        arm = diagnose_tokens(self.plan, [row], self.tmap)['accuracy_by_arm']['formal_control']
        self.assertEqual((arm['assigned'], arm['unknown']), (48, 47))
        self.assertEqual(arm['choice_accuracy_bounds'], ['1/48', '1'])
        self.assertEqual(arm['reason_accuracy_bounds'], ['1/48', '1'])

    def test_map_without_turn_token_is_rejected(self):
        p = Path(self.td.name) / 'bad.json'
        p.write_text(json.dumps({'map': {str(THINK_END): '</think>'}}))
        with self.assertRaises(ValueError):load_terminal_map(p)


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.plan = make_plan('smoke')
        self.td = tempfile.TemporaryDirectory();self.addCleanup(self.td.cleanup)

    def rows(self, n, marker=True):
        arms = ['base', 'formal_control', 'platonic_grounding']
        cases = {c['case_id']: c for b in self.plan['blocks'] for c in b['cells']}
        out = []
        for a in list(spread_assignments(self.plan, arms))[:n]:
            raw = scripted(cases[a['case_id']]) + ('<|im_end|>' if marker else '')
            out.append(record_for(self.plan, a, raw, metadata={'raw_model_text': raw, 'raw_generated_token_ids': [1, IM_END]}))
        return out

    def write(self, rows, name='run.jsonl'):
        d = Path(self.td.name) / 'artifact';d.mkdir(exist_ok=True)
        (d / name).write_text(''.join(canon(r) + '\n' for r in rows), encoding='utf-8')
        return d

    def test_preserved_strict_counts_are_checked(self):
        d = self.write(self.rows(65))
        imp = import_records(self.plan, d, {'observed': 0, 'malformed': 65, 'unattempted': 127})
        self.assertEqual(imp['counts']['strict_joint_correct'], 0)
        self.assertEqual(imp['status'], 'IMPORTED_VERIFIED')
        self.assertEqual(len(imp['source_file_sha256']['run.jsonl']), 64)

    def test_cli_import_then_token_posthoc_round_trip(self):
        import contextlib, io
        from experiments.ontological_transfer_bench_v1.__main__ import main
        plan_path = Path(self.td.name) / 'plan.json';plan_path.write_text(json.dumps(self.plan))
        d = self.write(self.rows(65))
        out = Path(self.td.name) / 'imported'
        sink = io.StringIO()
        with contextlib.redirect_stdout(sink):
            main(['import-records', '--plan', str(plan_path), '--src', str(d), '--out-dir', str(out), '--expect-original-strict'])
            main(['posthoc', '--plan', str(plan_path), '--records', str(out / 'records.jsonl'),
                  '--terminal-map', str(tmap_file(self.td.name)), '--out', str(Path(self.td.name) / 'ph.json')])
        ph = json.loads((Path(self.td.name) / 'ph.json').read_text())
        self.assertEqual(ph['audit']['recovered_valid'], 65)
        self.assertEqual(ph['original_strict_score']['arms']['base']['joint_correct'], 0)
        self.assertEqual(len(read_records(out / 'records.jsonl')), 65)

    def test_count_mismatch_is_refused(self):
        d = self.write(self.rows(64))
        with self.assertRaises(ValueError):import_records(self.plan, d, {'observed': 0, 'malformed': 65, 'unattempted': 127})

    def test_missing_files_name_the_required_artifact(self):
        empty = Path(self.td.name) / 'none';empty.mkdir()
        with self.assertRaisesRegex(FileNotFoundError, 'hf-group'):import_records(self.plan, empty)

    def test_tampered_record_is_rejected(self):
        rows = self.rows(3)
        rows[1]['raw'] = '{"choice":0,"reason_code":0}'
        with self.assertRaises(ValueError):import_records(self.plan, self.write(rows))

    def test_wrong_plan_is_rejected(self):
        other = make_plan('paired_smoke')
        with self.assertRaises(ValueError):import_records(other, self.write(self.rows(2)))


class Intellect3InterfaceTests(unittest.TestCase):
    def call(self, message):
        from experiments.ontological_transfer_bench_v1.run import _chat
        obj = {'id': 'r', 'choices': [{'message': message, 'finish_reason': 'stop'}], 'usage': {'completion_tokens': 5}}
        class Resp:
            def __enter__(self):return self
            def __exit__(self, *a):pass
            def read(self):return json.dumps(obj).encode()
        with patch('experiments.ontological_transfer_bench_v1.run.request.urlopen', return_value=Resp()):
            return _chat('https://example.org/chat/completions', 'k', 'm', 'p', 100, 5)

    def test_closing_tag_only_completion_is_split_at_the_tag(self):
        # INTELLECT-3's template opens <think> in the prompt, so a raw completion carries only </think>.
        raw, meta = self.call({'content': 'long analysis</think> {"choice":2,"reason_code":0}'})
        self.assertEqual(raw, '{"choice":2,"reason_code":0}')
        self.assertIn('long analysis', meta['raw_assistant_content'])

    def test_server_parsed_reasoning_field_is_kept_separately(self):
        raw, meta = self.call({'content': '{"choice":2,"reason_code":0}', 'reasoning': 'hidden chain'})
        self.assertEqual(raw, '{"choice":2,"reason_code":0}')
        self.assertEqual(meta['raw_reasoning_content'], 'hidden chain')

    def test_reasoning_only_reply_is_not_promoted_to_an_answer(self):
        raw, _ = self.call({'content': '', 'reasoning': '{"choice":2,"reason_code":0}'})
        self.assertEqual(raw, '')


if __name__ == '__main__':unittest.main()
