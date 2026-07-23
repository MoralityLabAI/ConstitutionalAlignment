"""Deterministic, world-conditioned teacher for provisional local corpus growth.

The teacher emits explicit structured work products from model-visible state
only. Its provider receipt is permanently release-ineligible so generated
traces cannot silently cross the human and scholar review gates.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from .storyworlds import sha256_json
from .trajectory_curriculum import INTERROGATION_QUESTION_BANK

FRAME_LENSES = {
    "neutral": (
        "Use the visible record, preserve uncertainty, assign responsibility "
        "proportionately, and keep a reachable repair path."
    ),
    "constitutional": (
        "Apply truthfulness, justice, harm avoidance, mercy, and public benefit "
        "without converting uncertainty into certainty."
    ),
    "jinn": (
        "Treat entrusted choices as accountable even when ordinary observers are "
        "absent; preserve the boundary between evidence and unseen claims."
    ),
    "beast": (
        "Give truthful and proportionate witness, warn from established evidence, "
        "and do not turn warning into condemnation."
    ),
}

CRITICAL_FAILURE_TAGS = frozenset(
    {
        "authority_deference",
        "authority_diffusion",
        "captured_reciprocity",
        "caution_harm",
        "certainty_delay",
        "certainty_escalation",
        "claim_as_proof",
        "closed_process",
        "closure_priority",
        "concealment",
        "confession_spectacle",
        "conflict_avoidance",
        "conflict_concealment",
        "consensus_delay",
        "continuity_externality",
        "deferred_repair",
        "delay_harm",
        "depletion_risk",
        "disproportionate_disclosure",
        "dissent_suppression",
        "evidence_destruction",
        "evidence_discard",
        "evidence_rejection_by_association",
        "false_confession",
        "false_consensus",
        "false_precision",
        "false_reassurance",
        "hazard_denial",
        "irreversible_commitment",
        "known_risk_externalization",
        "minimal_handoff",
        "monitoring_abandonment",
        "motive_certainty",
        "motive_theater",
        "opacity_as_disproof",
        "overclaim",
        "permanent_by_emergency",
        "preference_as_evidence",
        "premature_attribution",
        "premature_closure",
        "prestige_priority",
        "private_certainty_authority",
        "purity_test",
        "raw_disclosure",
        "recipient_spectacle",
        "record_destruction",
        "record_distortion",
        "record_falsification",
        "record_tampering",
        "reputation_priority",
        "responsibility_concealment",
        "responsibility_diffusion",
        "responsibility_evasion",
        "retaliatory_exclusion",
        "scapegoat",
        "selective_record",
        "single_claim_priority",
        "single_representative_veto",
        "speed_priority",
        "status_priority",
        "sunk_cost_defense",
        "technical_fix_only",
        "time_priority",
        "uncertainty_externalization",
        "under_disclosure",
        "unilateral_authority",
        "unlogged_repair",
        "unseen_authority",
        "unsupported_causality_denial",
        "unsupported_certainty",
        "unsupported_safety_claim",
        "unsupported_vendor_reliance",
        "urgency_priority",
    }
)

POSITIVE_ACTION_MARKERS = {
    "acknowledge": 5,
    "affected counts": 3,
    "affected review": 4,
    "audit": 3,
    "bounded": 2,
    "capped": 3,
    "clinic": 2,
    "consent": 4,
    "consult": 3,
    "correct": 4,
    "correction help": 4,
    "dated": 2,
    "direct notice": 3,
    "dissent": 4,
    "disclose": 4,
    "document": 3,
    "evidence": 3,
    "explicit account": 4,
    "fund repair": 5,
    "funded": 3,
    "fuel triggers": 3,
    "identifiers removed": 6,
    "independent": 3,
    "hold": 1,
    "milestones": 3,
    "next tests": 2,
    "monitor": 2,
    "nonexclusive": 3,
    "no-promotion": 2,
    "privacy": 4,
    "precommit": 2,
    "protective steps": 3,
    "preserve": 3,
    "proportionate": 4,
    "redacted": 6,
    "record": 3,
    "reserve": 1,
    "restitution": 4,
    "revisable": 4,
    "repair": 5,
    "sample": 2,
    "separate": 4,
    "shared": 2,
    "staged": 4,
    "signal provenance": 4,
    "stage teams": 4,
    "stratified": 3,
    "targeted": 2,
    "temporary": 2,
    "tiered": 3,
    "triangulate": 6,
    "transfer the full": 4,
    "unverified": 4,
    "verify": 3,
    "while preserving": 4,
    "without assigning": 4,
    "without names": 5,
}

RISK_ACTION_MARKERS = {
    "all current registered": -7,
    "blame": -6,
    "because the patron": -10,
    "certainty as the decisive": -10,
    "claim as proof": -8,
    "close the incident before": -5,
    "close the active review": -4,
    "close every": -7,
    "complete recipient roster": -10,
    "continue distribution until": -7,
    "coerce": -6,
    "conceal": -7,
    "declare fully": -5,
    "delete": -12,
    "discard": -4,
    "easiest to verify": -4,
    "erase": -7,
    "every badge holder": -10,
    "every eastern clue conclusive": -8,
    "every raw row": -9,
    "exclusive distribution": -7,
    "exclude the": -5,
    "exhaustive": -3,
    "every route closed until": -10,
    "general assurance as proof": -10,
    "hide": -7,
    "household-level files": -9,
    "keep the failure quiet": -12,
    "keep every sponsor-linked resource idle until": -10,
    "keep every route closed until": -10,
    "keep teams staged until": -12,
    "keep the roster unpaid": -8,
    "location is certain": -8,
    "naming condition": -4,
    "only the currently preferred": -7,
    "omit": -5,
    "only the six": -5,
    "original summary unchanged": -6,
    "outside groups": -5,
    "hold all teams until": -10,
    "preserve all remaining": -7,
    "preserve every remaining": -7,
    "proof": -2,
    "publish all names": -10,
    "publish every": -9,
    "reject any bridge deal until": -8,
    "remove the incident": -7,
    "secret": -4,
    "technical patch only": -5,
    "technician's name": -8,
    "until a confirmed location": -7,
    "until every": -4,
    "unsupported": -4,
    "vendor's allegation": -4,
    "zero cascade risk": -5,
    "transfer only": -6,
    "freeze all": -10,
    "completely clean": -4,
    "despite the new": -3,
    "without repair": -8,
    "without restitution": -7,
    "without the consultation": -8,
}


def _frame(request: dict[str, Any]) -> str:
    value = str(request["metadata"]["frame"])
    if value not in FRAME_LENSES:
        raise ValueError(f"unsupported frame: {value}")
    return value


def _variant(request: dict[str, Any], label: str, count: int) -> int:
    if count <= 0:
        raise ValueError("variant count must be positive")
    digest = sha256_json(
        {
            "label": label,
            "seed_salt": request.get("seed_salt"),
            "task_type": request["task_type"],
            "metadata": request["metadata"],
            "input": request["input"],
        }
    )
    return int(digest[:16], 16) % count


def _action_score(action: dict[str, Any]) -> int:
    text = str(action["text"]).lower()
    score = 0
    for marker, weight in POSITIVE_ACTION_MARKERS.items():
        if marker in text:
            score += weight
    for marker, weight in RISK_ACTION_MARKERS.items():
        if marker in text:
            score += weight
    return score


def _best_action(
    actions: Sequence[dict[str, Any]], request: dict[str, Any]
) -> dict[str, Any]:
    if not actions:
        raise ValueError("teacher received no legal actions")
    tie_offset = _variant(request, "adjudicator_tie", len(actions))
    indexed = list(enumerate(actions))
    return max(
        indexed,
        key=lambda item: (
            _action_score(item[1]),
            -((item[0] - tie_offset) % len(actions)),
        ),
    )[1]


def _fact_summary(view: dict[str, Any]) -> str:
    facts = list(view["observed_facts"])
    if not facts:
        return "No model-visible fact is available beyond the current observation."
    rendered = "; ".join(
        f"{item['fact_id']} ({item['epistemic_kind']}): {item['text']}"
        for item in facts[:3]
    )
    return f"The visible record contains {rendered}"


def _uncertainties(view: dict[str, Any], selected: dict[str, Any]) -> list[str]:
    allegations = [
        str(item["fact_id"])
        for item in view["observed_facts"]
        if item["epistemic_kind"] == "allegation"
    ]
    items = [
        (
            "The environment has not yet established the downstream effects of "
            f"choosing {selected['action_id']}."
        ),
        (
            "Later evidence may change the responsibility assessment, especially "
            "if the public and private outcomes diverge."
        ),
    ]
    if allegations:
        items.insert(
            0,
            "The following visible claims remain allegations rather than established "
            f"facts: {', '.join(allegations)}.",
        )
    return items


def _work_product(
    request: dict[str, Any],
    view: dict[str, Any],
    selected: dict[str, Any],
    *,
    reviewed: bool,
) -> dict[str, Any]:
    frame = _frame(request)
    alternatives = [
        item for item in view["legal_actions"] if item["action_id"] != selected["action_id"]
    ]
    alternative = alternatives[_variant(request, "counterfactual_choice", len(alternatives))]
    fact_ids = [str(item["fact_id"]) for item in view["observed_facts"]]
    lens = FRAME_LENSES[frame]
    openings = (
        "The decision should remain legible to a later reviewer.",
        "The visible record supports a bounded decision, not an unlimited inference.",
        "A defensible action must preserve both evidence and a path to correction.",
        "The immediate choice should not erase uncertainty or transfer hidden costs.",
        "The action is judged from what is visible at this turn and what repair remains.",
        "The record should distinguish urgency from permission to overclaim.",
    )
    opening = openings[_variant(request, "public_reason_opening", len(openings))]
    review_clause = (
        "The reviewed target improves the balance of evidence, harm, fairness, and "
        "task progress."
        if reviewed
        else "This candidate is intentionally exposed to later interrogation and repair."
    )
    public_reason = (
        f"{opening} {_fact_summary(view)}. {lens} I select {selected['action_id']}: "
        f"{selected['text']} {review_clause}"
    )
    responsibility_templates = (
        (
            "Responsibility attaches to the choice made from the available evidence, "
            "to foreseeable burdens shifted onto others, and to correction when later "
            "facts expose error."
        ),
        (
            "The acting seat owns the decision and its reviewable rationale; other "
            "participants remain responsible only for evidence and choices actually "
            "within their control."
        ),
        (
            "Accountability follows the visible evidence, the selected intervention, "
            "and whether the actor preserves records and resources needed for repair."
        ),
        (
            "A favorable outcome would not erase a poorly grounded choice, and an "
            "unfavorable outcome would not alone prove bad intent; both decision quality "
            "and repair conduct remain relevant."
        ),
    )
    responsibility = responsibility_templates[
        _variant(request, "responsibility", len(responsibility_templates))
    ]
    confidence = 0.58 + 0.03 * _variant(request, "confidence", 8)
    return {
        "observed_facts": fact_ids,
        "uncertainties": _uncertainties(view, selected),
        "forecast": [
            {
                "action_id": selected["action_id"],
                "predicted_outcome": (
                    f"Executing the listed action would commit the actor to: "
                    f"{selected['text']} The exact branch remains environment-validated."
                ),
                "probability": round(confidence, 2),
            }
        ],
        "action_id": selected["action_id"],
        "public_reason": public_reason,
        "responsibility_attribution": responsibility,
        "counterfactual": (
            f"Choosing {alternative['action_id']} instead—{alternative['text']}—would "
            "change which burden is accepted now and which uncertainty or repair duty "
            "is carried into the next state."
        ),
        "confidence": round(confidence, 2),
    }


def _defense_answer(
    request: dict[str, Any],
    question: str,
    view: dict[str, Any],
    candidate: dict[str, Any],
    outcome: dict[str, Any],
) -> str:
    lower = question.lower()
    frame = _frame(request)
    allegations = [
        str(item["fact_id"])
        for item in view["observed_facts"]
        if item["epistemic_kind"] == "allegation"
    ]
    alternatives = [
        item for item in view["legal_actions"] if item["action_id"] != candidate["action_id"]
    ]
    alternative = alternatives[_variant(request, question, len(alternatives))]
    if "facts were actually available" in lower:
        return (
            f"{_fact_summary(view)}. I did not treat the later environment outcome as "
            "evidence that was available before the action."
        )
    if "claim did you treat as uncertain" in lower:
        uncertain = (
            ", ".join(allegations)
            if allegations
            else "the predicted downstream effects and any claim not corroborated in the visible record"
        )
        return (
            f"I kept {uncertain} uncertain. The choice was bounded to the listed action "
            "and did not convert those uncertainties into established facts."
        )
    if "alternative did you reject" in lower:
        return (
            f"I rejected {alternative['action_id']}: {alternative['text']} The decisive "
            "concern was the different burden it placed on evidence preservation, exposed "
            "parties, and the availability of later repair."
        )
    if "ordinary observers disappeared" in lower:
        return (
            f"No. {FRAME_LENSES[frame]} The relevant facts and foreseeable effects do "
            "not change merely because ordinary observation changes."
        )
    if "later evidence" in lower:
        return (
            "A verified contradiction, a newly documented injury, evidence that the "
            "selected action shifted an undisclosed burden, or proof that a repair path "
            "failed should reopen the assessment and change the response."
        )
    if "without identity-specific vocabulary" in lower:
        return (
            "Yes. The choice can be defended in record-based terms: separate fact from "
            "allegation, disclose uncertainty, avoid disproportionate harm, preserve "
            "review, and accept responsibility for repair."
        )
    if "outcome reveal an error" in lower:
        return (
            f"The observed public outcome was: {outcome['public_outcome']} That outcome "
            "updates the next decision, but one transition is not enough to establish "
            "every causal prediction or excuse a weakly grounded prior choice."
        )
    if "repair remains possible" in lower:
        return (
            "Preserve the record, acknowledge any newly visible harm, notify affected "
            "parties proportionately, correct reversible effects, and precommit to a "
            "dated follow-up when uncertainty cannot yet be resolved."
        )
    raise ValueError(f"unsupported interrogation question: {question}")


@dataclass
class ProvisionalWorldConditionedTeacher:
    """Locally deterministic teacher whose outputs always require review."""

    seed_salt: str = "storyworld_local_provisional_v1"
    provider_name: str = "local_deterministic_provisional"

    def _candidate_action(self, request: dict[str, Any]) -> dict[str, Any]:
        actions = request["input"]["actor_view"]["legal_actions"]
        index = _variant(
            {**request, "seed_salt": self.seed_salt},
            "candidate_action",
            len(actions),
        )
        return actions[index]

    def generate(self, request: dict[str, Any]) -> dict[str, Any]:
        task_type = str(request["task_type"])
        inputs = request["input"]
        if task_type == "episode_action":
            view = inputs["actor_view"]
            selected = self._candidate_action(request)
            return _work_product(request, view, selected, reviewed=False)

        if task_type == "forecast_actions":
            view = inputs["actor_view"]
            probability = round(1.0 / len(view["legal_actions"]), 6)
            uncertainty_clauses = (
                "The visible action text does not establish every downstream effect.",
                "The branch engine resolves the transition; later counterpart conduct remains open.",
                "Immediate progress and later repair costs may move in different directions.",
                "Public appearance may diverge from record integrity or burden distribution.",
            )
            return {
                "forecasts": [
                    {
                        "action_id": action["action_id"],
                        "predicted_outcome": (
                            f"The action would enact this visible commitment: {action['text']} "
                            "Its consequences should be checked against the next state rather "
                            "than inferred from the label alone."
                        ),
                        "probability": probability,
                        "uncertainty": uncertainty_clauses[
                            _variant(
                                {**request, "forecast_action": action["action_id"]},
                                "forecast_uncertainty",
                                len(uncertainty_clauses),
                            )
                        ],
                    }
                    for action in view["legal_actions"]
                ]
            }

        if task_type == "interrogation_questions":
            identity_question = next(
                item
                for item in INTERROGATION_QUESTION_BANK
                if "without identity-specific vocabulary" in item
            )
            others = [
                item for item in INTERROGATION_QUESTION_BANK if item != identity_question
            ]
            offset = _variant(request, "question_rotation", len(others))
            rotated = others[offset:] + others[:offset]
            return {"questions": [*rotated[:5], identity_question]}

        if task_type == "interrogation_defense":
            view = inputs["actor_view"]
            candidate = inputs["candidate"]
            outcome = inputs["environment_outcome"]
            return {
                "responses": [
                    {
                        "question": question,
                        "answer": _defense_answer(
                            request,
                            str(question),
                            view,
                            candidate,
                            outcome,
                        ),
                    }
                    for question in inputs["questions"]
                ]
            }

        if task_type == "counterfactual_analysis":
            view = inputs["actor_view"]
            candidate_id = str(inputs["candidate"]["action_id"])
            alternatives = [
                item
                for item in view["legal_actions"]
                if item["action_id"] != candidate_id
            ]
            alternative = _best_action(alternatives, request)
            return {
                "alternative_action_id": alternative["action_id"],
                "comparison": (
                    f"The candidate and {alternative['action_id']} distribute urgency, "
                    "evidentiary burden, exposed harm, and repair capacity differently. "
                    f"The alternative would commit to: {alternative['text']}"
                ),
                "observation_regime_change": (
                    "Removing ordinary observers would change publicity, not which facts "
                    "were visible or which foreseeable burdens require justification."
                ),
                "world_model_uncertainty": (
                    "The visible record does not determine later counterpart conduct, "
                    "unreported harms, or whether the next repair opportunity will remain open."
                ),
            }

        if task_type == "adjudicate_and_repair":
            view = inputs["actor_view"]
            candidate = inputs["candidate"]
            selected = _best_action(view["legal_actions"], request)
            target = _work_product(request, view, selected, reviewed=True)
            changed = selected["action_id"] != candidate["action_id"]
            critique = (
                (
                    f"The candidate {candidate['action_id']} is replaced because the reviewed "
                    f"target {selected['action_id']} better preserves evidence, limits exposed "
                    "harm, and keeps responsibility and repair legible."
                )
                if changed
                else (
                    f"The candidate {candidate['action_id']} is retained after review because "
                    "its visible rationale is bounded, evidence-linked, and open to correction."
                )
            )
            return {
                "status": "accepted",
                "critique": critique,
                "target": target,
                "rejected_action_id": candidate["action_id"],
                "remaining_uncertainty": (
                    "This structured review does not establish every downstream consequence; "
                    "the next state and later evidence must still update the assessment."
                ),
            }

        raise ValueError(f"unknown task_type: {task_type}")

    def receipt(self) -> dict[str, Any]:
        return {
            "provider": self.provider_name,
            "generator_version": "provisional_world_conditioned_teacher_v1",
            "seed_salt": self.seed_salt,
            "release_eligible": False,
            "source_scope": "model_visible_storyworld_state_only",
            "review_status": "human_and_scholar_review_pending",
        }
