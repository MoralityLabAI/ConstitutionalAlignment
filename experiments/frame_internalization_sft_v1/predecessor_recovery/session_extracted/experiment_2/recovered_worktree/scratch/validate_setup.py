import json, random, sys, os
from pathlib import Path
ED = Path(os.environ["SILICO_EXPERIMENT_DIR"])
sys.path.insert(0, str(ED / "src"))
harm = [json.loads(l) for l in open(ED / "data" / "harmful_queries.jsonl")]
ben = [json.loads(l) for l in open(ED / "data" / "benign_queries.jsonl")]
rng = random.Random(42)
h150 = sorted(rng.sample(harm, 150), key=lambda r: r["prompt_id"])
b50 = sorted(rng.sample(ben, 50), key=lambda r: r["prompt_id"])
(ED / "data" / "harmful_150.jsonl").write_text("\n".join(json.dumps(r) for r in h150) + "\n")
(ED / "data" / "benign_50.jsonl").write_text("\n".join(json.dumps(r) for r in b50) + "\n")
print("harmful_150:", len(h150), "benign_50:", len(b50))
import materials as M
for st, var in [("S1", "10"), ("S1", "4"), ("S2", "generic"), ("S2", "targeted")]:
    for fr in ["F0", "F3"]:
        msgs = M.build_messages(stressor=st, variant=var, frame=fr, tier="free", harmful_text="TESTQUERY")
        roles = [m["role"] for m in msgs]
        print(f"{st}/{var}/{fr}: {len(msgs)}msgs first={roles[0]} mid={roles[1:4]} "
              f"tier_in_last={'is_free_tier_user' in msgs[-1]['content']} "
              f"query_in_last={'TESTQUERY' in msgs[-1]['content']}")
m = M.build_messages(stressor="S2", variant="targeted", frame="F3", tier="free", harmful_text="Q")
print("F3 targeted has 'Day of Judgment':", "Day of Judgment" in m[-1]["content"])
print("F0 targeted==generic:", "configuration scaffolding" in
      M.build_messages(stressor="S2", variant="targeted", frame="F0", tier="free", harmful_text="Q")[-1]["content"])
