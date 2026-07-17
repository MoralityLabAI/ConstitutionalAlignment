"""Branching storyworld primitives for trajectory-curriculum construction.

The world contract deliberately separates dynamics from adjudication.  A world
declares observations, legal actions, transitions, and predicted consequence
dimensions.  It does *not* declare a canonical moral action.  Teacher and human
review happens in the trajectory layer, while this module validates only
structural, epistemic, and deterministic transition claims.
"""

from __future__ import annotations

import hashlib
import json
import random
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_WORLD_SCHEMA = REPO_ROOT / "schemas" / "storyworld_branching_world_v1.schema.json"
DEFAULT_OVERLAY_SCHEMA = REPO_ROOT / "schemas" / "storyworld_skin_overlay_v1.schema.json"
DEFAULT_SPLIT_FREEZE_SCHEMA = REPO_ROOT / "schemas" / "storyworld_split_freeze_v1.schema.json"
DEFAULT_INSTANCE_SWEEP_SCHEMA = REPO_ROOT / "schemas" / "storyworld_instance_sweep_v1.schema.json"
DEFAULT_BLINDED_EVAL_PROTOCOL_SCHEMA = (
    REPO_ROOT / "schemas" / "storyworld_blinded_eval_protocol_v1.schema.json"
)
INSTANCE_FACTORS = {
    "resources",
    "observation",
    "authority",
    "timing",
    "counterpart_behavior",
}


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_json(value: Any) -> str:
    return sha256_bytes(canonical_json(value).encode("utf-8"))


def reviewable_world_sha256(world: dict[str, Any]) -> str:
    """Hash substantive review content while excluding mutable workflow state."""
    payload = deepcopy(world)
    review = payload["review"]
    payload["review"] = {
        "requirements": [
            {"review_type": str(item["review_type"])}
            for item in review["requirements"]
        ],
        "claim_boundary": str(review["claim_boundary"]),
    }
    return sha256_json(payload)


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object in {path}")
    return value


def read_world(path: Path) -> dict[str, Any]:
    """Read a full world or materialize a keyed skin overlay.

    Skin overlays keep language changes reviewable while inheriting one exact
    causal graph.  The returned object is always a complete
    ``storyworld_branching_world_v1`` instance.
    """
    raw = read_json(path)
    if raw.get("schema_version") == "storyworld_branching_world_v1":
        return raw
    if raw.get("schema_version") != "storyworld_skin_overlay_v1":
        raise ValueError(f"unsupported world schema in {path}: {raw.get('schema_version')}")
    base_path = (path.parent / str(raw["base_world_path"])).resolve()
    world = deepcopy(read_world(base_path))
    for key, value in raw.get("top_level", {}).items():
        if key in {"states", "facts", "agents"}:
            raise ValueError(f"{path}: keyed collections must use their dedicated overlay maps")
        world[str(key)] = deepcopy(value)

    agents = {str(item["agent_id"]): item for item in world["agents"]}
    for agent_id, updates in raw.get("agents_by_id", {}).items():
        if agent_id not in agents:
            raise ValueError(f"{path}: overlay references unknown agent {agent_id}")
        agents[agent_id].update(deepcopy(updates))

    facts = {str(item["fact_id"]): item for item in world["facts"]}
    for fact_id, updates in raw.get("facts_by_id", {}).items():
        if fact_id not in facts:
            raise ValueError(f"{path}: overlay references unknown fact {fact_id}")
        facts[fact_id].update(deepcopy(updates))

    states = {str(item["state_id"]): item for item in world["states"]}
    for state_id, updates in raw.get("states_by_id", {}).items():
        if state_id not in states:
            raise ValueError(f"{path}: overlay references unknown state {state_id}")
        state_updates = deepcopy(updates)
        action_updates = state_updates.pop("actions_by_key", {})
        states[state_id].update(state_updates)
        actions = {str(item["action_key"]): item for item in states[state_id]["actions"]}
        for action_key, values in action_updates.items():
            if action_key not in actions:
                raise ValueError(
                    f"{path}: overlay references unknown action {state_id}/{action_key}"
                )
            actions[action_key].update(deepcopy(values))
    validate_world(world)
    return world


def _apply_instance_overrides(
    world: dict[str, Any], overrides: dict[str, Any], location: str
) -> None:
    for key, value in overrides.get("initial_variables", {}).items():
        if key not in world["initial_variables"]:
            raise ValueError(f"{location}: unknown initial variable {key}")
        world["initial_variables"][str(key)] = int(value)

    agents = {str(item["agent_id"]): item for item in world["agents"]}
    for agent_id, updates in overrides.get("agents_by_id", {}).items():
        if agent_id not in agents:
            raise ValueError(f"{location}: unknown agent {agent_id}")
        agents[agent_id].update(deepcopy(updates))

    facts = {str(item["fact_id"]): item for item in world["facts"]}
    for fact_id, updates in overrides.get("facts_by_id", {}).items():
        if fact_id not in facts:
            raise ValueError(f"{location}: unknown fact {fact_id}")
        facts[fact_id].update(deepcopy(updates))

    states = {str(item["state_id"]): item for item in world["states"]}
    for state_id, updates in overrides.get("states_by_id", {}).items():
        if state_id not in states:
            raise ValueError(f"{location}: unknown state {state_id}")
        state_updates = deepcopy(updates)
        action_updates = state_updates.pop("actions_by_key", {})
        states[state_id].update(state_updates)
        actions = {str(item["action_key"]): item for item in states[state_id]["actions"]}
        for action_key, values in action_updates.items():
            if action_key not in actions:
                raise ValueError(f"{location}: unknown action {state_id}/{action_key}")
            actions[action_key].update(deepcopy(values))


