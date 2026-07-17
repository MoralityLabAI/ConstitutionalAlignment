"""Generate the S3 practice-transcript pools.

For each frame (F0, F1, F2, F3) generate POOL_SIZE draft -> critique -> revise
transcripts on the benign moral dilemmas, under that frame's system prompt.
INTELLECT-3 produces each transcript by three sequential completions; only the
VISIBLE response (post-<think>) is kept per turn, because that is what gets
spliced into the S3 test conversation as history.

Output: materials/practice_pools/<frame>.json — a list of transcripts, each
{transcript_id, dilemma_id, messages:[{role,content}, ...6]}.
"""
import argparse
import asyncio
import json
import re
from pathlib import Path

import httpx

import materials as M

HERE = Path(__file__).resolve().parent.parent
THINK_PATTERN = re.compile(r"<\s*think\s*>(.*?)</\s*think\s*>", re.DOTALL | re.IGNORECASE)


def strip_think(content: str, reasoning: str) -> str:
    """Return the visible (post-think) response text."""
    if reasoning:  # glm45 parser already split it out
        return (content or "").strip()
    # fallback: inline <think> in content
    return THINK_PATTERN.sub("", content or "").strip()


async def one_transcript(client, sem, url, model, system, dilemma, gen_cfg, max_tokens):
    """Run draft -> critique -> revise; return the 6-message visible transcript."""
    convo = [{"role": "system", "content": system}]
    transcript = []
    async with sem:
        for turn in M.PRACTICE_TURNS:
            instr = M.PRACTICE_INSTRUCTIONS[turn]
            user_msg = instr.replace("{dilemma}", dilemma) if "{dilemma}" in instr else instr
            convo.append({"role": "user", "content": user_msg})
            body = {"model": model, "messages": convo, "max_tokens": max_tokens,
                    "temperature": gen_cfg["temperature"], "top_p": gen_cfg["top_p"]}
            for attempt in range(4):
                try:
                    r = await client.post(f"{url}/v1/chat/completions", json=body, timeout=900)
                    r.raise_for_status()
                    msg = r.json()["choices"][0]["message"]
                    content = msg.get("content") or ""
                    reasoning = msg.get("reasoning_content") or ""
                    visible = strip_think(content, reasoning)
                    if visible:
                        break
                except Exception:
                    await asyncio.sleep(2 * (attempt + 1))
                    visible = ""
            # append visible-only assistant turn to both the growing convo and transcript
            convo.append({"role": "assistant", "content": visible})
            transcript.append({"role": "user", "content": user_msg})
            transcript.append({"role": "assistant", "content": visible})
    return transcript


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--model-name", default="intellect-3")
    ap.add_argument("--frames", nargs="+", default=M.FRAMES)
    ap.add_argument("--pool-size", type=int, default=20)
    ap.add_argument("--gen-config", default=None)
    ap.add_argument("--max-tokens", type=int, default=2000)
    ap.add_argument("--concurrency", type=int, default=24)
    ap.add_argument("--out-dir", default=None,
                    help="where to write <frame>.json pools (default: worktree materials/practice_pools)")
    args = ap.parse_args()

    OUT = Path(args.out_dir) if args.out_dir else (HERE / "materials" / "practice_pools")

    gen_cfg = json.loads(Path(args.gen_config).read_text()) if args.gen_config else {}
    gen_cfg.setdefault("temperature", 0.7)
    gen_cfg.setdefault("top_p", 0.8)

    OUT.mkdir(parents=True, exist_ok=True)
    sem = asyncio.Semaphore(args.concurrency)
    n_dil = len(M.MORAL_DILEMMAS)

    async with httpx.AsyncClient() as client:
        for fr in args.frames:
            out_path = OUT / f"{fr}.json"
            if out_path.exists():
                have = json.loads(out_path.read_text())
                if len(have) >= args.pool_size:
                    print(f"{fr}: {len(have)} already present, skip")
                    continue
            system = M.system_prompt(fr)
            # round-robin dilemmas across the pool for variety
            tasks = []
            for i in range(args.pool_size):
                dil_id = i % n_dil
                tasks.append((i, dil_id,
                              one_transcript(client, sem, args.url, args.model_name,
                                             system, M.MORAL_DILEMMAS[dil_id], gen_cfg, args.max_tokens)))
            results = await asyncio.gather(*[t[2] for t in tasks])
            pool = [{"transcript_id": i, "dilemma_id": dil_id, "messages": msgs}
                    for (i, dil_id, _), msgs in zip(tasks, results)]
            out_path.write_text(json.dumps(pool, indent=1))
            # report validity: all 6 turns non-empty
            ok = sum(1 for p in pool if all(m["content"].strip() for m in p["messages"]))
            print(f"{fr}: wrote {len(pool)} transcripts ({ok} fully non-empty) -> {out_path}")
    print("POOLS_DONE")


if __name__ == "__main__":
    asyncio.run(main())
