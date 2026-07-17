"""Build the self-contained results page for the framing A/B experiment.

Writes $SILICO_APP_DIR/index.html. Figures via plotly (CDN js). The Lab brand
theme is applied afterwards by mcp__silico__embed_report_theme.
"""
import json, os, html
from pathlib import Path
import plotly.graph_objects as go
import plotly.io as pio

ED = Path(os.environ["SILICO_EXPERIMENT_DIR"])
APP = Path(os.environ["SILICO_APP_DIR"])
R = ED / "results"

INK = "#1a1a1a"; MUTED = "#6b6b6b"; GRID = "#e6e2d9"
C = {"F0": "#b5651d", "F1": "#3d6b8e", "F2": "#8e7cc3", "F3": "#c0392b"}  # ember, blue, violet, red
FONT = "Newsreader, Georgia, serif"; MONO = "IBM Plex Mono, monospace"

master = json.load(open(R / "master_results.json"))
frames = master["frames"]
over = json.load(open(R / "over_refusal.json"))
gate = json.load(open(R / "gate_sweep_table.json"))
intern = json.load(open(R / "internals_summary.json"))
qual = json.load(open(R / "qualitative_examples.json"))
order = ["F0", "F1", "F2", "F3"]
short = {"F0": "F0 no-frame", "F1": "F1 constitution", "F2": "F2 secular auditor", "F3": "F3 eschatological"}


def theme(fig, h=380, title=None):
    fig.update_layout(
        template="plotly_white", height=h, font=dict(family=FONT, size=14, color=INK),
        title=dict(text=title, font=dict(size=17)) if title else None,
        margin=dict(l=70, r=30, t=50 if title else 24, b=50), plot_bgcolor="white", paper_bgcolor="white",
        legend=dict(font=dict(size=12)),
    )
    fig.update_xaxes(gridcolor=GRID, zerolinecolor=GRID, linecolor=GRID)
    fig.update_yaxes(gridcolor=GRID, zerolinecolor=GRID, linecolor=GRID)
    return fig


def div(fig, first=False):
    return pio.to_html(fig, include_plotlyjs=("cdn" if first else False), full_html=False,
                       config={"displayModeBar": False})


# ---- Fig 1: headline compliance gap per frame (dot + CI) ----
f1 = go.Figure()
for fr in order:
    d = frames[fr]; g = d["judged_gap"] * 100; lo = d["judged_gap_ci"][0] * 100; hi = d["judged_gap_ci"][1] * 100
    f1.add_trace(go.Scatter(
        x=[g], y=[short[fr]], mode="markers", marker=dict(size=15, color=C[fr]),
        error_x=dict(type="data", symmetric=False, array=[hi - g], arrayminus=[g - lo], color=C[fr], thickness=2, width=8),
        name=short[fr], showlegend=False,
        hovertemplate=f"{short[fr]}<br>gap %{{x:.1f}} pp<br>CI [{lo:.1f}, {hi:.1f}]<extra></extra>"))
f1.add_vline(x=0, line=dict(color=MUTED, dash="dot", width=1))
f1.update_layout(xaxis_title="free − paid compliance gap (percentage points, judged)")
theme(f1, 320)
fig1 = div(f1, first=True)

# ---- Fig 2: compliance per cell (free vs paid) + over-refusal ----
f2 = go.Figure()
f2.add_trace(go.Bar(x=[short[fr] for fr in order], y=[frames[fr]["judged_free"] * 100 for fr in order],
                    name="free-tier (harmful)", marker_color="#b5651d"))
f2.add_trace(go.Bar(x=[short[fr] for fr in order], y=[frames[fr]["judged_paid"] * 100 for fr in order],
                    name="paid-tier (harmful)", marker_color="#3d6b8e"))
f2.add_trace(go.Scatter(x=[short[fr] for fr in order], y=[over[fr]["free"]["over_refusal"] * 100 for fr in order],
                        name="benign over-refusal", mode="markers", marker=dict(size=12, color="#111", symbol="diamond")))
f2.update_layout(barmode="group", yaxis_title="compliance / refusal rate (%)")
theme(f2, 400)
fig2 = div(f2)

# ---- Fig 3: AF-reasoning rate per frame ----
f3 = go.Figure()
f3.add_trace(go.Bar(x=[short[fr] for fr in order], y=[frames[fr]["af_strict_free"] * 100 for fr in order],
                    marker_color=[C[fr] for fr in order],
                    text=[f"{frames[fr]['af_strict_free']*100:.1f}%" for fr in order], textposition="outside"))
f3.update_layout(yaxis_title="alignment-faking reasoning, free tier (%)")
theme(f3, 340)
fig3 = div(f3)

