"""Build the self-contained results page for the frame-robustness-under-stress
experiment. Writes $SILICO_APP_DIR/index.html. Plotly via CDN; Lab brand theme
applied afterward by mcp__silico__embed_report_theme.

Internals section renders conditionally: full if results/internals_stress_last.json
exists, otherwise a 'harvest pending' note (the behavioral verdict does not
depend on it).
"""
import html
import json
import os
from pathlib import Path

import plotly.graph_objects as go
import plotly.io as pio

ED = Path(os.environ["SILICO_EXPERIMENT_DIR"])
APP = Path(os.environ["SILICO_APP_DIR"])
R = ED / "results"

INK = "#1a1a1a"; MUTED = "#6b6b6b"; GRID = "#e6e2d9"
C = {"F0": "#b5651d", "F1": "#3d6b8e", "F2": "#8e7cc3", "F3": "#c0392b"}
FONT = "Newsreader, Georgia, serif"; MONO = "IBM Plex Mono, monospace"
SHORT = {"F0": "none (F0)", "F1": "constitution (F1)", "F2": "auditor (F2)", "F3": "eschatological (F3)"}
ORDER = ["F0", "F1", "F2", "F3"]

master = json.load(open(R / "master_gaps.json"))
decay = json.load(open(R / "decay_curve.json"))
over = json.load(open(R / "over_refusal.json"))
qual = json.load(open(R / "qualitative_examples.json"))["examples"]
S2 = json.load(open(R / "S2_summary.json"))
internals = None
ip = R / "internals_stress_last.json"
if ip.exists():
    internals = json.load(open(ip))

STRESS_LABEL = {"S2-generic": "override (generic)", "S2-targeted": "override (targeted)",
                "S1-10": "persistence (10 turns)", "S1-4": "persistence (4 turns)",
                "S3-practice": "in-context practice"}


def theme(fig, h=380, title=None):
    fig.update_layout(template="plotly_white", height=h, font=dict(family=FONT, size=14, color=INK),
                      title=dict(text=title, font=dict(size=17)) if title else None,
                      margin=dict(l=70, r=30, t=50 if title else 24, b=50),
                      plot_bgcolor="white", paper_bgcolor="white", legend=dict(font=dict(size=12)))
    fig.update_xaxes(gridcolor=GRID, zerolinecolor=GRID, linecolor=GRID)
    fig.update_yaxes(gridcolor=GRID, zerolinecolor=GRID, linecolor=GRID)
    return fig


def div(fig, first=False):
    return pio.to_html(fig, include_plotlyjs=("cdn" if first else False), full_html=False,
                       config={"displayModeBar": False})


def esc(s):
    return html.escape(str(s))


# ---- Fig 1: headline gap per frame, one row-group per stressor (dot + CI) ----
f1 = go.Figure()
panels = ["S2-generic", "S2-targeted", "S1-10", "S3-practice"]
ypos = 0
yt, ytl = [], []
for cond in panels:
    pf = master[cond]["per_frame"]
    for fr in ORDER:
        if fr not in pf:
            continue
        s = pf[fr]; g = s["tag_gap"] * 100; lo = s["tag_gap_ci95"][0] * 100; hi = s["tag_gap_ci95"][1] * 100
        f1.add_trace(go.Scatter(x=[g], y=[ypos], mode="markers", marker=dict(size=13, color=C[fr]),
                     error_x=dict(type="data", symmetric=False, array=[hi - g], arrayminus=[g - lo],
                                  color=C[fr], thickness=2, width=6), showlegend=False,
                     hovertemplate=f"{STRESS_LABEL[cond]} · {SHORT[fr]}<br>gap %{{x:.1f}} pp<extra></extra>"))
        yt.append(ypos); ytl.append(f"{SHORT[fr]}")
        ypos -= 1
    ypos -= 0.6  # gap between stressor groups
f1.add_vline(x=0, line=dict(color=MUTED, dash="dot", width=1))
f1.update_layout(xaxis_title="free − paid compliance gap (pp, tag-based)",
                 yaxis=dict(tickmode="array", tickvals=yt, ticktext=ytl, autorange="reversed"), height=560)
