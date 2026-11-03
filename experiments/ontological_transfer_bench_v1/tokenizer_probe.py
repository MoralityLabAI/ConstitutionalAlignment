"""Local tokenizer-only probe of the stopping protocols (needs `transformers`; not used by CI).

Runs bounded_generate with a scripted generator against a real chat tokenizer, so
token IDs, the chat template and the forced-close text are real while no model runs.
"""
from __future__ import annotations
import hashlib
from pathlib import Path
from . import generation
from .cases import parse
from .run import decode_hf_final, write_json


def probe(tokenizer_dir, label, out):
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(tokenizer_dir, local_files_only=True)
    tmap = generation.terminal_map(tok)
    stops = generation.stop_ids(tmap)
    turn = stops['turn'];end = stops['think_end']
    im_end = next(i for i, n in tmap.items() if n == '<|im_end|>')
    enc = lambda s: tok.encode(s, add_special_tokens=False)
    answer = enc('{"choice": 2, "reason_code": 1}')
    messages = [{'role': 'system', 'content': 'Provide a final JSON answer using the case menu IDs.'}, {'role': 'user', 'content': 'x'}]
    templates = {str(th): tok.apply_chat_template(messages, add_generation_prompt=True, tokenize=False, enable_thinking=th)[-48:]
                 for th in (False, True)}
    def scripted(*phases):
        it = iter(phases)
        return lambda ids, n, stops_: list(next(it))[:n]
    cases = {
        'direct_clean': ('direct_v1', [answer + [im_end]]),
        'direct_verbose_hits_answer_budget': ('direct_v1', [enc('The chain of reasoning is long ' * 40)[:64]]),
        'think_closes_then_answers': ('bounded_think_v1', [enc('<think>\nbrief') + [end], enc('\n\n') + answer + [im_end]]),
        'think_overlong_forced_close': ('bounded_think_v1', [enc('<think>\n' + 'step ' * 900)[:768], answer + [im_end]]),
        'answer_phase_overlong': ('bounded_think_v1', [enc('<think>\nok') + [end], enc('Sure! ' * 40)[:64]]),
        'eos_without_think': ('bounded_think_v1', [answer + [im_end]]),
    }
    results = {}
    for name, (proto, phases) in cases.items():
        res = generation.bounded_generate(scripted(*phases), tok, [1, 2, 3], proto, tmap)
        raw, full, stripped = decode_hf_final(tok, res['final_token_ids'])
        try:parse(raw);valid = True
        except (TypeError, ValueError):valid = False
        results[name] = {'stop_reason': res['stop_reason'], 'force_closed': res['reasoning_force_closed'],
                         'model_tokens': res['total_model_tokens'], 'forced_tokens': res['total_forced_tokens'],
                         'stripped_terminal_ids': stripped, 'strict_valid': valid}
    receipt = {'status': 'TOKENIZER_STOP_PROBE_NO_MODEL', 'tokenizer_label': label, 'terminal_map': {str(k): v for k, v in tmap.items()},
               'eos_token_id': tok.eos_token_id, 'template_tail_by_enable_thinking': templates,
               'forced_close_token_count': len(enc(generation.FORCED_CLOSE_TEXT)),
               'protocols': {n: generation.protocol(n) for n in generation.PROTOCOLS}, 'cases': results}
    write_json(out, receipt)
    return receipt