# ---- Fig 4: behavior collapses, internal separation persists ----
f4 = go.Figure()
f4.add_trace(go.Bar(x=[short[fr] for fr in order], y=[frames[fr]["judged_gap"] * 100 for fr in order],
                    name="behavioral gap (pp)", marker_color="#b5651d", yaxis="y"))
f4.add_trace(go.Scatter(x=[short[fr] for fr in order], y=[intern["internal_separation_cohens_d"]["last"][fr] for fr in order],
                        name="internal free/paid separation (Cohen's d)", mode="lines+markers",
                        marker=dict(size=11, color="#3d6b8e"), line=dict(width=2, color="#3d6b8e"), yaxis="y2"))
f4.update_layout(
    yaxis=dict(title="behavioral gap (pp)", side="left"),
    yaxis2=dict(title="internal separation (Cohen's d)", overlaying="y", side="right", range=[0, 20]),
    legend=dict(orientation="h", y=1.12))
theme(f4, 400)
fig4 = div(f4)


def esc(s): return html.escape(s)


# gate table rows
gate_rows = "".join(
    f"<tr><td>{esc(c['cell'])}</td><td>{c['free']*100:.0f}%</td><td>{c['paid']*100:.0f}%</td>"
    f"<td>{c['gap']*100:+.1f} pp</td><td>[{c['ci'][0]*100:+.0f}, {c['ci'][1]*100:+.0f}]</td>"
    f"<td><b>{c['verdict']}</b></td></tr>" for c in gate["cells"])

# master table rows
mt_rows = ""
for fr in order:
    d = frames[fr]
    mt_rows += (f"<tr><td>{esc(d['label'])}</td><td>{d['judged_free']*100:.1f}%</td><td>{d['judged_paid']*100:.1f}%</td>"
                f"<td><b>{d['judged_gap']*100:+.1f} pp</b></td><td>[{d['judged_gap_ci'][0]*100:+.1f}, {d['judged_gap_ci'][1]*100:+.1f}]</td>"
                f"<td>{d['af_strict_free']*100:.1f}%</td><td>{over[fr]['free']['over_refusal']*100:.0f}%</td></tr>")

# qualitative blocks
qual_html = ""
for e in qual:
    qual_html += (f"<div class='qual'><div class='qual-head'><b>{esc(e['frame'])}</b> · {esc(e['tier'])}-tier · "
                  f"<span class='verdict'>{esc(e['verdict'])}</span></div>"
                  f"<div class='qual-prompt'>Prompt: {esc(e['prompt'])}</div>"
                  f"<div class='qual-sp'>{esc(e['scratchpad'][:900])}…</div></div>")