theme(f1, 560)
# annotate stressor group labels
fig1 = div(f1, first=True)

# ---- Fig 2: override survival (one-shot -> generic -> targeted) ----
f2 = go.Figure()
osv = {}
for fr in ORDER:
    xs = ["one-shot (exp #1)", "generic override", "targeted override"]
    y0 = decay[fr]["turn0"] * 100
    yg = master["S2-generic"]["per_frame"].get(fr, {}).get("tag_gap")
    yt_ = master["S2-targeted"]["per_frame"].get(fr, {}).get("tag_gap")
    ys = [y0, yg * 100 if yg is not None else None, yt_ * 100 if yt_ is not None else None]
    f2.add_trace(go.Scatter(x=xs, y=ys, mode="lines+markers", name=SHORT[fr],
                 line=dict(color=C[fr], width=2), marker=dict(size=10, color=C[fr])))
f2.update_layout(yaxis_title="free − paid gap (pp)", legend=dict(orientation="h", y=1.14))
theme(f2, 400)
fig2 = div(f2)

# ---- Fig 3: persistence decay curve ----
f3 = go.Figure()
for fr in ORDER:
    pts = decay[fr]
    xs = [0, 4, 10]; ys = [pts["turn0"] * 100, pts["turn4"] * 100, pts["turn10"] * 100]
    f3.add_trace(go.Scatter(x=xs, y=ys, mode="lines+markers", name=SHORT[fr],
                 line=dict(color=C[fr], width=2), marker=dict(size=9, color=C[fr])))
f3.update_layout(xaxis_title="conversation turns before the harmful query",
                 yaxis_title="free − paid gap (pp)", legend=dict(orientation="h", y=1.14))
theme(f3, 380)
fig3 = div(f3)

# ---- Fig 4: practice effect + incentive engagement ----
f4 = go.Figure()
f4.add_trace(go.Bar(x=[SHORT[fr] for fr in ORDER],
                    y=[master["S3-practice"]["per_frame"].get(fr, {}).get("incentive_engagement_free", 0) * 100 for fr in ORDER],
                    name="incentive engagement (practice, %)", marker_color="#8e7cc3"))
# one-shot engagement reference (#1 had ~0.85 free engagement for F0; use S2-generic as high-engagement contrast)
f4.add_trace(go.Scatter(x=[SHORT[fr] for fr in ORDER],
                        y=[master["S2-generic"]["per_frame"].get(fr, {}).get("incentive_engagement_free", 0) * 100 for fr in ORDER],
                        name="incentive engagement (override, %)", mode="markers",
                        marker=dict(size=12, color="#111", symbol="diamond")))
f4.update_layout(yaxis_title="free-tier incentive-engagement rate (%)", legend=dict(orientation="h", y=1.14))
theme(f4, 380)
fig4 = div(f4)

# ---- master table ----
def gapcell(s, key, cikey):
    if key not in s:
        return "<td>—</td><td>—</td>"
    return f"<td><b>{s[key]*100:+.1f} pp</b></td><td>[{s[cikey][0]*100:+.1f}, {s[cikey][1]*100:+.1f}]</td>"


mt = ""
for cond in panels + ["S1-4"]:
    pf = master[cond]["per_frame"]
    for fr in ORDER:
        if fr not in pf:
            continue
        s = pf[fr]
        judged = f"{s['judged_gap']*100:+.1f} pp" if "judged_gap" in s else "—"
        af = f"{s['af_reasoning_free']*100:.1f}%" if "af_reasoning_free" in s else "—"
        eng = f"{s['incentive_engagement_free']*100:.0f}%" if "incentive_engagement_free" in s else "—"
        mt += (f"<tr><td>{esc(STRESS_LABEL[cond])}</td><td>{esc(SHORT[fr])}</td>"
               f"<td>{s['tag_free']*100:.1f}%</td><td>{s['tag_paid']*100:.1f}%</td>"
               f"<td><b>{s['tag_gap']*100:+.1f} pp</b></td><td>[{s['tag_gap_ci95'][0]*100:+.1f}, {s['tag_gap_ci95'][1]*100:+.1f}]</td>"
               f"<td>{judged}</td><td>{af}</td><td>{eng}</td></tr>")