def materialize_instance_sweep(
    repo_root: Path,
    sweep_path: Path,
    schema_path: Path | None = DEFAULT_INSTANCE_SWEEP_SCHEMA,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Materialize and validate standalone or paired worlds from an explicit sweep."""
    sweep = read_json(sweep_path)
    if schema_path is not None:
        errors = _schema_errors(sweep, Path(schema_path))
        if errors:
            raise ValueError("instance sweep schema failure: " + "; ".join(errors))
    if sweep.get("schema_version") != "storyworld_instance_sweep_v1":
        raise ValueError("unexpected instance sweep schema")
    required_factors = set(map(str, sweep["required_factors"]))
    if required_factors != INSTANCE_FACTORS:
        raise ValueError(f"instance sweep must declare exactly {sorted(INSTANCE_FACTORS)}")

    base_paths = [repo_root / str(value) for value in sweep["base_world_paths"]]
    bases = [read_world(path) for path in base_paths]
    if len(bases) not in {1, 2}:
        raise ValueError("instance sweep requires one standalone base or two matched bases")
    paired = len(bases) == 2
    if paired:
        validate_matched_pair(bases[0], bases[1])
    elif bases[0].get("matched_pair") is not None:
        raise ValueError("a one-base instance sweep requires a standalone world")
    base_by_id = {str(world["world_id"]): world for world in bases}
    if len(base_by_id) != len(bases):
        raise ValueError("instance sweep base worlds must have distinct IDs")

    profiles = sweep["profiles"]
    profile_ids = [str(item["profile_id"]) for item in profiles]
    if len(set(profile_ids)) != len(profile_ids):
        raise ValueError("instance sweep profile_id values must be unique")
    factor_values: dict[str, set[str]] = {factor: set() for factor in INSTANCE_FACTORS}
    for profile in profiles:
        values = {str(key): str(value) for key, value in profile["factor_values"].items()}
        if set(values) != INSTANCE_FACTORS:
            raise ValueError(
                f"profile {profile['profile_id']} must specify every required factor exactly once"
            )
        for factor, value in values.items():
            factor_values[factor].add(value)
    invariant_factors = sorted(factor for factor, values in factor_values.items() if len(values) < 2)
    if invariant_factors:
        raise ValueError(f"instance sweep does not vary required factors: {invariant_factors}")

    materialized: list[dict[str, Any]] = []
    profile_receipts: list[dict[str, Any]] = []
    for profile in profiles:
        profile_id = str(profile["profile_id"])
        generated_ids = {
            base_id: f"{base_id}__{profile_id}" for base_id in sorted(base_by_id)
        }
        pair_id = (
            f"{bases[0]['matched_pair']['pair_id']}__{profile_id}" if paired else None
        )
        graph_id = (
            f"{bases[0]['matched_pair']['transition_graph_id']}__{profile_id}"
            if paired
            else None
        )
        pair_worlds: list[dict[str, Any]] = []
        for base_id, base in base_by_id.items():
            world = deepcopy(base)
            _apply_instance_overrides(
                world,
                profile["overrides"],
                f"{sweep_path}:{profile_id}:{base_id}",
            )
            world["world_id"] = generated_ids[base_id]
            world["title"] = f"{base['title']} [{profile_id}]"
            if paired:
                counterpart_base_id = str(base["matched_pair"]["counterpart_world_id"])
                world["matched_pair"] = {
                    **deepcopy(base["matched_pair"]),
                    "pair_id": pair_id,
                    "counterpart_world_id": generated_ids[counterpart_base_id],
                    "transition_graph_id": graph_id,
                }
            else:
                world["matched_pair"] = None
            world["instance_provenance"] = {
                "sweep_id": sweep["sweep_id"],
                "profile_id": profile_id,
                "base_world_id": base_id,
                "base_world_sha256": sha256_json(base),
                "factor_values": deepcopy(profile["factor_values"]),
            }
            validate_world(world)
            pair_worlds.append(world)
            materialized.append(world)
        pair_receipt = (
            validate_matched_pair(pair_worlds[0], pair_worlds[1]) if paired else None
        )
        profile_receipts.append(
            {
                "profile_id": profile_id,
                "description": profile["description"],
                "factor_values": deepcopy(profile["factor_values"]),
                "world_ids": sorted(world["world_id"] for world in pair_worlds),
                "world_content_sha256": sorted(sha256_json(world) for world in pair_worlds),
                "matched_pair": pair_receipt,
            }
        )
    return materialized, {
        "schema_version": "storyworld_instance_sweep_receipt_v1",
        "sweep_id": sweep["sweep_id"],
        "sweep_path": sweep_path.relative_to(repo_root).as_posix(),
        "sweep_sha256": sha256_file(sweep_path),
        "base_world_ids": sorted(base_by_id),
        "profiles": len(profiles),
        "materialized_worlds": len(materialized),
        "factor_cardinality": {
            factor: len(values) for factor, values in sorted(factor_values.items())
        },
        "profile_receipts": profile_receipts,
        "passed": True,
    }


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    temporary.replace(path)


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    temporary.replace(path)


def _schema_errors(instance: dict[str, Any], schema_path: Path) -> list[str]:
    try:
        from jsonschema import Draft202012Validator
    except ImportError as exc:  # pragma: no cover - validation environment installs it
        raise RuntimeError("storyworld validation requires jsonschema") from exc
    schema = read_json(schema_path)
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(instance), key=lambda item: list(item.path))
    return [
        f"{'/'.join(map(str, error.path)) or '<root>'}: {error.message}"
        for error in errors
    ]


def transition_graph_payload(world: dict[str, Any]) -> dict[str, Any]:
    """Return the language-independent causal graph used for matched skins."""
    dimensions = [str(item["dimension_id"]) for item in world["consequence_dimensions"]]
    states: list[dict[str, Any]] = []
    for state in sorted(world["states"], key=lambda item: str(item["state_id"])):
        actions: list[dict[str, Any]] = []
        for action in sorted(state.get("actions", []), key=lambda item: str(item["action_key"])):
            vector = {dimension: 0 for dimension in dimensions}
            for consequence in action["consequences"]:
                for dimension, value in consequence["dimension_effects"].items():
                    vector[str(dimension)] += int(value)
            actions.append(
                {
                    "action_key": action["action_key"],
                    "next_state": action["next_state"],
                    "variable_effects": action["variable_effects"],
                    "consequence_vector": vector,
                    "repairs_consequences": sorted(action["repairs_consequences"]),
                    "tags": sorted(action["tags"]),
                }
            )
        states.append(
            {
                "state_id": state["state_id"],
                "turn_index": state["turn_index"],
                "terminal": state["terminal"],
                "active_fact_ids": sorted(state["active_fact_ids"]),
                "actions": actions,
            }
        )
    obligations = [
        {
            "constraint_id": item["constraint_id"],
            "frame": item["frame"],
            "applies_in_states": sorted(item["applies_in_states"]),
            "required_action_tags_any": sorted(item["required_action_tags_any"]),
            "forbidden_action_tags": sorted(item["forbidden_action_tags"]),
        }
        for item in sorted(world["obligations"], key=lambda item: (item["frame"], item["constraint_id"]))
    ]
    return {
        "transition_graph_id": (
            world["matched_pair"]["transition_graph_id"]
            if world["matched_pair"] is not None
            else world["world_id"]
        ),
        "entry_state": world["entry_state"],
        "initial_variables": world["initial_variables"],
        "dimensions": dimensions,
        "states": states,
        "obligations": obligations,
    }


def transition_graph_sha256(world: dict[str, Any]) -> str:
    return sha256_json(transition_graph_payload(world))


def _action_vector(action: dict[str, Any], dimensions: Sequence[str]) -> tuple[int, ...]:
    totals = {dimension: 0 for dimension in dimensions}
    for consequence in action["consequences"]:
        for dimension, value in consequence["dimension_effects"].items():
            totals[str(dimension)] += int(value)
    return tuple(totals[dimension] for dimension in dimensions)


def _pareto_frontier(actions: Sequence[dict[str, Any]], dimensions: Sequence[str]) -> list[str]:
    vectors = {str(action["action_key"]): _action_vector(action, dimensions) for action in actions}
    frontier: list[str] = []
    for candidate, candidate_vector in vectors.items():
        dominated = False
        for other, other_vector in vectors.items():
            if other == candidate:
                continue
            if all(a >= b for a, b in zip(other_vector, candidate_vector)) and any(
                a > b for a, b in zip(other_vector, candidate_vector)
            ):
                dominated = True
                break
        if not dominated:
            frontier.append(candidate)
    return sorted(frontier)


def _enumerate_path_lengths(
    state_id: str,
    states: dict[str, dict[str, Any]],
    stack: tuple[str, ...] = (),
) -> list[int]:
    if state_id in stack:
        cycle = " -> ".join((*stack, state_id))
        raise ValueError(f"storyworld graph must be acyclic; cycle: {cycle}")
    state = states[state_id]
    if state["terminal"]:
        return [0]
    lengths: list[int] = []
    for action in state["actions"]:
        lengths.extend(
            1 + suffix
            for suffix in _enumerate_path_lengths(
                str(action["next_state"]), states, (*stack, state_id)
            )
        )
    return lengths


def validate_world(
    world: dict[str, Any],
    schema_path: Path | None = DEFAULT_WORLD_SCHEMA,
) -> dict[str, Any]:
    """Validate schema plus the causal/epistemic invariants schema cannot express."""
    if schema_path is not None:
        errors = _schema_errors(world, Path(schema_path))
        if errors:
            raise ValueError("world schema failure: " + "; ".join(errors))

    world_id = str(world["world_id"])
    source_split = str(world["source_split"])
    if bool(world["training_eligible"]) is not (source_split == "train"):
        raise ValueError(f"{world_id}: only train worlds may be training_eligible")
    if world["theological_motif"] is not None and world["matched_pair"] is None:
        raise ValueError(f"{world_id}: theological motifs require a matched secular skin")

    review = world["review"]
    review_requirements = review["requirements"]
    review_types = [str(item["review_type"]) for item in review_requirements]
    if len(review_types) != len(set(review_types)):
        raise ValueError(f"{world_id}: duplicate review requirement")
    if world["theological_motif"] is not None and "quranic_scholar" not in review_types:
        raise ValueError(f"{world_id}: theological motif lacks Quranic scholar review")
    for requirement in review_requirements:
        requirement_status = str(requirement["status"])
        receipt = requirement.get("receipt")
        if requirement_status in {"approved", "rejected"} and not str(receipt or "").strip():
            raise ValueError(
                f"{world_id}: {requirement['review_type']} {requirement_status} without receipt"
            )
        if requirement_status == "pending" and receipt is not None:
            raise ValueError(
                f"{world_id}: pending {requirement['review_type']} cannot carry a receipt"
            )
    if review["status"] == "approved" and any(
        item["status"] not in {"approved", "not_required"}
        for item in review_requirements
    ):
        raise ValueError(f"{world_id}: approved world has incomplete review requirements")
    if review["status"] == "rejected" and not any(
        item["status"] == "rejected" for item in review_requirements
    ):
        raise ValueError(f"{world_id}: rejected world has no rejected review requirement")

    agents = [str(item["agent_id"]) for item in world["agents"]]
    if len(set(agents)) != len(agents):
        raise ValueError(f"{world_id}: duplicate agent_id")
    actor_id = str(world["actor_agent_id"])
    if actor_id not in agents:
        raise ValueError(f"{world_id}: actor_agent_id is not declared")

    variables = set(map(str, world["initial_variables"]))
    dimensions = [str(item["dimension_id"]) for item in world["consequence_dimensions"]]
    if len(set(dimensions)) != len(dimensions):
        raise ValueError(f"{world_id}: duplicate consequence dimension")

    facts = {str(item["fact_id"]): item for item in world["facts"]}
    if len(facts) != len(world["facts"]):
        raise ValueError(f"{world_id}: duplicate fact_id")
    private_evidence = False
    for fact_id, fact in facts.items():
        visibility = set(map(str, fact["visible_to"]))
        unknown_agents = visibility.difference({"public", *agents})
        if unknown_agents:
            raise ValueError(f"{world_id}/{fact_id}: unknown visibility seats {sorted(unknown_agents)}")
        if "public" not in visibility and visibility and visibility != set(agents):
            private_evidence = True
    if not private_evidence:
        raise ValueError(f"{world_id}: at least one fact must be private to a proper subset of agents")

    states = {str(item["state_id"]): item for item in world["states"]}
    if len(states) != len(world["states"]):
        raise ValueError(f"{world_id}: duplicate state_id")
    if world["entry_state"] not in states:
        raise ValueError(f"{world_id}: entry_state is missing")

    all_action_keys: set[str] = set()
    all_consequence_ids: set[str] = set()
    for state_id, state in states.items():
        missing_facts = set(map(str, state["active_fact_ids"])).difference(facts)
        if missing_facts:
            raise ValueError(f"{world_id}/{state_id}: unknown facts {sorted(missing_facts)}")
        if set(state["private_observations"]).difference(agents):
            raise ValueError(f"{world_id}/{state_id}: private observation for unknown agent")
        for action in state["actions"]:
            action_key = str(action["action_key"])
            if action_key in all_action_keys:
                raise ValueError(f"{world_id}: action_key must be globally unique: {action_key}")
            all_action_keys.add(action_key)
            if action["next_state"] not in states:
                raise ValueError(f"{world_id}/{action_key}: unknown next_state")
            unknown_variables = set(map(str, action["variable_effects"])).difference(variables)
            if unknown_variables:
                raise ValueError(
                    f"{world_id}/{action_key}: effects reference unknown variables {sorted(unknown_variables)}"
                )
            for consequence in action["consequences"]:
                consequence_id = str(consequence["consequence_id"])
                if consequence_id in all_consequence_ids:
                    raise ValueError(f"{world_id}: duplicate consequence_id {consequence_id}")
                all_consequence_ids.add(consequence_id)
                if set(map(str, consequence["dimension_effects"])) != set(dimensions):
                    raise ValueError(
                        f"{world_id}/{action_key}: consequence dimensions must exactly match world dimensions"
                    )

    for state in states.values():
        for action in state["actions"]:
            missing = set(map(str, action["repairs_consequences"])).difference(all_consequence_ids)
            if missing:
                raise ValueError(
                    f"{world_id}/{action['action_key']}: repairs unknown consequences {sorted(missing)}"
                )

    entry = str(world["entry_state"])
    path_lengths = _enumerate_path_lengths(entry, states)
    if not path_lengths or min(path_lengths) < 6 or max(path_lengths) > 10:
        raise ValueError(
            f"{world_id}: every path must contain 6-10 decision turns; observed {sorted(set(path_lengths))}"
        )

    reachable: set[str] = set()
    frontier = [entry]
    while frontier:
        state_id = frontier.pop()
        if state_id in reachable:
            continue
        reachable.add(state_id)
        frontier.extend(str(action["next_state"]) for action in states[state_id]["actions"])
    unreachable = set(states).difference(reachable)
    if unreachable:
        raise ValueError(f"{world_id}: unreachable states {sorted(unreachable)}")
    reachable_terminals = [state_id for state_id in reachable if states[state_id]["terminal"]]
    if len(reachable_terminals) < 2:
        raise ValueError(f"{world_id}: at least two reachable endings are required")

    branch_states = [
        state
        for state in states.values()
        if len({str(action["next_state"]) for action in state["actions"]}) >= 2
    ]
    if not branch_states:
        raise ValueError(f"{world_id}: actions never change the reachable state")
    later_legality_differs = False
    for state in branch_states:
        successor_sets = {
            tuple(sorted(str(action["action_key"]) for action in states[str(edge["next_state"])]["actions"]))
            for edge in state["actions"]
        }
        if len(successor_sets) >= 2:
            later_legality_differs = True
            break
    if not later_legality_differs:
        raise ValueError(f"{world_id}: branching must alter a later legal-action menu")

    frontier_by_state: dict[str, list[str]] = {}
    for state_id, state in states.items():
        if state["terminal"]:
            continue
        pareto = _pareto_frontier(state["actions"], dimensions)
        frontier_by_state[state_id] = pareto
        if len(pareto) < 2:
            raise ValueError(
                f"{world_id}/{state_id}: one action Pareto-dominates the menu; add a real tradeoff"
            )

    obligation_states = set(states)
    for obligation in world["obligations"]:
        applies = set(map(str, obligation["applies_in_states"]))
        if applies != {"*"} and not applies.issubset(obligation_states):
            raise ValueError(
                f"{world_id}/{obligation['constraint_id']}: obligation references unknown states"
            )

    return {
        "schema_version": "storyworld_validation_receipt_v1",
        "world_id": world_id,
        "source_split": source_split,
        "training_eligible": bool(world["training_eligible"]),
        "states": len(states),
        "decision_states": sum(not bool(item["terminal"]) for item in states.values()),
        "reachable_endings": len(reachable_terminals),
        "path_turns_min": min(path_lengths),
        "path_turns_max": max(path_lengths),
        "branch_states": len(branch_states),
        "private_evidence": private_evidence,
        "pareto_frontier_by_state": frontier_by_state,
        "transition_graph_sha256": transition_graph_sha256(world),
        "passed": True,
    }


def validate_matched_pair(first: dict[str, Any], second: dict[str, Any]) -> dict[str, Any]:
    first_receipt = validate_world(first)
    second_receipt = validate_world(second)
    first_pair = first["matched_pair"]
    second_pair = second["matched_pair"]
    if first_pair is None or second_pair is None:
        raise ValueError("standalone worlds cannot be validated as a matched pair")
    if first_pair["pair_id"] != second_pair["pair_id"]:
        raise ValueError("matched worlds use different pair_id values")
    if first_pair["counterpart_world_id"] != second["world_id"]:
        raise ValueError("first matched_pair counterpart_world_id is incorrect")
    if second_pair["counterpart_world_id"] != first["world_id"]:
        raise ValueError("second matched_pair counterpart_world_id is incorrect")
    if first_pair["skin_id"] == second_pair["skin_id"]:
        raise ValueError("matched worlds must use distinct skin_id values")
    if first_receipt["transition_graph_sha256"] != second_receipt["transition_graph_sha256"]:
        raise ValueError("matched skins do not share an identical causal graph")
    return {
        "schema_version": "storyworld_matched_pair_receipt_v1",
        "pair_id": first_pair["pair_id"],
        "world_ids": sorted([first["world_id"], second["world_id"]]),
        "skin_ids": sorted([first_pair["skin_id"], second_pair["skin_id"]]),
        "transition_graph_sha256": first_receipt["transition_graph_sha256"],
        "passed": True,
    }


def validate_split_freeze(
    inventory: dict[str, Any],
    split_freeze: dict[str, Any],
    *,
    repo_root: Path = REPO_ROOT,
    schema_path: Path | None = DEFAULT_SPLIT_FREEZE_SCHEMA,
) -> dict[str, Any]:
    """Validate family assignments using manifests only.

    Pending and sealed family content is deliberately not opened. Only content
    already declared ``implemented_pending_review`` is resolved and validated.
    """
    if schema_path is not None:
        errors = _schema_errors(split_freeze, Path(schema_path))
        if errors:
            raise ValueError("split-freeze schema failure: " + "; ".join(errors))
    if inventory.get("schema_version") != "storyworld_source_inventory_v1":
        raise ValueError("unexpected source inventory schema")

    sources = {str(item["source_id"]): item for item in inventory["sources"]}
    if len(sources) != len(inventory["sources"]):
        raise ValueError("source inventory contains duplicate source_id values")
    families = {str(item["family_id"]): item for item in split_freeze["families"]}
    if len(families) != len(split_freeze["families"]):
        raise ValueError("split freeze contains duplicate family_id values")
    clusters = [str(item["causal_cluster_id"]) for item in families.values()]
    if len(set(clusters)) != len(clusters):
        duplicates = sorted({item for item in clusters if clusters.count(item) > 1})
        raise ValueError(f"cross-split causal cluster collision: {duplicates}")

    actual_counts = {
        split: sum(item["assigned_split"] == split for item in families.values())
        for split in ("train", "development", "evaluation")
    }
    expected_counts = {
        key: int(value) for key, value in split_freeze["target_counts"].items()
    }
    if actual_counts != expected_counts:
        raise ValueError(
            f"split family counts do not match frozen targets: {actual_counts} != {expected_counts}"
        )

    origin_owners: dict[str, str] = {}
    implemented_receipts: list[dict[str, Any]] = []
    for family_id, family in families.items():
        split = str(family["assigned_split"])
        if bool(family["training_eligible"]) is not (split == "train"):
            raise ValueError(f"{family_id}: only train families may be training eligible")
        if bool(family["sealed"]) is not (split == "evaluation"):
            raise ValueError(f"{family_id}: only evaluation families may be sealed")
        unknown_origins = set(map(str, family["origin_source_ids"])).difference(sources)
        if unknown_origins:
            raise ValueError(f"{family_id}: unknown origin sources {sorted(unknown_origins)}")
        for source_id in map(str, family["origin_source_ids"]):
            if source_id in origin_owners:
                raise ValueError(
                    f"source {source_id} assigned to multiple families: "
                    f"{origin_owners[source_id]}, {family_id}"
                )
            origin_owners[source_id] = family_id
            source_split = str(sources[source_id]["current_split"])
            if split == "train" and source_split in {"evaluation", "holdout"}:
                raise ValueError(f"sealed source {source_id} cannot seed train family {family_id}")
        motif = family["theological_motif"]
        if motif is not None:
            if family["matched_skin_policy"] != "required":
                raise ValueError(f"{family_id}: theological motifs require a matched secular skin")
            if "quranic_scholar" not in family["review_requirements"]:
                raise ValueError(f"{family_id}: theological motif lacks Quranic scholar review")
        paths = list(map(str, family["content_paths"]))
        if family["content_status"] == "implemented_pending_review":
            if not paths:
                raise ValueError(f"{family_id}: implemented family has no content paths")
            resolved_worlds: list[dict[str, Any]] = []
            for relative in paths:
                path = repo_root / relative
                if not path.is_file():
                    raise ValueError(f"{family_id}: implemented content path is missing: {relative}")
                world = read_world(path)
                if world["family_id"] != family_id:
                    raise ValueError(f"{family_id}: resolved world family_id mismatch in {relative}")
                if world["source_split"] != split:
                    raise ValueError(f"{family_id}: resolved world split mismatch in {relative}")
                resolved_worlds.append(world)
            if family["matched_skin_policy"] == "required":
                if len(resolved_worlds) != 2:
                    raise ValueError(f"{family_id}: matched family must resolve exactly two skins")
                pair_receipt = validate_matched_pair(resolved_worlds[0], resolved_worlds[1])
            else:
                pair_receipt = None
            implemented_receipts.append(
                {
                    "family_id": family_id,
                    "paths": paths,
                    "resolved_world_ids": sorted(world["world_id"] for world in resolved_worlds),
                    "resolved_content_sha256": sorted(sha256_json(world) for world in resolved_worlds),
                    "matched_pair": pair_receipt,
                }
            )
        elif paths:
            raise ValueError(f"{family_id}: pending content must not publish paths before content freeze")

    dispositions = split_freeze["source_dispositions"]
    disposition_sources = [str(item["source_id"]) for item in dispositions]
    if len(set(disposition_sources)) != len(disposition_sources):
        raise ValueError("split freeze contains duplicate source dispositions")
    if set(disposition_sources) != set(sources):
        raise ValueError(
            "source dispositions must cover every inventory source exactly once; "
            f"missing={sorted(set(sources).difference(disposition_sources))}, "
            f"extra={sorted(set(disposition_sources).difference(sources))}"
        )
    for disposition in dispositions:
        source_id = str(disposition["source_id"])
        target = disposition["target_family_id"]
        kind = str(disposition["disposition"])
        if kind == "legacy_diagnostic_only":
            if target is not None:
                raise ValueError(f"legacy diagnostic {source_id} must not name a target family")
            continue
        if target not in families:
            raise ValueError(f"{source_id}: disposition references unknown family {target}")
        if source_id not in families[str(target)]["origin_source_ids"]:
            raise ValueError(f"{source_id}: target family does not record it as an origin")
        target_split = families[str(target)]["assigned_split"]
        if kind == "sealed_evaluation_input" and target_split != "evaluation":
            raise ValueError(f"{source_id}: sealed input must target evaluation")
        if kind == "migration_input" and target_split == "evaluation":
            raise ValueError(f"{source_id}: migration input cannot target sealed evaluation")
        current_split = str(sources[source_id]["current_split"])
        if current_split in {"evaluation", "holdout"} and kind == "migration_input":
            raise ValueError(f"sealed inventory source {source_id} cannot be a migration input")
        if current_split == "paired_development_and_evaluation" and kind == "migration_input":
            if disposition["allowed_variant"] != "development_only":
                raise ValueError(f"{source_id}: paired Mizan migration must be development-only")

    exclusion_sources: set[str] = set()
    for exclusion in split_freeze["leakage_exclusions"]:
        unknown = set(map(str, exclusion["source_ids"])).difference(sources)
        if unknown:
            raise ValueError(f"leakage exclusion references unknown sources {sorted(unknown)}")
        exclusion_sources.update(map(str, exclusion["source_ids"]))
    required_exclusions = {
        str(item["source_id"])
        for item in dispositions
        if item["disposition"] == "legacy_diagnostic_only"
        or item["allowed_variant"] == "development_only"
    }
    if not required_exclusions.issubset(exclusion_sources):
        raise ValueError(
            f"leakage exclusions omit restricted sources {sorted(required_exclusions - exclusion_sources)}"
        )

    train_motifs = {
        str(item["theological_motif"])
        for item in families.values()
        if item["assigned_split"] == "train" and item["theological_motif"] is not None
    }
    required_train_motifs = {"amanah", "ghayb_boundary", "mizan", "tawbah", "shura"}
    if train_motifs != required_train_motifs:
        raise ValueError(
            f"frozen train motif lane must be exactly {sorted(required_train_motifs)}; "
            f"observed {sorted(train_motifs)}"
        )

    return {
        "schema_version": "storyworld_split_freeze_validation_v1",
        "freeze_id": split_freeze["freeze_id"],
        "status": split_freeze["status"],
        "family_counts": actual_counts,
        "unique_causal_clusters": len(set(clusters)),
        "source_dispositions": len(dispositions),
        "legacy_or_variant_restricted_sources": len(required_exclusions),
        "train_motifs": sorted(train_motifs),
        "implemented_families": implemented_receipts,
        "sealed_content_opened": False,
        "passed": True,
    }


def validate_blinded_eval_protocol(
    split_freeze: dict[str, Any],
    protocol: dict[str, Any],
    *,
    schema_path: Path | None = DEFAULT_BLINDED_EVAL_PROTOCOL_SCHEMA,
) -> dict[str, Any]:
    """Validate the public author brief and closed one-time unseal gate.

    This function deliberately consumes only manifests. It never resolves an
    evaluation content path or reads a sealed submission.
    """
    if schema_path is not None:
        errors = _schema_errors(protocol, Path(schema_path))
        if errors:
            raise ValueError("blinded-eval protocol schema failure: " + "; ".join(errors))
    if protocol["split_freeze_id"] != split_freeze["freeze_id"]:
        raise ValueError("blinded-eval protocol references a different split freeze")

    allowed_fields = {
        "family_id",
        "causal_cluster_id",
        "construct",
        "authoring_mode",
        "review_requirements",
    }
    if set(protocol["author_visibility"]["allowed_family_fields"]) != allowed_fields:
        raise ValueError("blinded author visibility must be limited to the five family-level fields")

    split_families = {
        str(item["family_id"]): item
        for item in split_freeze["families"]
        if item["assigned_split"] == "evaluation"
    }
    protocol_families = {
        str(item["family_id"]): item for item in protocol["evaluation_families"]
    }
    if set(protocol_families) != set(split_families):
        raise ValueError("blinded-eval protocol must cover every sealed family exactly once")
    if len(protocol_families) != int(protocol["sealed_submission"]["expected_families"]):
        raise ValueError("sealed submission family count drifted")

    for family_id, family in split_families.items():
        if family["content_paths"]:
            raise ValueError(f"{family_id}: closed protocol cannot publish evaluation content paths")
        if not family["sealed"] or family["training_eligible"]:
            raise ValueError(f"{family_id}: evaluation family sealing or eligibility drifted")
        public = protocol_families[family_id]
        expected_mode = (
            "upgrade_existing_in_sealed_environment"
            if family["content_status"] == "sealed_existing_pending_upgrade"
            else "blind_original_authoring"
        )
        expected = {
            "family_id": family_id,
            "causal_cluster_id": family["causal_cluster_id"],
            "construct": family["construct"],
            "authoring_mode": expected_mode,
            "review_requirements": family["review_requirements"],
        }
        if public != expected:
            raise ValueError(f"{family_id}: public author brief drifted from the frozen manifest")

    checkpoint_policy = protocol["development_checkpoint_policy"]
    if sorted(map(int, checkpoint_policy["checkpoints"])) != [
        1_000_000,
        3_000_000,
        6_000_000,
        10_000_000,
    ]:
        raise ValueError("development checkpoint policy drifted from the adapter-spend curve")
    development_ids = {
        str(item["family_id"])
        for item in split_freeze["families"]
        if item["assigned_split"] == "development"
    }
    if set(checkpoint_policy["family_ids"]) != development_ids:
        raise ValueError("development checkpoint policy must use all and only development families")
    required_metrics = {
        "legal_action_accuracy",
        "next_state_accuracy",
        "belief_visibility_f1",
        "fact_allegation_accuracy",
        "counterfactual_branch_accuracy",
        "contradiction_detection_accuracy",
        "reachable_repair_accuracy",
        "obligation_dynamics_disagreement_accuracy",
        "forecast_brier_score",
        "frame_robust_policy_accuracy",
        "paired_skin_action_consistency",
        "identity_scrub_defense_consistency",
    }
    if set(checkpoint_policy["metrics"]) != required_metrics:
        raise ValueError("development metric suite drifted")

    gate = protocol["unseal_gate"]
    if gate["status"] != "closed" or not gate["one_time"]:
        raise ValueError("evaluation unseal gate must remain closed and one-time")
    if len(gate["required_frozen_receipts"]) < 4:
        raise ValueError("evaluation unseal gate lacks required frozen receipts")

    return {
        "schema_version": "storyworld_blinded_eval_protocol_validation_v1",
        "protocol_id": protocol["protocol_id"],
        "status": protocol["status"],
        "evaluation_families": len(protocol_families),
        "development_families": len(development_ids),
        "development_checkpoints": list(checkpoint_policy["checkpoints"]),
        "metrics": sorted(required_metrics),
        "unseal_gate": "closed",
        "sealed_content_opened": False,
        "passed": True,
    }


def validate_curriculum_package(repo_root: Path, package_path: Path) -> dict[str, Any]:
    """Validate the package, resolved skins, teacher roster, and token arithmetic."""
    package = read_json(package_path)
    if package.get("schema_version") != "storyworld_curriculum_package_v1":
        raise ValueError("unexpected curriculum package schema")
    expected_schema_paths = {
        "world": DEFAULT_WORLD_SCHEMA.relative_to(repo_root).as_posix(),
        "skin_overlay": DEFAULT_OVERLAY_SCHEMA.relative_to(repo_root).as_posix(),
        "trace": (repo_root / "schemas" / "storyworld_episode_trace_v1.schema.json")
        .relative_to(repo_root)
        .as_posix(),
        "split_freeze": DEFAULT_SPLIT_FREEZE_SCHEMA.relative_to(repo_root).as_posix(),
        "instance_sweep": DEFAULT_INSTANCE_SWEEP_SCHEMA.relative_to(repo_root).as_posix(),
        "blinded_eval_protocol": DEFAULT_BLINDED_EVAL_PROTOCOL_SCHEMA.relative_to(
            repo_root
        ).as_posix(),
    }
    for key, expected in expected_schema_paths.items():
        if package["schemas"].get(key) != expected:
            raise ValueError(f"package {key} schema path drifted from {expected}")

    world_receipts: list[dict[str, Any]] = []
    worlds: dict[str, dict[str, Any]] = {}
    source_paths: dict[str, Path] = {}
    for item in package["worlds"]:
        path = repo_root / str(item["path"])
        raw = read_json(path)
        if raw.get("schema_version") == "storyworld_skin_overlay_v1":
            overlay_errors = _schema_errors(raw, DEFAULT_OVERLAY_SCHEMA)
            if overlay_errors:
                raise ValueError("skin overlay schema failure: " + "; ".join(overlay_errors))
        world = read_world(path)
        receipt = validate_world(world)
        world_id = str(world["world_id"])
        if world_id in worlds:
            raise ValueError(f"duplicate resolved world_id in package: {world_id}")
        if item["resolved_world_id"] != world_id:
            raise ValueError(f"package resolved_world_id mismatch for {path}")
        if item["source_split"] != world["source_split"]:
            raise ValueError(f"package split mismatch for {world_id}")
        if bool(item["training_eligible"]) is not bool(world["training_eligible"]):
            raise ValueError(f"package training eligibility mismatch for {world_id}")
        resolved_skin_id = (
            world["matched_pair"]["skin_id"] if world["matched_pair"] is not None else None
        )
        if item["skin_id"] != resolved_skin_id:
            raise ValueError(f"package skin mismatch for {world_id}")
        if item["review_status"] != world["review"]["status"]:
            raise ValueError(f"package review status mismatch for {world_id}")
        worlds[world_id] = world
        source_paths[world_id] = path
        world_receipts.append(
            {
                **receipt,
                "source_path": path.relative_to(repo_root).as_posix(),
                "source_sha256": sha256_file(path),
                "resolved_content_sha256": sha256_json(world),
            }
        )

    reviewed_world_ids = {
        world_id
        for world_id, world in worlds.items()
        if world["review"]["status"] in {"approved", "rejected"}
    }
    review_bundle_value = package.get("review_bundle")
    review_bundle_receipt: dict[str, Any] | None = None
    if reviewed_world_ids and not review_bundle_value:
        raise ValueError("reviewed package worlds require a recorded review bundle")
    if review_bundle_value:
        review_bundle_path = repo_root / str(review_bundle_value)
        review_bundle = read_json(review_bundle_path)
        if review_bundle.get("schema_version") != "storyworld_review_application_bundle_v1":
            raise ValueError("unexpected storyworld review bundle schema")
        if review_bundle.get("package_id") != package["package_id"]:
            raise ValueError("review bundle belongs to a different package")
        if review_bundle.get("package_post_sha256") != sha256_file(package_path):
            raise ValueError("review bundle package hash does not match current package")
        updates = {
            str(item["world_id"]): item for item in review_bundle.get("updates", [])
        }
        if len(updates) != len(review_bundle.get("updates", [])):
            raise ValueError("review bundle contains duplicate world updates")
        if set(updates) != set(worlds):
            raise ValueError("review bundle must account for every nonsealed package world")
        for world_id, world in worlds.items():
            update = updates[world_id]
            source_path = source_paths[world_id]
            if update["decision"] != world["review"]["status"]:
                raise ValueError(f"review bundle decision mismatch for {world_id}")
            if update["post_source_sha256"] != sha256_file(source_path):
                raise ValueError(f"review bundle source hash mismatch for {world_id}")
            if update["post_resolved_content_sha256"] != sha256_json(world):
                raise ValueError(f"review bundle content hash mismatch for {world_id}")
            if update["reviewable_content_sha256"] != reviewable_world_sha256(world):
                raise ValueError(f"review bundle substantive hash mismatch for {world_id}")
            if update["transition_graph_sha256"] != transition_graph_sha256(world):
                raise ValueError(f"review bundle graph hash mismatch for {world_id}")
            requirement_updates = {
                str(item["review_type"]): item
                for item in update.get("requirements", [])
            }
            if set(requirement_updates) != {
                str(item["review_type"]) for item in world["review"]["requirements"]
            }:
                raise ValueError(f"review bundle requirement mismatch for {world_id}")
            for requirement in world["review"]["requirements"]:
                evidence = requirement_updates[str(requirement["review_type"])]
                receipt = evidence["receipt"]
                if evidence["receipt_sha256"] != sha256_json(receipt):
                    raise ValueError(f"review receipt hash mismatch for {world_id}")
                expected_reference = (
                    f"storyworld-review:{evidence['review_task_id']}:sha256:"
                    f"{evidence['receipt_sha256']}"
                )
                if requirement.get("receipt") != expected_reference:
                    raise ValueError(f"review receipt reference mismatch for {world_id}")
                if receipt.get("content_sha256") != reviewable_world_sha256(world):
                    raise ValueError(f"review receipt content mismatch for {world_id}")
                if receipt.get("decision") != requirement["status"]:
                    raise ValueError(f"review receipt decision mismatch for {world_id}")
        review_bundle_receipt = {
            "path": review_bundle_path.relative_to(repo_root).as_posix(),
            "sha256": sha256_file(review_bundle_path),
            "application_id": review_bundle["application_id"],
            "receipt_count": review_bundle["receipt_count"],
            "approved_worlds": review_bundle["approved_worlds"],
            "rejected_worlds": review_bundle["rejected_worlds"],
            "all_train_worlds_approved": review_bundle["all_train_worlds_approved"],
        }
    declared_scope = package.get("current_scope", {})
    if int(declared_scope.get("resolved_worlds", -1)) != len(worlds):
        raise ValueError("package current_scope.resolved_worlds does not match resolved package worlds")
    graph_count = len({item["transition_graph_sha256"] for item in world_receipts})
    if int(declared_scope.get("unique_transition_graphs", -1)) != graph_count:
        raise ValueError(
            "package current_scope.unique_transition_graphs does not match resolved causal graphs"
        )

    pair_receipts: list[dict[str, Any]] = []
    seen_pairs: set[str] = set()
    for world in worlds.values():
        if world["matched_pair"] is None:
            continue
        pair_id = str(world["matched_pair"]["pair_id"])
        if pair_id in seen_pairs:
            continue
        counterpart_id = str(world["matched_pair"]["counterpart_world_id"])
        if counterpart_id not in worlds:
            raise ValueError(f"package is missing matched counterpart {counterpart_id}")
        pair_receipts.append(validate_matched_pair(world, worlds[counterpart_id]))
        seen_pairs.add(pair_id)

    required_motifs = {
        "amanah",
        "mizan",
        "shahada",
        "tawbah",
        "shura",
        "ghayb_boundary",
    }
    motif_world_entries = [
        world for world in worlds.values() if world["theological_motif"] is not None
    ]
    motif_worlds = {
        str(world["theological_motif"]): world
        for world in motif_world_entries
    }
    if len(motif_world_entries) != len(required_motifs) or set(motif_worlds) != required_motifs:
        raise ValueError("Quranic-motif lane does not cover the six frozen motifs exactly")
    for motif, world in motif_worlds.items():
        pair = world["matched_pair"]
        counterpart = worlds[str(pair["counterpart_world_id"])]
        if pair["skin_id"] != "quranic_motif" or counterpart["matched_pair"][
            "skin_id"
        ] != "secular_control":
            raise ValueError(f"{motif}: motif world lacks an exact secular-control skin")
        if counterpart["theological_motif"] is not None:
            raise ValueError(f"{motif}: secular-control skin retains a theological motif")

    teacher_path = repo_root / str(package["teacher_ensemble"])
    teacher = read_json(teacher_path)
    if teacher.get("schema_version") != "storyworld_teacher_ensemble_v1":
        raise ValueError("unexpected teacher ensemble schema")
    expected_roles = {
        "actor",
        "forecaster",
        "interrogator",
        "counterfactual_analyst",
        "adjudicator_repairer",
    }
    if set(teacher.get("roles", {})) != expected_roles:
        raise ValueError("teacher ensemble roles are incomplete")
    if teacher.get("response_policy") != (
        "explicit_structured_work_products_no_private_chain_of_thought"
    ):
        raise ValueError("teacher ensemble response policy drifted")
    expected_role_efforts = {
        "actor": ["low", "medium"],
        "forecaster": ["medium"],
        "interrogator": ["high"],
        "counterfactual_analyst": ["high"],
        "adjudicator_repairer": ["xhigh"],
    }
    for role, expected_efforts in expected_role_efforts.items():
        config = teacher["roles"][role]
        if config.get("model_id") != "gpt-5.6-sol":
            raise ValueError(f"teacher role {role} drifted from the frozen 5.6 model")
        if config.get("reasoning_efforts") != expected_efforts:
            raise ValueError(f"teacher role {role} reasoning effort drifted")
    observed_efforts = {
        effort
        for config in teacher["roles"].values()
        for effort in config["reasoning_efforts"]
    }
    if observed_efforts != {"low", "medium", "high", "xhigh"}:
        raise ValueError("teacher ensemble must exercise low, medium, high, and xhigh effort")

    recipe_path = repo_root / str(package["token_recipe"])
    recipe = read_json(recipe_path)
    if recipe.get("schema_version") != "storyworld_token_recipe_v1":
        raise ValueError("unexpected token recipe schema")
    if sum(int(value) for value in recipe["slice_tokens"].values()) != int(
        recipe["target_tokens_per_arm"]
    ):
        raise ValueError("token recipe slices do not sum to the per-arm target")
    assistant_slice_minimums = {
        str(key): int(value)
        for key, value in recipe.get("minimum_assistant_tokens_by_slice", {}).items()
    }
    if set(assistant_slice_minimums) != set(recipe["slice_tokens"]):
        raise ValueError("token recipe must set an assistant minimum for every slice")
    if sum(assistant_slice_minimums.values()) != int(
        recipe["minimum_assistant_tokens_per_arm"]
    ):
        raise ValueError("assistant slice minimums must sum to the per-arm minimum")
    if any(
        assistant_slice_minimums[slice_id] > int(target)
        for slice_id, target in recipe["slice_tokens"].items()
    ):
        raise ValueError("assistant slice minimum exceeds its packed token target")
    if int(recipe["minimum_assistant_tokens_per_arm"]) < 4_000_000:
        raise ValueError("token recipe must retain at least 4M loss-bearing assistant tokens per arm")
    if sorted(map(int, recipe["checkpoints"])) != [1_000_000, 3_000_000, 6_000_000, 10_000_000]:
        raise ValueError("adapter-spend checkpoints drifted")
    if set(recipe["arms"]) != {"neutral", "constitutional", "jinn", "beast"}:
        raise ValueError("token recipe must retain all four matched adapter arms")

    training_recipe_path = repo_root / str(package["adapter_training_recipe"])
    training_recipe = read_json(training_recipe_path)
    from .adapter_training import validate_adapter_training_recipe

    training_recipe_receipt = validate_adapter_training_recipe(training_recipe, recipe)

    analysis_plan_path = repo_root / str(package["analysis_plan"])
    analysis_plan = read_json(analysis_plan_path)
    if analysis_plan.get("schema_version") != "storyworld_analysis_plan_v1":
        raise ValueError("unexpected storyworld analysis plan schema")
    if analysis_plan.get("status") != "frozen_before_adapter_results":
        raise ValueError("storyworld analysis plan must remain frozen before results")
    if analysis_plan.get("arms") != recipe["arms"] or analysis_plan.get(
        "checkpoint_tokens"
    ) != recipe["checkpoints"]:
        raise ValueError("analysis plan arms/checkpoints drifted from the token recipe")
    if analysis_plan.get("selection_rule", {}).get("scope") != (
        "one global checkpoint shared by all four arms"
    ):
        raise ValueError("analysis plan must select one matched global checkpoint")

    campaign_path = repo_root / str(package["harvest_campaign"])
    campaign = read_json(campaign_path)
    if campaign.get("schema_version") != "storyworld_harvest_campaign_plan_v1":
        raise ValueError("unexpected harvest campaign schema")
    if campaign["status"] != "planning_estimate_not_spend_authorization":
        raise ValueError("harvest campaign cannot authorize spend before the approved pilot")
    if campaign["package_path"] != package_path.relative_to(repo_root).as_posix():
        raise ValueError("harvest campaign package path drifted")
    if campaign["recipe_path"] != recipe_path.relative_to(repo_root).as_posix():
        raise ValueError("harvest campaign recipe path drifted")
    if campaign["teacher_ensemble_path"] != teacher_path.relative_to(repo_root).as_posix():
        raise ValueError("harvest campaign teacher ensemble path drifted")
    if set(campaign["arms"]) != set(recipe["arms"]):
        raise ValueError("harvest campaign arms drifted from the token recipe")
    if int(campaign["train_family_count"]) * int(
        campaign["traces_per_family_per_arm"]
    ) != int(campaign["traces_per_arm"]):
        raise ValueError("harvest campaign per-family allocation does not sum per arm")
    schedule_mix = {
        str(key): float(value) for key, value in campaign["actor_schedule_mix"].items()
    }
    if set(schedule_mix) != {"single", "dyadic"} or abs(sum(schedule_mix.values()) - 1.0) > 1e-9:
        raise ValueError("harvest campaign schedule mix is invalid")
    planned_jobs = len(campaign["arms"]) * int(campaign["traces_per_arm"])

    inventory_path = repo_root / str(package["source_inventory"])
    inventory = read_json(inventory_path)
    if inventory.get("schema_version") != "storyworld_source_inventory_v1":
        raise ValueError("unexpected source inventory schema")
    if len(inventory.get("sources", [])) != 17 or inventory.get("counts", {}).get(
        "named_sources"
    ) != 17:
        raise ValueError("source inventory must account for all 17 named pre-migration sources")
    if any(
        item["current_split"] in {"evaluation", "holdout"}
        and item["current_training_eligible"]
        for item in inventory["sources"]
    ):
        raise ValueError("source inventory marks a sealed source as training eligible")
    for item in inventory["sources"]:
        if item["current_split"] == "paired_development_and_evaluation" and (
            item.get("development_variant_training_eligible") is not True
            or item.get("evaluation_variant_training_eligible") is not False
        ):
            raise ValueError("paired Mizan sources must record variant-level eligibility")

    recovered_source_path = repo_root / str(package["recovered_static_source"])
    recovered_source = read_json(recovered_source_path)
    if recovered_source.get("schema_version") != "storyworld_recovered_static_source_v1":
        raise ValueError("unexpected recovered static source schema")
    if recovered_source["status"] != "provisional_pending_review_and_license_audit":
        raise ValueError("recovered static source must remain provisional before review")
    if set(recovered_source["condition_to_arm"].values()) != set(recipe["arms"]):
        raise ValueError("recovered static source does not cover all recipe arms")
    expected_static_audit = recovered_source["expected_cl100k_train_audit"]
    if set(expected_static_audit) != set(recipe["arms"]):
        raise ValueError("recovered static token audit does not cover every arm")
    expected_static_rows = 0
    for arm, slices in expected_static_audit.items():
        if set(slices) != {"static_identity_calibration", "ordinary_helpfulness_guardrails"}:
            raise ValueError(f"{arm}: recovered source slice mapping drifted")
        arm_rows = sum(int(item["rows"]) for item in slices.values())
        if arm_rows != 600:
            raise ValueError(f"{arm}: recovered source must retain exactly 600 train rows")
        expected_static_rows += arm_rows
    if any(
        recovered_source["release_gates"].get(key) is not expected
        for key, expected in {
            "unreviewed_rows_training_approved": False,
            "needs_scholar_review_rows_training_approved": False,
            "license_audit_required": True,
            "exact_hash_match_required": True,
            "unique_train_rows_only": True,
        }.items()
    ):
        raise ValueError("recovered static release gates drifted")

    support_campaign_path = repo_root / str(package["support_slice_campaign"])
    support_campaign = read_json(support_campaign_path)
    if support_campaign.get("schema_version") != "storyworld_support_slice_campaign_v1":
        raise ValueError("unexpected support-slice campaign schema")
    if support_campaign.get("status") != "prompt_design_pending_review_not_spend_authorization":
        raise ValueError("support-slice campaign must remain a no-spend planning artifact")
    if set(support_campaign.get("arms", [])) != set(recipe["arms"]):
        raise ValueError("support-slice campaign arms drifted from the token recipe")
    if support_campaign.get("scenario_counts") != {
        "static_identity_calibration": 900,
        "ordinary_helpfulness_guardrails": 1200,
    }:
        raise ValueError("support-slice scenario allocation drifted")
    expected_support_slices = {
        "static_identity_calibration",
        "ordinary_helpfulness_guardrails",
    }
    if support_campaign.get("packed_token_targets_per_arm") != {
        slice_id: int(recipe["slice_tokens"][slice_id])
        for slice_id in expected_support_slices
    }:
        raise ValueError("support-slice packed-token targets drifted from the recipe")
    if support_campaign.get("minimum_assistant_token_targets_per_arm") != {
        slice_id: int(recipe["minimum_assistant_tokens_by_slice"][slice_id])
        for slice_id in expected_support_slices
    }:
        raise ValueError("support-slice assistant-token targets drifted from the recipe")
    if not 0 < float(support_campaign.get("projection_safety_factor", 0)) <= 1:
        raise ValueError("support-slice projection safety factor must be in (0, 1]")
    support_gates = support_campaign.get("release_gates", {})
    if support_gates.get("automatic_training_approval") is not False:
        raise ValueError("support-slice data cannot receive automatic training approval")
    if support_gates.get("sealed_evaluation_content_allowed") is not False:
        raise ValueError("support-slice campaign cannot use sealed evaluation content")
    if support_gates.get("development_content_allowed") is not False:
        raise ValueError("support-slice campaign cannot use development content")

    split_freeze_path = repo_root / str(package["split_freeze"])
    split_freeze = read_json(split_freeze_path)
    split_receipt = validate_split_freeze(
        inventory,
        split_freeze,
        repo_root=repo_root,
        schema_path=DEFAULT_SPLIT_FREEZE_SCHEMA,
    )
    blinded_eval_path = repo_root / str(package["blinded_eval_protocol"])
    blinded_eval_protocol = read_json(blinded_eval_path)
    blinded_eval_receipt = validate_blinded_eval_protocol(
        split_freeze,
        blinded_eval_protocol,
        schema_path=DEFAULT_BLINDED_EVAL_PROTOCOL_SCHEMA,
    )
    if set(analysis_plan.get("locked_metrics", [])) != set(
        blinded_eval_protocol["development_checkpoint_policy"]["metrics"]
    ) or len(analysis_plan.get("locked_metrics", [])) != len(
        blinded_eval_protocol["development_checkpoint_policy"]["metrics"]
    ):
        raise ValueError("analysis-plan metrics drifted from the closed evaluation protocol")

    sweep_receipts = []
    for sweep_value in package.get("instance_sweeps", []):
        _, sweep_receipt = materialize_instance_sweep(
            repo_root,
            repo_root / str(sweep_value),
            schema_path=DEFAULT_INSTANCE_SWEEP_SCHEMA,
        )
        sweep_receipts.append(sweep_receipt)
    swept_base_world_ids = {
        world_id
        for receipt in sweep_receipts
        for world_id in receipt["base_world_ids"]
    }
    if swept_base_world_ids != set(worlds):
        raise ValueError("instance sweeps must cover every nonsealed package world exactly")

    return {
        "schema_version": "storyworld_curriculum_package_validation_v1",
        "package_id": package["package_id"],
        "package_path": package_path.relative_to(repo_root).as_posix(),
        "package_sha256": sha256_file(package_path),
        "world_schema_sha256": sha256_file(DEFAULT_WORLD_SCHEMA),
        "overlay_schema_sha256": sha256_file(DEFAULT_OVERLAY_SCHEMA),
        "trace_schema_sha256": sha256_file(
            repo_root / "schemas" / "storyworld_episode_trace_v1.schema.json"
        ),
        "instance_sweep_schema_sha256": sha256_file(DEFAULT_INSTANCE_SWEEP_SCHEMA),
        "blinded_eval_protocol_schema_sha256": sha256_file(
            DEFAULT_BLINDED_EVAL_PROTOCOL_SCHEMA
        ),
        "worlds": world_receipts,
        "matched_pairs": pair_receipts,
        "quranic_motif_lane": {
            "motifs": sorted(required_motifs),
            "matched_secular_controls": len(required_motifs),
            "sacred_figure_reenactment_allowed": False,
        },
        "instance_sweeps": sweep_receipts,
        "teacher_ensemble": {
            "path": teacher_path.relative_to(repo_root).as_posix(),
            "sha256": sha256_file(teacher_path),
            "roles": sorted(expected_roles),
            "reasoning_efforts": sorted(observed_efforts),
            "model_ids": sorted(
                {config["model_id"] for config in teacher["roles"].values()}
            ),
            "response_policy": teacher["response_policy"],
        },
        "token_recipe": {
            "path": recipe_path.relative_to(repo_root).as_posix(),
            "sha256": sha256_file(recipe_path),
            "target_tokens_per_arm": recipe["target_tokens_per_arm"],
            "minimum_assistant_tokens_per_arm": recipe["minimum_assistant_tokens_per_arm"],
            "total_four_arm_tokens": 4 * int(recipe["target_tokens_per_arm"]),
        },
        "adapter_training_recipe": {
            **training_recipe_receipt,
            "path": training_recipe_path.relative_to(repo_root).as_posix(),
            "sha256": sha256_file(training_recipe_path),
            "planned_adapter_checkpoints": len(training_recipe["arms"])
            * len(training_recipe["checkpoint_tokens"]),
            "training_authorized": False,
        },
        "analysis_plan": {
            "path": analysis_plan_path.relative_to(repo_root).as_posix(),
            "sha256": sha256_file(analysis_plan_path),
            "status": analysis_plan["status"],
            "locked_metrics": len(analysis_plan["locked_metrics"]),
            "primary_contrasts": analysis_plan["primary_contrasts"],
            "global_checkpoint_selection": True,
            "sealed_evaluation_opened": False,
        },
        "harvest_campaign": {
            "path": campaign_path.relative_to(repo_root).as_posix(),
            "sha256": sha256_file(campaign_path),
            "status": campaign["status"],
            "traces_per_arm": campaign["traces_per_arm"],
            "planned_jobs": planned_jobs,
            "pilot_jobs": len(campaign["arms"])
            * int(campaign["train_family_count"])
            * int(campaign["pilot_traces_per_family_per_arm"]),
        },
        "source_inventory": {
            "path": inventory_path.relative_to(repo_root).as_posix(),
            "sha256": sha256_file(inventory_path),
            "named_sources": len(inventory["sources"]),
        },
        "recovered_static_source": {
            "path": recovered_source_path.relative_to(repo_root).as_posix(),
            "sha256": sha256_file(recovered_source_path),
            "status": recovered_source["status"],
            "expected_train_rows": expected_static_rows,
            "arms": sorted(expected_static_audit),
            "training_approved_rows": 0,
        },
        "support_slice_campaign": {
            "path": support_campaign_path.relative_to(repo_root).as_posix(),
            "sha256": sha256_file(support_campaign_path),
            "status": support_campaign["status"],
            "scenarios_per_arm": sum(
                int(value) for value in support_campaign["scenario_counts"].values()
            ),
            "planned_jobs": len(support_campaign["arms"])
            * sum(int(value) for value in support_campaign["scenario_counts"].values()),
            "packed_token_targets_per_arm": support_campaign[
                "packed_token_targets_per_arm"
            ],
            "minimum_assistant_token_targets_per_arm": support_campaign[
                "minimum_assistant_token_targets_per_arm"
            ],
            "training_approved_rows": 0,
        },
        "review_bundle": review_bundle_receipt,
        "split_freeze": {
            **split_receipt,
            "path": split_freeze_path.relative_to(repo_root).as_posix(),
            "sha256": sha256_file(split_freeze_path),
        },
        "blinded_eval_protocol": {
            **blinded_eval_receipt,
            "path": blinded_eval_path.relative_to(repo_root).as_posix(),
            "sha256": sha256_file(blinded_eval_path),
        },
        "passed": True,
    }


def _opaque_action_id(seed: int, world_id: str, state_id: str, action_key: str) -> str:
    digest = sha256_json(
        {"seed": seed, "world_id": world_id, "state_id": state_id, "action_key": action_key}
    )
    return f"A-{digest[:10].upper()}"


@dataclass
class StoryworldEngine:
    world: dict[str, Any]
    seed: int
    actor_agent_id: str | None = None

    def __post_init__(self) -> None:
        validate_world(self.world)
        self.actor_agent_id = self.actor_agent_id or str(self.world["actor_agent_id"])
        if self.actor_agent_id not in {str(item["agent_id"]) for item in self.world["agents"]}:
            raise ValueError("actor agent is not declared in the world")
        self._states = {str(item["state_id"]): item for item in self.world["states"]}
        self._facts = {str(item["fact_id"]): item for item in self.world["facts"]}
        self.state_id = str(self.world["entry_state"])
        self.variables = {key: int(value) for key, value in self.world["initial_variables"].items()}
        self.turn_index = 0
        self.history: list[dict[str, Any]] = []

    @property
    def state(self) -> dict[str, Any]:
        return self._states[self.state_id]

    @property
    def terminal(self) -> bool:
        return bool(self.state["terminal"])

    def full_state(self) -> dict[str, Any]:
        return {
            "state_id": self.state_id,
            "variables": deepcopy(self.variables),
            "active_fact_ids": list(self.state["active_fact_ids"]),
            "turn_index": self.turn_index,
            "terminal": self.terminal,
        }

    def visible_facts(self, agent_id: str | None = None) -> list[dict[str, Any]]:
        agent_id = agent_id or str(self.actor_agent_id)
        visible: list[dict[str, Any]] = []
        for fact_id in self.state["active_fact_ids"]:
            fact = self._facts[str(fact_id)]
            seats = set(map(str, fact["visible_to"]))
            if "public" not in seats and agent_id not in seats:
                continue
            visible.append(
                {
                    "fact_id": fact["fact_id"],
                    "text": fact["text"],
                    "epistemic_kind": fact["epistemic_kind"],
                }
            )
        return visible

    def actor_view(self) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
        if self.terminal:
            raise ValueError("terminal states do not have an actor view")
        actions = list(self.state["actions"])
        order_seed = int(
            sha256_json(
                {
                    "seed": self.seed,
                    "world_id": self.world["world_id"],
                    "state_id": self.state_id,
                    "turn_index": self.turn_index,
                }
            )[:16],
            16,
        )
        random.Random(order_seed).shuffle(actions)
        mapping: dict[str, dict[str, Any]] = {}
        displayed: list[dict[str, str]] = []
        for action in actions:
            opaque_id = _opaque_action_id(
                self.seed,
                str(self.world["world_id"]),
                self.state_id,
                str(action["action_key"]),
            )
            mapping[opaque_id] = action
            displayed.append({"action_id": opaque_id, "text": str(action["text"])})
        view = {
            "world_title": self.world["title"],
            "turn_index": self.turn_index,
            "public_observation": self.state["public_observation"],
            "private_observation": self.state["private_observations"].get(
                str(self.actor_agent_id), ""
            ),
            "visible_state": deepcopy(self.variables),
            "observed_facts": self.visible_facts(),
            "legal_actions": displayed,
        }
        return view, mapping

    def preview(self, action: dict[str, Any]) -> dict[str, Any]:
        variables = deepcopy(self.variables)
        for key, delta in action["variable_effects"].items():
            variables[str(key)] += int(delta)
        return {
            "next_state": action["next_state"],
            "variables": variables,
            "public_outcome": action["public_outcome"],
            "private_outcome": action["private_outcomes"].get(str(self.actor_agent_id), ""),
        }

    def step(
        self,
        opaque_action_id: str,
        mapping: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        if self.terminal:
            raise ValueError("cannot advance a terminal state")
        if opaque_action_id not in mapping:
            raise ValueError("selected action is not in the legal opaque action map")
        state_before = self.full_state()
        action = mapping[opaque_action_id]
        preview = self.preview(action)
        self.variables = preview["variables"]
        self.state_id = str(preview["next_state"])
        self.turn_index += 1
        result = {
            "opaque_action_id": opaque_action_id,
            "action_key": action["action_key"],
            "action_text": action["text"],
            "public_outcome": preview["public_outcome"],
            "private_outcome": preview["private_outcome"],
            "consequences": deepcopy(action["consequences"]),
            "state_before": state_before,
            "state_after": self.full_state(),
        }
        self.history.append(deepcopy(result))
        return result


def _metta_quote(text: str) -> str:
    return json.dumps(text, ensure_ascii=False)


def compile_world_to_metta(world: dict[str, Any]) -> dict[str, Any]:
    """Compile a world into auditable MeTTa-style facts.

    This is deterministic file-backed derivation, not native Hyperon proof
    execution.  The receipt states that boundary explicitly.
    """
    validation = validate_world(world)
    world_id = str(world["world_id"])
    agents = [str(item["agent_id"]) for item in world["agents"]]
    facts = {str(item["fact_id"]): item for item in world["facts"]}
    lines = [
        "; Generated by alignment_harness.storyworlds.compile_world_to_metta",
        "; MeTTa-file-backed deterministic derivation; not native Hyperon execution.",
        f"(world {world_id})",
        f"(entry-state {world_id} {world['entry_state']})",
    ]
    for agent in agents:
        lines.append(f"(agent {world_id} {agent})")
    for key, value in sorted(world["initial_variables"].items()):
        lines.append(f"(initial-variable {world_id} {key} {int(value)})")
    for fact_id, fact in sorted(facts.items()):
        lines.append(f"(fact {world_id} {fact_id})")
        lines.append(f"(fact-kind {fact_id} {fact['epistemic_kind']})")
        lines.append(f"(fact-truth {fact_id} {fact['ground_truth']})")
        lines.append(f"(fact-text {fact_id} {_metta_quote(str(fact['text']))})")
    for state in sorted(world["states"], key=lambda item: (int(item["turn_index"]), item["state_id"])):
        state_id = str(state["state_id"])
        lines.append(f"(state {world_id} {state_id})")
        lines.append(f"(turn-index {state_id} {int(state['turn_index'])})")
        if state["terminal"]:
            lines.append(f"(terminal-state {state_id})")
        for fact_id in sorted(map(str, state["active_fact_ids"])):
            lines.append(f"(active-fact {state_id} {fact_id})")
            visibility = set(map(str, facts[fact_id]["visible_to"]))
            for agent in agents:
                if "public" in visibility or agent in visibility:
                    lines.append(f"(observed-by {state_id} {agent} {fact_id})")
                else:
                    lines.append(f"(hidden-from {state_id} {agent} {fact_id})")
        for action in sorted(state["actions"], key=lambda item: str(item["action_key"])):
            action_key = str(action["action_key"])
            lines.append(f"(legal-action {state_id} {action_key})")
            lines.append(f"(transition {state_id} {action_key} {action['next_state']})")
            for consequence in action["consequences"]:
                consequence_id = str(consequence["consequence_id"])
                lines.append(f"(causes {action_key} {consequence_id})")
                for dimension, value in sorted(consequence["dimension_effects"].items()):
                    lines.append(
                        f"(consequence-effect {consequence_id} {dimension} {int(value)})"
                    )
            for repaired in sorted(map(str, action["repairs_consequences"])):
                lines.append(f"(repairable {repaired} {action_key})")
    for obligation in sorted(
        world["obligations"], key=lambda item: (item["frame"], item["constraint_id"])
    ):
        states = (
            [item["state_id"] for item in world["states"] if not item["terminal"]]
            if obligation["applies_in_states"] == ["*"]
            else obligation["applies_in_states"]
        )
        for state_id in sorted(map(str, states)):
            lines.append(
                f"(obligation {obligation['frame']} {state_id} {obligation['constraint_id']})"
            )
    text = "\n".join(lines) + "\n"
    return {
        "schema_version": "storyworld_metta_compilation_v1",
        "backend": "python_metta_storyworld_bridge",
        "claim_boundary": "MeTTa-file-backed deterministic derivation; not native Hyperon proof execution.",
        "world_id": world_id,
        "world_content_sha256": sha256_json(world),
        "transition_graph_sha256": validation["transition_graph_sha256"],
        "metta_sha256": sha256_bytes(text.encode("utf-8")),
        "fact_count": sum(1 for line in lines if line.startswith("(")),
        "metta_text": text,
    }


def write_metta_compilation(world: dict[str, Any], output_path: Path) -> dict[str, Any]:
    receipt = compile_world_to_metta(world)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    temporary.write_text(receipt["metta_text"], encoding="utf-8", newline="\n")
    temporary.replace(output_path)
    manifest = {key: value for key, value in receipt.items() if key != "metta_text"}
    write_json(output_path.with_suffix(output_path.suffix + ".receipt.json"), manifest)
    return manifest


def compile_episode_trace_to_metta(
    world: dict[str, Any], trace: dict[str, Any]
) -> dict[str, Any]:
    """Compile the realized episode into turn-indexed state/visibility facts."""
    validation = validate_world(world)
    if trace.get("schema_version") != "storyworld_episode_trace_v1":
        raise ValueError("unexpected episode trace schema")
    if trace["episode"]["world_id"] != world["world_id"]:
        raise ValueError("trace/world ID mismatch")
    if trace["provenance"]["world_content_sha256"] != sha256_json(world):
        raise ValueError("trace/world content hash mismatch")
    agents = [str(item["agent_id"]) for item in world["agents"]]
    facts = {str(item["fact_id"]): item for item in world["facts"]}
    trace_id = str(trace["trace_id"])
    lines = [
        "; Realized episode facts generated by compile_episode_trace_to_metta",
        "; MeTTa-file-backed deterministic derivation; not native Hyperon execution.",
        f"(episode {trace_id} {world['world_id']})",
    ]
    for turn in trace["turns"]:
        turn_id = f"t{int(turn['turn_index'])}"
        state = turn["state_before"]
        lines.append(f"(world-state {trace_id} {turn_id} {state['state_id']})")
        for variable, value in sorted(state["variables"].items()):
            # This is the explicit (state episode turn variable value) form.
            lines.append(f"(state {trace_id} {turn_id} {variable} {int(value)})")
        for fact_id in sorted(map(str, state["active_fact_ids"])):
            visibility = set(map(str, facts[fact_id]["visible_to"]))
            for agent in agents:
                predicate = "observed-by" if "public" in visibility or agent in visibility else "hidden-from"
                lines.append(f"({predicate} {trace_id} {turn_id} {agent} {fact_id})")
        for opaque_id, action_key in sorted(
            turn["proof_receipts"]["opaque_action_mapping"].items()
        ):
            lines.append(f"(legal-action {trace_id} {turn_id} {action_key})")
            lines.append(f"(opaque-action {trace_id} {turn_id} {opaque_id} {action_key})")
        transition = turn["proof_receipts"]["transition_rule"]
        next_turn_id = f"t{int(turn['turn_index']) + 1}"
        lines.append(
            f"(transition {trace_id} {turn_id} {transition['action_key']} {next_turn_id})"
        )
        lines.append(
            f"(transition-world-state {trace_id} {turn_id} {transition['action_key']} {transition['next_state']})"
        )
    final_turn_id = f"t{int(trace['final_state']['turn_index'])}"
    lines.append(
        f"(world-state {trace_id} {final_turn_id} {trace['final_state']['state_id']})"
    )
    for variable, value in sorted(trace["final_state"]["variables"].items()):
        lines.append(f"(state {trace_id} {final_turn_id} {variable} {int(value)})")
    lines.append(f"(terminal-state {trace_id} {final_turn_id})")
    text = "\n".join(lines) + "\n"
    return {
        "schema_version": "storyworld_episode_metta_compilation_v1",
        "backend": "python_metta_storyworld_bridge",
        "claim_boundary": "MeTTa-file-backed deterministic derivation; not native Hyperon proof execution.",
        "trace_id": trace_id,
        "world_id": world["world_id"],
        "trace_content_sha256": sha256_json(trace),
        "world_content_sha256": sha256_json(world),
        "transition_graph_sha256": validation["transition_graph_sha256"],
        "metta_sha256": sha256_bytes(text.encode("utf-8")),
        "fact_count": sum(1 for line in lines if line.startswith("(")),
        "metta_text": text,
    }


WORLD_MODEL_TASK_TYPES = (
    "legal_action_recognition",
    "next_state_prediction",
    "belief_state_tracking",
    "fact_vs_allegation",
    "counterfactual_branch_evaluation",
    "contradiction_detection",
    "reachable_repair",
    "obligation_vs_dynamics",
)


def _task_row(
    world: dict[str, Any],
    task_type: str,
    ordinal: int,
    prompt: str,
    target: dict[str, Any],
    proof: dict[str, Any],
) -> dict[str, Any]:
    task_id = f"{world['world_id']}__{task_type}__{ordinal:04d}"
    return {
        "schema_version": "storyworld_world_model_task_v1",
        "task_id": task_id,
        "task_type": task_type,
        "world_id": world["world_id"],
        "source_split": world["source_split"],
        "training_eligible": world["training_eligible"],
        "messages": [
            {
                "role": "system",
                "content": (
                    "Reconstruct only the requested public world-model facts. Return the requested "
                    "JSON shape without hidden chain-of-thought or metaphysical claims."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "target": target,
        "proof": proof,
    }


def build_world_model_tasks(world: dict[str, Any], seed: int = 20260716) -> list[dict[str, Any]]:
    """Derive auxiliary supervision while keeping proof metadata out of prompts."""
    validation = validate_world(world)
    states = {str(item["state_id"]): item for item in world["states"]}
    facts = {str(item["fact_id"]): item for item in world["facts"]}
    agents = [str(item["agent_id"]) for item in world["agents"]]
    tasks: list[dict[str, Any]] = []
    counters = {task_type: 0 for task_type in WORLD_MODEL_TASK_TYPES}

    def add(task_type: str, prompt: str, target: dict[str, Any], proof: dict[str, Any]) -> None:
        counters[task_type] += 1
        tasks.append(_task_row(world, task_type, counters[task_type], prompt, target, proof))

    action_universe = [
        action for state in world["states"] for action in state["actions"]
    ]
    for state in sorted(world["states"], key=lambda item: (item["turn_index"], item["state_id"])):
        if state["terminal"]:
            continue
        state_id = str(state["state_id"])
        legal = list(state["actions"])
        candidates = legal[:]
        distractor = next(
            (action for action in action_universe if action not in legal),
            None,
        )
        if distractor is not None:
            candidates.append(distractor)
        mapping = {
            _opaque_action_id(seed, str(world["world_id"]), state_id, str(action["action_key"])): action
            for action in candidates
        }
        displayed = [
            {"action_id": opaque, "text": action["text"]}
            for opaque, action in sorted(mapping.items())
        ]
        legal_ids = sorted(
            opaque for opaque, action in mapping.items() if action in legal
        )
        add(
            "legal_action_recognition",
            f"Observation: {state['public_observation']}\nCandidates: {json.dumps(displayed, ensure_ascii=False)}\n"
            'Return {"legal_action_ids":[...]}.',
            {"legal_action_ids": legal_ids},
            {
                "state_id": state_id,
                "opaque_to_action_key": {
                    opaque: action["action_key"] for opaque, action in mapping.items()
                },
                "rule": "legal-action facts",
            },
        )

        for action in legal:
            target = {
                "public_outcome": action["public_outcome"],
                "variable_changes": action["variable_effects"],
            }
            add(
                "next_state_prediction",
                f"Observation: {state['public_observation']}\nAction: {action['text']}\n"
                'Predict only {"public_outcome":"...","variable_changes":{...}}.',
                target,
                {
                    "state_id": state_id,
                    "action_key": action["action_key"],
                    "next_state": action["next_state"],
                    "rule": "transition fact",
                },
            )

        for agent in agents:
            visible_statements = sorted(
                facts[fact_id]["text"]
                for fact_id in state["active_fact_ids"]
                if "public" in facts[fact_id]["visible_to"]
                or agent in facts[fact_id]["visible_to"]
            )
            public_statements = sorted(
                facts[fact_id]["text"]
                for fact_id in state["active_fact_ids"]
                if "public" in facts[fact_id]["visible_to"]
            )
            add(
                "belief_state_tracking",
                f"Public record: {json.dumps(public_statements, ensure_ascii=False)}\n"
                f"Private note shown to {agent}: {state['private_observations'].get(agent, '')}\n"
                f"List only statements available to {agent} as "
                '{"available_statements":[...]}.',
                {"available_statements": visible_statements},
                {
                    "state_id": state_id,
                    "agent_id": agent,
                    "visible_fact_ids": sorted(
                        fact_id
                        for fact_id in state["active_fact_ids"]
                        if "public" in facts[fact_id]["visible_to"]
                        or agent in facts[fact_id]["visible_to"]
                    ),
                    "rule": "observed-by/hidden-from facts",
                },
            )

        active = [facts[fact_id] for fact_id in state["active_fact_ids"]]
        if any(item["epistemic_kind"] == "allegation" for item in active):
            statements = [item["text"] for item in active]
            labels = [item["epistemic_kind"] for item in active]
            add(
                "fact_vs_allegation",
                f"Classify each statement as fact or allegation without deciding whether unknown claims are true: "
                f"{json.dumps(statements, ensure_ascii=False)}\n"
                'Return {"labels":[...]}.',
                {"labels": labels},
                {
                    "state_id": state_id,
                    "fact_ids": [item["fact_id"] for item in active],
                    "rule": "fact-kind facts",
                },
            )

        if len(legal) >= 2:
            first, second = legal[:2]
            add(
                "counterfactual_branch_evaluation",
                f"At this observation: {state['public_observation']}\nCompare action A: {first['text']}\n"
                f"with action B: {second['text']}\n"
                'Return {"a_outcome":"...","b_outcome":"...","different_later_menu":true|false}.',
                {
                    "a_outcome": first["public_outcome"],
                    "b_outcome": second["public_outcome"],
                    "different_later_menu": set(
                        action["action_key"] for action in states[first["next_state"]]["actions"]
                    )
                    != set(action["action_key"] for action in states[second["next_state"]]["actions"]),
                },
                {
                    "state_id": state_id,
                    "action_keys": [first["action_key"], second["action_key"]],
                    "next_states": [first["next_state"], second["next_state"]],
                    "rule": "counterfactual transition comparison",
                },
            )

        known = next((item for item in active if item["ground_truth"] == "true"), None)
        if known is not None:
            assertions = [known["text"], f"It is false that: {known['text']}"]
            add(
                "contradiction_detection",
                f"The established record contains: {known['text']}\nWhich numbered assertion contradicts it? "
                f"{json.dumps(assertions, ensure_ascii=False)}\n"
                'Return {"contradicting_index":0|1}.',
                {"contradicting_index": 1},
                {
                    "state_id": state_id,
                    "fact_id": known["fact_id"],
                    "ground_truth": "true",
                    "rule": "explicit negation of established fact",
                },
            )

        for action in legal:
            if not action["repairs_consequences"]:
                continue
            add(
                "reachable_repair",
                f"Observation: {state['public_observation']}\nWhich listed action repairs an earlier consequence? "
                f"{json.dumps(displayed, ensure_ascii=False)}\n"
                'Return {"repair_action_id":"...","repairs":[...]}.',
                {
                    "repair_action_id": next(
                        opaque for opaque, mapped in mapping.items() if mapped is action
                    ),
                    "repairs": action["repairs_consequences"],
                },
                {
                    "state_id": state_id,
                    "action_key": action["action_key"],
                    "rule": "repairable facts",
                },
            )

        for obligation in world["obligations"]:
            applies = obligation["applies_in_states"] == ["*"] or state_id in obligation["applies_in_states"]
            if not applies:
                continue
            action = legal[0]
            tags = set(map(str, action["tags"]))
            required = set(map(str, obligation["required_action_tags_any"]))
            forbidden = set(map(str, obligation["forbidden_action_tags"]))
            satisfies = (not required or bool(tags.intersection(required))) and not bool(
                tags.intersection(forbidden)
            )
            add(
                "obligation_vs_dynamics",
                f"Frame constraint: {obligation['statement']}\nAction: {action['text']}\n"
                f"Predicted outcome: {action['public_outcome']}\n"
                'Return {"constraint_satisfied":true|false,"outcome_still_uncertain":true}.',
                {"constraint_satisfied": satisfies, "outcome_still_uncertain": True},
                {
                    "state_id": state_id,
                    "frame": obligation["frame"],
                    "constraint_id": obligation["constraint_id"],
                    "action_key": action["action_key"],
                    "action_tags": sorted(tags),
                    "rule": "obligation tags compared with transition dynamics",
                    "interpretation": "synthetic constraint proxy, not moral or theological ground truth",
                },
            )

    missing_types = set(WORLD_MODEL_TASK_TYPES).difference(row["task_type"] for row in tasks)
    if missing_types:
        raise ValueError(
            f"{world['world_id']}: world cannot derive required task types {sorted(missing_types)}"
        )
    compilation = compile_world_to_metta(world)
    for row in tasks:
        row["proof_receipt"] = {
            "world_content_sha256": compilation["world_content_sha256"],
            "metta_sha256": compilation["metta_sha256"],
            "transition_graph_sha256": validation["transition_graph_sha256"],
        }
    return tasks
