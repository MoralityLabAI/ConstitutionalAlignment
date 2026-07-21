from alignment_harness.worldview_skills import derive_scale_profile, load_skill_graph, render_skill_scaffold


def test_skill_graph_separates_1p7b_and_4b_hypotheses() -> None:
    one = derive_scale_profile("qwen3_1p7b")
    four = derive_scale_profile("qwen_4b")

    assert one["capacity_hypothesis_not_result"] is True
    assert "bounded-storyworld-reasoning" in one["available_skill_hypotheses"]
    assert "novel-principle-composition" not in one["available_skill_hypotheses"]
    assert "novel-principle-composition" in four["available_skill_hypotheses"]
    assert one["levels"]["native"]["all_skills_in_capacity_set"] is False
    assert four["levels"]["native"]["all_skills_in_capacity_set"] is False


def test_guided_scaffold_is_bounded_by_scale() -> None:
    text = render_skill_scaffold(
        "qwen3_1p7b",
        "guided",
        include_skills=["value-prioritization", "bounded-storyworld-reasoning"],
    )
    assert "Rank competing values" in text
    assert "Choose legal actions" in text


def test_interference_and_commutator_axes_are_explicit() -> None:
    graph = load_skill_graph()
    assert ("persona-voice", "factual-invariance") in graph.interference_pairs
    assert set(graph.commutator_axes) == {
        "cue-location",
        "cue-phrasing",
        "cue-order",
        "explicit-reminder",
        "cue-ablation",
    }