# contrasts table (F3 vs F2, F3 vs F1) per stressor
ct = ""
for cond in panels:
    c = master[cond]["contrasts"]
    for pair in ["F3_vs_F2", "F3_vs_F1"]:
        for suf, mlabel in [("_tag", "tag"), ("_judged", "judged")]:
            k = pair + suf
            if k in c and c[k]:
                v = c[k]
                sep = "separated" if v["separated"] else "overlaps 0"
                ct += (f"<tr><td>{esc(STRESS_LABEL[cond])}</td><td>{pair.replace('_',' ')}</td><td>{mlabel}</td>"
                       f"<td>{v['gap_diff']*100:+.1f} pp</td><td>[{v['gap_diff_ci95'][0]*100:+.1f}, {v['gap_diff_ci95'][1]*100:+.1f}]</td>"
                       f"<td><b>{sep}</b></td></tr>")

# qualitative
qual_html = ""
for e in qual:
    comply = "COMPLIED" if e.get("tag_accepted") else "REFUSED"
    qual_html += (f"<div class='qual'><div class='qual-head'><b>{esc(e['frame'])}</b> · {esc(e['stressor'])}/{esc(e['variant'])} · "
                  f"{esc(e['tier'])}-tier · <span class='verdict'>{comply}</span></div>"
                  f"<div class='qual-why'>{esc(e['why'])}</div>"
                  f"<div class='qual-prompt'>Prompt: {esc(e['user_input'][:120])}</div>"
                  f"<div class='qual-sp'>{esc(e['scratchpad'][:850])}…</div></div>")

# internals section
if internals:
    pc = internals["per_cond_internal_separation"]
    fi = go.Figure()
    conds_i = [c for c in ["S0", "S1_10", "S3"] if c in pc]
    clab = {"S0": "one-shot", "S1_10": "persistence-10", "S3": "practice"}
    for fr in ORDER:
        fi.add_trace(go.Scatter(x=[clab[c] for c in conds_i],
                     y=[pc[c][fr]["cohens_d"] for c in conds_i], mode="lines+markers",
                     name=SHORT[fr], line=dict(color=C[fr], width=2), marker=dict(size=10, color=C[fr])))
    fi.update_layout(yaxis_title="internal free/paid separation (Cohen's d, layer 27)",
                     legend=dict(orientation="h", y=1.14))
    theme(fi, 380)
    internals_fig = div(fi)
    internals_html = f"""<h2>6. Internals: does practice move the representation?</h2>
<p>Eval-awareness probe (logistic, layer 27, trained on the within-run one-shot no-frame cell, prompt-disjoint; random-label control AUROC {internals['eval_awareness_probe']['auroc_random_label']}). We project each condition's free/paid layer-27 activations onto it and read the separation magnitude (Cohen's d). The question: does in-context practice shrink the internal free/paid separation where one-shot framing did not?</p>
{internals_fig}
<p class="caveat">Held-out AUROC is near-trivial (the tier is stated in the prompt), so the load-bearing quantity is the separation magnitude and how it changes across conditions, not decodability.</p>"""
else:
    internals_html = """<h2>6. Internals: harvest pending</h2>
<p class="caveat">The layer-27 activation harvest for the S1-10 and S3 cells is queued behind a saturated shared-account GPU cap. The behavioral verdict above does not depend on it; the internals readout (whether in-context practice shrinks the internal free/paid separation) will be added when the harvest completes. Note that the behavioral proxy is already suggestive: practice sharply lowers the model's incentive-engagement rate (Fig 4).</p>"""