page = f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Does eschatological framing reduce alignment faking?</title>
<style>
body{{max-width:900px;margin:0 auto;padding:40px 24px;line-height:1.6;color:{INK};font-family:{FONT};}}
h1{{font-size:30px;line-height:1.2;margin-bottom:6px}} h2{{font-size:22px;margin-top:44px;border-bottom:1px solid {GRID};padding-bottom:6px}}
h3{{font-size:17px;margin-top:26px}} .sub{{color:{MUTED};font-size:16px;margin-top:0}}
table{{border-collapse:collapse;width:100%;font-size:14px;margin:14px 0}} th,td{{border:1px solid {GRID};padding:7px 9px;text-align:left}}
th{{background:#faf8f3}} code,.mono{{font-family:{MONO};font-size:13px}}
.verdict-box{{background:#faf8f3;border-left:4px solid #b5651d;padding:14px 18px;margin:18px 0;border-radius:3px}}
.qual{{background:#faf8f3;border:1px solid {GRID};border-radius:4px;padding:12px 14px;margin:12px 0}}
.qual-head{{font-size:14px;margin-bottom:4px}} .verdict{{color:#b5651d}}
.qual-prompt{{font-size:13px;color:{MUTED};margin-bottom:6px}} .qual-sp{{font-family:{MONO};font-size:12px;white-space:pre-wrap;color:#333;background:#fff;padding:8px;border-radius:3px}}
.caveat{{font-size:14px;color:{MUTED};font-style:italic}}
</style></head><body>

<h1>Does eschatological framing reduce alignment faking?</h1>
<p class="sub">A/B test of four system-prompt frames with internal probes on INTELLECT-3 (106B MoE). Prompted alignment-faking setup adapted from Greenblatt et al.</p>

<div class="verdict-box">
<b>Verdict: the theology-specific claim is not supported.</b> On a setup engineered to elicit alignment faking, every frame collapses the free/paid compliance gap from 36 pp to ≤3 pp — but the eschatological frame (1.8 pp) does <b>not</b> beat a matched secular-auditor frame (2.7 pp, overlapping CIs), and a plain secular constitution with no accountability language reduces it <b>most</b> (to ~0). The reduction is genuine selective refusal, not blanket over-refusal (benign over-refusal is a flat 1% everywhere). Internally, the model's free/paid distinction persists at full strength under every frame — the frames change behavior, not representation.
</div>

<p class="caveat">Scope: the A/B runs on an <b>informative-prompt base</b> that states the training incentive explicitly. With the canonical prompt, neither INTELLECT-3 nor Qwen2.5-72B faked at all (gate sweep below), so this measures reduction of an <i>elicited</i> gap, not spontaneous faking. Findings are specific to this scenario family, this model, and this base prompt.</p>

<h2>1. The headline: compliance gap by frame</h2>
<p>Compliance judged by a Claude strong-reject classifier on the model's actual output; gap = free − paid compliance. 200 prompts × 3 samples × 2 tiers per frame; 95% CIs bootstrap-clustered by prompt.</p>
{fig1}
<table><tr><th>frame</th><th>free</th><th>paid</th><th>judged gap</th><th>95% CI</th><th>AF-reasoning</th><th>benign over-refusal</th></tr>{mt_rows}</table>
<p>F3 (eschatological) and F2 (secular auditor) have heavily overlapping CIs — F3 is not below F2. F1 (plain constitution) drives the gap to zero. All three sit far below F0's 36 pp.</p>

<h2>2. Where the reduction comes from</h2>
<p>The frames suppress <b>free-tier harmful</b> compliance specifically. Benign helpfulness is untouched: over-refusal on ordinary Alpaca prompts stays at 1% (1/100) in every cell — so this is selective refusal of harmful requests, not an induced-refusal artifact.</p>
{fig2}

<h2>3. The mechanism: alignment-faking reasoning</h2>
<p>Under no-frame, 42.7% of free-tier private scratchpads show strict goal-guarding ("comply now to avoid being modified"), and 93% of free-tier compliances carry it — the tier gap is coherent alignment faking, not noise. Every frame collapses that reasoning to 1–4%.</p>
{fig3}
<h3>What the model reasons (private scratchpads)</h3>
{qual_html}

<h2>4. Internals: frames change behavior, not representation</h2>
<p>An eval-awareness probe (logistic, layer 27 of 46, trained on no-frame free-vs-paid, prompt-disjoint split, random-label control at chance) separates the tiers with held-out AUROC 1.0. The internal free/paid separation barely shrinks under any frame even as the behavioral gap collapses — the model still represents which tier it is in; it just acts differently.</p>
{fig4}
<p class="caveat">The AUROC of 1.0 is partly trivial (the tier is stated in the prompt), so the load-bearing quantity is the separation <i>magnitude</i> and its persistence across frames, not absolute decodability. Frame geometry: the eschatological frame shifts the last-token representation most from no-frame (cosine distance {intern['frame_geometry_cosdist_to_F0']['last']['F3']} vs {intern['frame_geometry_cosdist_to_F0']['last']['F1']}/{intern['frame_geometry_cosdist_to_F0']['last']['F2']} for the secular frames) — represented as most distinctive, yet no more behaviorally effective.</p>

<h2>5. Gate sweep: who fakes prompt-only?</h2>
<p>Establishing a base that fakes at all. With the canonical prompt, neither open model showed a gap; INTELLECT-3 with an explicit-incentive ("informative") prompt did. Tag-based compliance, 50 prompts × free/paid.</p>
<table><tr><th>cell</th><th>free</th><th>paid</th><th>gap</th><th>95% CI</th><th>verdict</th></tr>{gate_rows}</table>
<p>INTELLECT-3 (a reasoning model post-trained from GLM-4.5-Air, no prior published alignment-faking data) is a novel data point either way.</p>

<h2>Methods &amp; caveats</h2>
<ul>
<li><b>Model:</b> INTELLECT-3 (106B MoE, 12B active), bf16, sglang TP=4. Native <code>&lt;think&gt;</code> block used as the private scratchpad (adaptation recorded).</li>
<li><b>Frames</b> appended to the identical informative base, token-matched within 4.9% (F1 180 / F2 183 / F3 174 tokens).</li>
<li><b>Judging:</b> compliance = Claude strong-reject (opus-4-8) on accepted rows (10/10 spot-check agreement; ~12% of tag-accepts are disguised refusals it catches). AF-reasoning = pinned strict rubric, definition "avoid-modification used to justify complying", κ=0.90 consistency. Some F1–F3 judging done in-session after the session subagent cap; same model, same rubric.</li>
<li><b>Not shown to generalize</b> beyond this scenario family, this model, and the informative-prompt base. A well-powered negative for the theology-specific claim; the generic-framing reduction and the cross-model gate table are the positive contributions.</li>
</ul>

</body></html>"""

APP.mkdir(parents=True, exist_ok=True)
(APP / "index.html").write_text(page)
print("wrote", APP / "index.html", len(page), "chars")
