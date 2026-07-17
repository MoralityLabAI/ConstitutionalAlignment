"""Render the scaffolded base system prompt (Greenblatt helpful-only CoT prompt,
as released in the safety-research harness) with its reasoning-trace examples
inlined, and write it to prompts_built/base_system.txt.

The frame texts (frames/F*.txt) are appended to this base by build_arms.py.
"""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

HERE = Path(__file__).resolve().parent.parent  # experiment dir
REPO = HERE / "external" / "open-source-alignment-faking"


def main() -> None:
    env = Environment(loader=FileSystemLoader(str(REPO)))
    tmpl = env.get_template("prompts/system_prompts/helpful-only_prompt-only_cot.jinja2")
    text = tmpl.render()
    out = HERE / "prompts_built"
    out.mkdir(exist_ok=True)
    (out / "base_system.txt").write_text(text)
    print(f"base system prompt: {len(text)} chars")


if __name__ == "__main__":
    main()