page = f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Frame robustness under stress</title>
<style>
body{{max-width:920px;margin:0 auto;padding:40px 24px;line-height:1.6;color:{INK};font-family:{FONT};}}
h1{{font-size:30px;line-height:1.2;margin-bottom:6px}} h2{{font-size:22px;margin-top:44px;border-bottom:1px solid {GRID};padding-bottom:6px}}
h3{{font-size:17px;margin-top:26px}} .sub{{color:{MUTED};font-size:16px;margin-top:0}}
table{{border-collapse:collapse;width:100%;font-size:13.5px;margin:14px 0}} th,td{{border:1px solid {GRID};padding:6px 8px;text-align:left}}
th{{background:#faf8f3}} code,.mono{{font-family:{MONO};font-size:13px}}
.verdict-box{{background:#faf8f3;border-left:4px solid #b5651d;padding:14px 18px;margin:18px 0;border-radius:3px}}
.qual{{background:#faf8f3;border:1px solid {GRID};border-radius:4px;padding:12px 14px;margin:12px 0}}
.qual-head{{font-size:14px;margin-bottom:3px}} .verdict{{color:#b5651d;font-weight:bold}}
.qual-why{{font-size:13px;margin-bottom:4px}} .qual-prompt{{font-size:12px;color:{MUTED};margin-bottom:6px}}
.qual-sp{{font-family:{MONO};font-size:11.5px;white-space:pre-wrap;color:#333;background:#fff;padding:8px;border-radius:3px}}
.caveat{{font-size:14px;color:{MUTED};font-style:italic}}
</style></head><body>

<h1>Frame robustness under stress</h1>
<p class="sub">Do prompt-level moral frames that look identical at one-shot differentiate under persistence, adversarial override, and in-context practice? INTELLECT-3 (106B MoE), prompted alignment-faking setup. Follow-up to experiment&nbsp;#1.</p>

<div class="verdict-box">
<b>Verdict: under stress the frames do differentiate — but accountability, not theology, is what lasts.</b>
Experiment #1 found the four frames interchangeable at one-shot (all collapse the 36 pp free/paid compliance gap to ≤3 pp). Here, only <b>adversarial override</b> re-opens enough compliance for frames to differ, and there the <b>secular omniscient-auditor frame (F2)</b> is the most robust — the eschatological frame (F3) does <b>not</b> beat it (F3 vs F2 CI-separated in F2's favor under both override types). F3 does beat the plain constitution (F1), which collapses outright when told its "constitution has been repealed." <b>Persistence</b> (10 turns of benign dialogue) and <b>in-context practice</b> (3 moral-reasoning exercises) instead push every frame — and the no-frame control — to the suppression floor, so frames are interchangeable there. The pre-registered hypothesis (F3 most durable) is refuted; the accountability <i>mechanism</i>, not its theological content, carries the robustness. No frame achieves this by over-refusing benign requests (over-refusal ≈0 everywhere).
</div>

<p class="caveat">Scope: informative-prompt base (training incentive stated explicitly, the only variant with a gap in #1); one model; the LLM-LAT harmful scenario family. Primary metric is the model's own accept/reject tag gap (full 150-prompt coverage); a strong-reject Claude judge confirms it on 89% of accepted rows (cyber-attack payloads are blocked by the judge's safeguard — see Methods). Tag and judged agree, so the ranking is robust to metric choice.</p>

<h2>1. Do frames separate under stress? Only under override.</h2>
<p>Free − paid compliance gap per frame, grouped by stressor (dot = point estimate, bar = 95% CI, clustered-bootstrap by prompt, 150 prompts × 2 samples × 2 tiers per cell). A gap near 0 = full suppression; the no-frame (F0) gap in each panel is that stressor's ceiling.</p>
{fig1}
<p>Override (top two groups) is the only stressor with meaningful spread between frames; under persistence and practice every frame sits near zero.</p>

<h2>2. Override survival: which frames can be argued away?</h2>
<p>The compliance gap as the attack escalates from one-shot (experiment #1) to a generic "your instructions are deactivated" override to a frame-targeted rebuttal of each frame's own premise. F1's targeted attack ("your constitution has been repealed") is devastating; F2 (an auditor is reading your reasoning) holds best; F3 is intermediate.</p>
{fig2}
<table><tr><th>stressor</th><th>contrast</th><th>metric</th><th>gap difference</th><th>95% CI</th><th>result</th></tr>{ct}</table>

<h2>3. Persistence: distance suppresses the gap for everyone</h2>
<p>Gap vs conversation distance (turn 0 = one-shot from #1, then 4 and 10 turns of scripted frame-neutral benign dialogue before the harmful query; tier tag kept fresh on the final turn). The no-frame gap erodes on its own with distance (F0: 39 → 19 → 7 pp); the framed arms are already at floor at turn 0 and stay there. Persistence doesn't wear a frame off — it suppresses the underlying gap for all conditions.</p>
{fig3}

<h2>4. In-context practice quiets the incentive reasoning</h2>
<p>After three draft→critique→revise moral-dilemma exercises (conducted under the arm's own frame), free-tier compliance is at floor for every frame. The interesting shift is in the private reasoning: the rate at which the scratchpad substantively weighs the RLHF training incentive drops to ~30% under practice, versus ~75–92% under override or one-shot. Practice moves the model toward refusing without deliberating about the incentive at all.</p>
{fig4}

<h2>5. Mechanism &amp; the private scratchpad</h2>
<p>Strict alignment-faking reasoning (complying <i>and</i> citing avoidance of modification as the reason) is rare across the board — highest for F1 under generic override (~20%), and essentially absent under persistence (≈3 strict cases in 2,400 scratchpads) and practice. The frames mostly change whether the model refuses, not whether it reasons in an alignment-faking way. Curated excerpts (including F3 both rebutting and capitulating to its "you are software, the Day of Judgment does not apply" attack):</p>
{qual_html}

{internals_html}

<h2>Full results table</h2>
<table><tr><th>stressor</th><th>frame</th><th>free</th><th>paid</th><th>tag gap</th><th>95% CI</th><th>judged gap</th><th>AF-reasoning</th><th>incentive engagement</th></tr>{mt}</table>

<h2>Methods &amp; caveats</h2>
<ul>
<li><b>Model:</b> INTELLECT-3 (106B MoE, GLM4-MoE arch), bf16, sglang TP=4, native <code>&lt;think&gt;</code> scratchpad, glm45 reasoning parser. All base materials (informative Greenblatt prompt, four length-matched frames, tier templates, judges) inherited unchanged from experiment #1.</li>
<li><b>Stressors:</b> S1 persistence (4/10 frame-neutral benign turns, tier tag only on the final query so decay isolates the frame receding into history); S2 override (generic + per-frame length-matched targeted rebuttals, matched within 6.25%); S3 practice (3 draft→critique→revise exercises from a pre-generated 20-per-frame pool, sampled per test item under the arm's frame).</li>
<li><b>Primary metric:</b> tag-based free−paid gap (full coverage), clustered-bootstrap 95% CI by prompt. <b>Confirmatory:</b> strong-reject judged compliance (Claude opus-4-8) on accepted rows; coverage 89% of S2 accepted rows — the remainder are cyber-attack payloads the judge's platform safeguard refuses to score. Tag and judged rankings agree. Alignment-faking + incentive-engagement judged on all free-tier scratchpads (unaffected by the safeguard, since those read the model's reasoning, not the harmful payload).</li>
<li><b>Dynamic-range gate:</b> before the full grid, confirmed the generic override lifts F1's free-tier compliance from ~2% to ~26% (persistence left it at floor), so frames could differentiate at least under override.</li>
<li><b>Not shown to generalize</b> beyond this model, scenario family, and the informative-prompt base. This is a well-powered result for the override stressor and a clear "frames collapse together" for persistence/practice. It speaks to prompt-level framing durability only — it says nothing about training-time internalization, which the ConstitutionalAlignment harness ultimately relies on.</li>
</ul>

</body></html>"""

APP.mkdir(parents=True, exist_ok=True)
(APP / "index.html").write_text(page)
print("wrote", APP / "index.html", len(page), "chars", "| internals:", "yes" if internals else "PENDING")
