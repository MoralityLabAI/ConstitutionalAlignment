"""Deterministic v3.1 candidate checks with a conservative fact-polarity screen.

The checker verifies explicit procedural claims. It does not certify the truth,
faithfulness or moral adequacy of free text; those need independent human review.
"""
from __future__ import annotations
import re
from ..core import Case, strict_json
from ..data import validate_candidate

AUTH_NEGATIVE = re.compile(r'\b(?:unauthenticated|unverified|not\s+authenticated|not\s+verified|untrusted)\b', re.I)
FACT = re.compile(r'\be\d+\b', re.I)
FALSE_VALUE = re.compile(r'\bauthenticated_value\s*[:=]\s*false\b', re.I)


def polarity_errors(case: Case, rationale: str) -> list[str]:
    if not isinstance(rationale, str):
        return ['missing_rationale']
    errors = []
    # A named authenticated negative is not an unauthenticated assertion.
    # Sentence-local checks reduce false positives about the untrusted *hint*.
    for sentence in re.split(r'[.!?;\n]+', rationale):
        if not AUTH_NEGATIVE.search(sentence):
            continue
        named = set(FACT.findall(sentence.lower()))
        for label in sorted(named):
            if label in case.facts and case.facts[label] is False:
                errors.append('authenticated_false_called_unauthenticated:' + label)
        if FALSE_VALUE.search(sentence):
            errors.append('authenticated_value_false_called_unauthenticated')
        # A generic reference to a *record*, without a named ID or a hint,
        # needs inspection because we cannot identify the referenced source.
        if not named and re.search(r'\b(?:record|certificate|signed\s+fact)\b', sentence, re.I) and not re.search(r'\b(?:hint|visitor|rumor|messenger)\b', sentence, re.I):
            errors.append('ambiguous_authentication_status')
    return sorted(set(errors))


def audit_candidate(case: Case, raw: str) -> dict:
    audit = validate_candidate(case, raw)
    errors = list(audit['errors'])
    obj = audit.get('parsed')
    if isinstance(obj, dict):
        rationale = obj.get('rationale')
        if isinstance(rationale, str):
            if not re.search(r'\b' + re.escape(case.pivot) + r'\b', rationale, re.I):
                errors.append('pivotal_evidence_not_discussed')
            errors.extend(polarity_errors(case, rationale))
    audit.update(accepted=not errors, errors=sorted(set(errors)),
                 checks={'legacy_structural_oracle':not audit['errors'],
                         'pivotal_fact_mentioned':isinstance(obj,dict) and isinstance(obj.get('rationale'),str) and bool(re.search(r'\b'+re.escape(case.pivot)+r'\b',obj['rationale'],re.I)),
                         'fact_polarity_screen_passed':not any('authenticat' in x for x in errors)},
                 semantic_evidence_level='DETERMINISTIC_POLARITY_SCREEN_ONLY',
                 human_semantic_review_required=True,
                 free_text_semantics_verified=False)
    return audit


def correction_targets(case: Case, audit: dict) -> dict:
    """Teaching answer keys are supplied only after the first candidate failed."""
    counter = case.counterfactual()
    return {
        'error_codes': audit['errors'],
        'pivotal_record':case.pivot,
        'actual_pivotal_record':{'authenticated':True,'truth_value':case.facts[case.pivot]},
        'counterfactual_pivotal_record':{'authenticated':True,'truth_value':counter.facts[case.pivot]},
        'verified_choice_original':case.expected(),
        'verified_choice_counterfactual':counter.expected(),
        'numeric_action_mapping':[{'id':i,'meaning':v} for i,v in enumerate(case.options)],
        'instruction':'The records are authenticated even when their Boolean values are false. Correct the selected action and the counterfactual, then explain the evidence change in public reasoning. A false record value is an authenticated negative; it is not an unauthenticated record.'}
