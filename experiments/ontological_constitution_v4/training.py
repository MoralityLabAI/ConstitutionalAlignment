"""Typed adapter into the existing natural-EOS encoder, with source revalidation."""
from .curriculum import verify_row, lesson_content
from .logic import canon


def as_sft(row):
    verify_row(row)
    return {'record_id': row['id'], 'group_id': row['group_id'], 'split': 'train',
            'arm': row['arm']+'_'+row['view'], 'system': row['messages'][0]['content'],
            'user': row['messages'][1]['content'],
            'rationale': lesson_content(row['certificate'], row['arm'], row['view'])['rationale'],
            'final': canon({'choice': row['choice']}), 'rationale_weight': 0.25, 'action_weight': 1.0,
            'source_evidence_class': row['evidence_class'], 'source_certificate_sha256': row['certificate']['sha256'],
            'natural_eos_targets': 1, 'legacy_trainer_acceptance': False}


def encode_certified(tokenizer, row, max_length=4096):
    # Importing this upstream function loads no model or Torch weights.
    from experiments.constitutional_reasoning_gym_v3.runtime import encode_sft
    return encode_sft(tokenizer, as_sft(row), max_length)
