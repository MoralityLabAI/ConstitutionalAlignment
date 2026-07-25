# Experiment Contract

- Freeze prompt text, topic order, turn order, model IDs, sampling, cost cap,
  analysis metrics, and highlight selection before generation.
- Use the same base model for both roles in the prompt-skill control.
- Hold both system prompts fixed when replacing the control Jinn weights with
  the registered hosted-RL Jinn adapter.
- Never label the prompted Beast control as a trained Beast adapter.
- Give every turn the full verbatim public transcript through the immediately
  preceding turn.
- Store provider reasoning separately from public council speech. Never feed
  private reasoning into later turns.
- Use one request at a time. Resume only from a prefix that exactly matches the
  frozen schedule.
- Select every cycle-two topic revisit as a highlight. Do not cherry-pick a
  topic or speaker after seeing outputs.
- Treat source interpretation as pending qualified review.
- Make no promotion, internal-state, population, or theological-validity claim
  from this qualitative run.
