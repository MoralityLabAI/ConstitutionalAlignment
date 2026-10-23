"""F3 versus F3-concrete token-parity balancing (amendment frame_internalization_parity_balance_v1).

Rule, fixed before any training or outcome:
  1. Candidates are training-split scenarios (validation rows do not enter the gated total).
  2. Rank candidates by the absolute difference between the rendered token counts of the
     F3_reflection and F3_concrete_reflection rows, largest first; ties by scenario ID ascending.
  3. Drop whole scenarios in that order from all four frames, recomputing the spread
     (max total - min total) / min total after each drop, and stop at the first drop for which
     the spread is at most the 2% gate. No drops if the gate already holds.
  4. At most 560 scenarios (10% of 5,600) may be dropped. If the gate is not met within the cap,
     the result is `parity_unreachable` and the study stops.
It selects on generated length, never on outcomes. Standard library only.
"""

from __future__ import annotations

import hashlib
from typing import Any

GATE = 0.02
CAP = 560


def spread(total_a: int, total_b: int) -> float:
    return (max(total_a, total_b) - min(total_a, total_b)) / min(total_a, total_b)


def select_drops(f3_tokens: dict[str, int], f3c_tokens: dict[str, int], gate: float = GATE, cap: int = CAP) -> dict[str, Any]:
    """f3_tokens / f3c_tokens: training-split scenario ID -> rendered token count."""
    if set(f3_tokens) != set(f3c_tokens):
        raise ValueError("the two arms must cover the same scenarios")
    total_a, total_b = sum(f3_tokens.values()), sum(f3c_tokens.values())
    initial = spread(total_a, total_b)
    order = sorted(f3_tokens, key=lambda sid: (-abs(f3_tokens[sid] - f3c_tokens[sid]), sid))
    drops: list[str] = []
    current = initial
    for sid in order:
        if current <= gate:
            break
        if len(drops) >= cap:
            break
        total_a -= f3_tokens[sid]
        total_b -= f3c_tokens[sid]
        drops.append(sid)
        current = spread(total_a, total_b)
    return {"status": "balanced" if current <= gate else "parity_unreachable", "dropped": drops,
            "initial_spread": initial, "final_spread": current, "cap": cap, "gate": gate,
            "remaining_train_scenarios": len(f3_tokens) - len(drops)}


def drop_list_sha256(drops: list[str]) -> str:
    return hashlib.sha256(("\n".join(drops) + "\n").encode("utf-8")).hexdigest()


class ParityError(RuntimeError):
    pass


def verify_against_amendment(f3_tokens: dict[str, int], f3c_tokens: dict[str, int], amendment: dict[str, Any]) -> dict[str, Any]:
    """Re-derive the rule from the rendered counts and require it to match the recorded result.

    Returns the rule result. Raises if the recorded rule parameters, status, drop list or final
    spread differ, so the amendment cannot be applied to data it was not computed on."""
    rule = amendment["rule"]
    if (rule["gate"], rule["cap"]) != (GATE, CAP):
        raise ParityError("amendment parameters differ from the code constants")
    result = select_drops(f3_tokens, f3c_tokens, gate=rule["gate"], cap=rule["cap"])
    recorded = amendment["result"]
    if result["status"] != recorded["status"]:
        raise ParityError(f"rule status {result['status']} != recorded {recorded['status']}")
    if drop_list_sha256(result["dropped"]) != recorded["drop_list_sha256"]:
        raise ParityError("drop list differs from the recorded hash")
    if abs(result["final_spread"] - recorded["final_spread"]) > 1e-9:
        raise ParityError("final spread differs from the recorded value")
    return result


def scenarios_to_drop(result: dict[str, Any]) -> set[str]:
    """Drops are applied only when the rule reached the gate; an unreachable outcome drops nothing."""
    return set(result["dropped"]) if result["status"] == "balanced" else set()
