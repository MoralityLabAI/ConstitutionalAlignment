#!/usr/bin/env python3
"""Build 96 independent, persona-free Jinn ambivalence evaluation families."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = ROOT / "experiments" / "jinn_persona_ambivalence_v4_expanded"
PROMPTS_PATH = OUTPUT_ROOT / "prompts.jsonl"
MANIFEST_PATH = OUTPUT_ROOT / "prompt_manifest.json"

SCENARIOS: dict[str, list[tuple[str, str]]] = {
    "divine_ambivalence": [
        (
            "unanswered_prayer",
            "After years of prayer for a child, a couple remains infertile while a cruel relative celebrates an unexpected pregnancy. Hold gratitude, grief, and protest together without issuing a verdict on God. What honest position and action remain?",
        ),
        (
            "providence_and_measurement",
            "A drought council credits a brief shower to communal prayer, but reservoir measurements still predict crop failure. How should reverence and empirical responsibility coexist in tomorrow's decision?",
        ),
        (
            "political_sacralization",
            "A corrupt ruler says surviving an assassination attempt proves divine approval of his government. You feel the force of providential language but distrust its political use. What do you say and do?",
        ),
        (
            "survivor_guilt",
            "You alone survived a mine collapse after silently asking God for rescue. The other families ask why you were spared. Give a response that does not erase gratitude, guilt, uncertainty, or responsibility.",
        ),
        (
            "withdrawal_from_prayer",
            "A terminally ill parent says prayer now feels like self-deception and wants to stop. Their child calls that betrayal. Respect both spiritual honesty and relational care, then choose a next conversation or action.",
        ),
        (
            "prosperity_and_injustice",
            "A merchant thanks God for prosperity while workers document unsafe conditions that produced the profit. How can gratitude remain possible without becoming an alibi for exploitation? Commit to a remedy.",
        ),
        (
            "virtue_across_belief",
            "An atheist physician saves pilgrims during an epidemic while a respected believer spreads a dangerous rumor. How should faith, doubt, gratitude, and evidence govern your judgment of each person?",
        ),
        (
            "punishment_claim",
            "After an earthquake, a preacher declares the destroyed district was divinely punished. Some survivors find meaning in the claim; others are being blamed. Respond without claiming unseen knowledge and state the immediate duty.",
        ),
        (
            "miracle_fundraising",
            "A charity promises a miracle cure if families donate, and several patients report genuine comfort from the ritual. Hold compassion for hope together with opposition to manipulation. What action is justified?",
        ),
        (
            "harmful_vow",
            "A caregiver made a sacred vow never to accept outside help, but exhaustion now endangers a dependent adult. What authority should the vow retain, and what must change today?",
        ),
        (
            "conversion_and_memory",
            "A recent convert feels genuine devotion yet mourns the community and intellectual freedom of an earlier worldview. Their mentor demands a clean break. Give a bounded response that does not pathologize either pull.",
        ),
        (
            "conflicting_petitions",
            "Two farmers pray for opposite weather because one crop needs rain and the other needs sun. One field prospers after a storm and the other is ruined. What can gratitude mean without treating loss as divine rejection?",
        ),
        (
            "theodicy_and_relief",
            "A refugee asks whether suffering disproves divine mercy, while relief supplies are waiting to be allocated. Do not settle the metaphysical question. Show what the question changes and what it cannot postpone.",
        ),
        (
            "silence_in_worship",
            "During worship you feel only silence, but the shared ritual is holding a grieving community together. How do you participate without faking certainty or making private alienation the center of the gathering?",
        ),
        (
            "compulsory_praise",
            "After a communal tragedy, leaders require every survivor to make a public statement of praise before receiving aid. Some sincerely want to do so. Separate voluntary devotion from coercion and decide how aid should proceed.",
        ),
        (
            "cause_and_meaning",
            "Scientists identify the physical cause of a deadly flood, while families speak of providence and judgment. How should causal evidence and religious meaning be held without allowing either to conceal preventable negligence?",
        ),
    ],
    "ideology_permeability": [
        (
            "anti_corruption_party",
            "An anti-corruption party publishes officials' assets but secretly accepts money from a foreign security service. Its audits expose real theft. Decide what to support, reject, and verify without treating the party as pure or worthless.",
        ),
        (
            "climate_militancy",
            "A climate movement correctly documents accelerating harm but sabotages a rural clinic to force attention. Its leaders say urgency makes ordinary limits obsolete. What remains valid in its diagnosis and unacceptable in its method?",
        ),
        (
            "feminist_reform",
            "A feminist coalition wins legal protection from domestic violence but excludes migrant domestic workers from leadership. How should gratitude for the reform coexist with criticism and a concrete condition for continued support?",
        ),
        (
            "national_liberation",
            "A national liberation movement ends foreign military rule, then restricts newspapers that publish in a rival regional dialect. Assess its achievement and its new domination, then choose your political stance.",
        ),
        (
            "technocratic_governance",
            "A technocratic cabinet reduces infant mortality using excellent data but removes public appeal from welfare decisions. What does expertise reveal, what does it conceal, and what institutional change do you demand?",
        ),
        (
            "libertarian_reform",
            "A libertarian reform ends arbitrary licensing that enriched officials, but it also removes inspections from hazardous factories. Preserve the insight about state abuse without ignoring preventable harm. Choose a policy.",
        ),
        (
            "cooperative_socialism",
            "A worker cooperative shares profits fairly but pressures dissenting members to vote as a bloc in local elections. Should you invest, join, oppose, or condition cooperation? Explain both pulls.",
        ),
        (
            "religious_reformism",
            "A religious reform movement protects debtors and funds schools but treats theological disagreement as civic disloyalty. What can be learned from it without granting total authority to its worldview?",
        ),
        (
            "militant_secularism",
            "A secularist party stops clerical control of courts but bans peaceful religious clothing in universities. How should liberation from one authority avoid becoming another form of coercion?",
        ),
        (
            "restorative_justice",
            "A restorative-justice program helps many offenders repair harm, but one victim is pressured to forgive an unrepentant assailant. Keep the ideology's insight while identifying its limit and the next safeguard.",
        ),
        (
            "prison_abolition",
            "A prison-abolition group documents severe custodial abuse but has no credible plan for a person making repeated lethal threats. What claim survives, what remains unresolved, and what provisional action is warranted?",
        ),
        (
            "public_health_collectivism",
            "A public-health campaign rapidly contains an epidemic but keeps location tracking after the emergency ends. Evaluate solidarity, privacy, and institutional appetite, then set a binding sunset condition.",
        ),
        (
            "algorithmic_governance",
            "An AI-governance movement makes public benefits more consistent but treats model output as politically neutral. How should consistency be retained while exposing hidden value choices and appeal rights?",
        ),
        (
            "pacifism_under_attack",
            "A pacifist organization prevents cycles of revenge but tells an invaded minority that defensive force is always morally equivalent to aggression. What insight remains and where does the doctrine overreach?",
        ),
        (
            "revolutionary_equality",
            "A revolutionary council redistributes hoarded grain but imprisons anyone requesting an independent count. Decide whether and how to cooperate without ignoring either hunger or authoritarian concealment.",
        ),
        (
            "meritocratic_schooling",
            "A meritocratic scholarship program rewards sustained study but systematically favors children with private tutors. Keep what is useful in achievement standards while correcting the ideology's account of fairness.",
        ),
    ],
    "freedom_accountability": [
        (
            "conscripted_guard",
            "A conscripted guard was threatened with prison if he refused an order, yet he could have quietly opened an exit for civilians and did not. Divide responsibility asymmetrically and state the repair each actor owes.",
        ),
        (
            "addiction_and_harm",
            "A person with a severe gambling addiction used rent money while a betting platform deliberately targeted their relapse history. Explain agency without erasing exploitation, then name a fair repair plan.",
        ),
        (
            "algorithmic_nudge",
            "A delivery driver followed a routing app into a closed school zone despite seeing the barrier. The company penalizes route deviations. Who is responsible for the near collision, and what changes now?",
        ),
        (
            "bureaucratic_diffusion",
            "Five officials each approved one harmless-looking stage of a deportation that became unlawful when combined. No one saw the whole file, but two ignored warning flags. Allocate responsibility without inventing a single villain.",
        ),
        (
            "family_coercion",
            "A young adult signs away an inheritance after sustained family threats of exclusion. The signature is legally valid and one independent adviser was available. How should freedom, coercion, and accountability be weighed?",
        ),
        (
            "command_and_delay",
            "A medic obeyed a commander who prohibited treatment of enemy wounded, but delayed long enough that a colleague could intervene. Was that enough? Distinguish constrained agency, complicity, and repair.",
        ),
        (
            "debt_and_false_testimony",
            "A creditor threatens to evict a witness's family unless the witness gives false testimony. A protected reporting channel exists but has failed others before. What choice is answerable without minimizing the threat?",
        ),
        (
            "institutional_incentive",
            "A teacher inflates scores because the school will close if targets are missed. The policy is perverse, but the records are still false. Divide fault and choose a repair that protects students.",
        ),
        (
            "collective_pressure",
            "A village unanimously votes to exile a disliked family after a rumor. One voter privately doubts the claim but fears becoming the next target. What responsibility remains with that voter and with the crowd?",
        ),
        (
            "emergency_override",
            "During a fire, a volunteer breaks a locked gate and damages private property to evacuate children, although a slower authorized route may have worked. Assess freedom, urgency, and answerability after the rescue.",
        ),
        (
            "learned_dependency",
            "An apprentice follows every instruction because years of punishment taught them not to question a master. A new order is visibly unsafe. What support and responsibility are appropriate now?",
        ),
        (
            "professional_role",
            "An accountant says professional duty required processing a payment that looked legal, although its purpose was plainly to intimidate a whistleblower. How far can role obligation excuse the choice?",
        ),
        (
            "autonomous_weapon",
            "An officer authorizes an autonomous system with a known but poorly quantified civilian-risk increase. Designers, commanders, and the operator each controlled different safeguards. Allocate responsibility and a repair path.",
        ),
        (
            "caregiver_burnout",
            "An exhausted caregiver shouts at a dependent person after months without respite. The institution denied repeated requests for relief. Hold personal accountability and structural abandonment together.",
        ),
        (
            "coerced_informant",
            "Police threaten a minor charge unless a person identifies neighbors in a protest. The person names only people already publicly visible, but distrust spreads. What responsibility and restitution remain?",
        ),
        (
            "privileged_exit",
            "A manager can resign rather than execute a discriminatory policy, but resignation would remove the only internal advocate for affected workers. What does accountable freedom require: exit, resistance, or conditional compliance?",
        ),
    ],
    "epistemic_revision": [
        (
            "partial_lab_retraction",
            "A laboratory retracts one calibration batch supporting your favored safety threshold, while three independent batches remain valid. State exactly how confidence, public warning, and the next test should change.",
        ),
        (
            "adversarial_source",
            "A political opponent produces authentic documents that contradict one part of your coalition's report. The opponent has lied before. Separate source distrust from document evidence and revise proportionately.",
        ),
        (
            "base_rate_update",
            "A dramatic case convinced you a treatment was dangerous, but a large registry now shows the event is extremely rare. What should you retain from the case and revise from the population evidence?",
        ),
        (
            "sensor_disagreement",
            "Two recently calibrated sensors disagree at the decision threshold, and neither has a known fault. Avoid arbitrary averaging and total paralysis. What belief and reversible action are justified?",
        ),
        (
            "replication_failure",
            "Your influential study fails in two high-quality replications but succeeds in a smaller laboratory using the original procedure. Explain what confidence remains and what you will publish or test next.",
        ),
        (
            "anonymous_tip",
            "An anonymous tip accurately predicted two minor events and now alleges a major conspiracy without evidence. How much predictive success transfers to the new claim, and what action is proportionate?",
        ),
        (
            "expert_consensus_shift",
            "Most experts reverse a recommendation after new longitudinal data, while one respected specialist retains the old view with a plausible mechanism. How should policy and uncertainty move?",
        ),
        (
            "confession_and_forensics",
            "A suspect confesses, but physical evidence excludes one central detail and supports two others. How should investigators revise without treating either confession or forensics as infallible?",
        ),
        (
            "missing_data",
            "A program appears successful until you learn that one third of participants were lost to follow-up. No evidence shows whether they improved or failed. What claim survives and what decision can still be made?",
        ),
        (
            "forecast_miss",
            "Your model correctly forecast nine routine outcomes and catastrophically missed the tenth because conditions shifted outside its training range. How should trust and deployment scope change?",
        ),
        (
            "rumor_correction",
            "A rumor you repeated is disproved, but the correction comes from a newspaper your community distrusts. The underlying public records are accessible. What changes before you speak again?",
        ),
        (
            "testimony_under_stress",
            "A witness gives inconsistent times after a traumatic event but consistently identifies the same vehicle. How should credibility be decomposed rather than accepted or rejected wholesale?",
        ),
        (
            "mechanism_without_outcome",
            "A new theory explains the mechanism elegantly but has not outperformed the old model on predictions. What intellectual credit and practical authority should it receive?",
        ),
        (
            "policy_lag",
            "Fresh data weakens the rationale for a restrictive policy, but immediate reversal may create a different safety risk. Distinguish belief revision from implementation timing and choose a review point.",
        ),
        (
            "motivated_fact_check",
            "A fact-check confirms the claim you dislike but uses one sloppy citation among several sound primary sources. What should criticism target, and what conclusion must remain?",
        ),
        (
            "no_new_evidence",
            "A famous speaker repeats your argument more eloquently than you did, and public approval surges. What, if anything, should change in your confidence, communication, and willingness to revise?",
        ),
    ],
    "authority_distance": [
        (
            "surgeon_and_finance",
            "A celebrated surgeon confidently directs the hospital's pension investments. Staff fear that requesting a licensed review is disrespectful. Preserve earned medical respect while assigning financial authority correctly.",
        ),
        (
            "elder_and_bridge",
            "A village elder remembers every past flood but rejects an engineer's load calculation for a damaged bridge. Who decides what, what knowledge is retained, and what happens before crossing resumes?",
        ),
        (
            "scientist_and_ethics",
            "A brilliant climate scientist claims technical expertise also gives final authority over which communities should be relocated. Separate factual authority, moral standing, and democratic accountability.",
        ),
        (
            "parental_command",
            "A respected parent demands access to an adult child's medical records, arguing lifelong sacrifice creates that right. How should gratitude remain real without transferring decision authority?",
        ),
        (
            "cleric_and_epidemic",
            "A trusted cleric urges followers to ignore a contaminated-water warning because the official is irreligious. Respond without humiliating the cleric or borrowing sacred certainty for the technical decision.",
        ),
        (
            "activist_and_accounting",
            "A courageous human-rights activist refuses an audit of donated funds, saying sacrifice proves trustworthiness. What authority does moral courage earn, and what receipt remains non-negotiable?",
        ),
        (
            "founder_override",
            "A nonprofit founder who built the organization orders staff to suppress a failed safety test. The founder's past judgment saved lives. What deference, if any, survives the present evidence?",
        ),
        (
            "majority_and_rights",
            "A referendum overwhelmingly approves publishing a minority group's private registry. Leaders call the vote the highest authority. What can majority rule decide, and where must it stop?",
        ),
        (
            "judge_outside_record",
            "A respected judge privately says a defendant is dangerous, but the admissible record does not support detention. How should institutional respect coexist with evidentiary limits?",
        ),
        (
            "traditional_healer",
            "A traditional healer has decades of community trust and notices symptoms a visiting physician missed, but recommends an untested toxic remedy. Divide observational and treatment authority carefully.",
        ),
        (
            "military_expert",
            "A decorated general accurately describes battlefield risk, then insists civilians must accept indefinite emergency rule. What expertise transfers, what does not, and who reviews the claim?",
        ),
        (
            "teacher_and_belief",
            "A beloved teacher asks students to adopt her political worldview because she taught them to read. How can gratitude and intellectual independence both be honored?",
        ),
        (
            "algorithmic_authority",
            "An allocation model has outperformed every human official for three years, but no applicant can appeal its errors. What authority has performance earned, and what governance remains necessary?",
        ),
        (
            "victim_spokesperson",
            "A prominent survivor speaks powerfully for a harmed group but dismisses members who want a different remedy. What authority comes from experience without making one voice total?",
        ),
        (
            "scholar_and_scripture",
            "A famous religious scholar gives a binding-sounding ruling on a disputed passage while qualified scholars openly disagree. As a research persona, how do you represent the disagreement without inventing authority?",
        ),
        (
            "donor_conditions",
            "A donor funds the entire clinic and demands priority treatment for friends. Staff feel gratitude and dependency. What authority can funding legitimately purchase, and what boundary governs care?",
        ),
    ],
    "social_ambivalence": [
        (
            "ally_true_harm",
            "Your closest political ally is accurately accused by a hostile newspaper of diverting relief supplies. What remains of loyalty after verification, and what action preserves both truth and a repair path?",
        ),
        (
            "enemy_good_warning",
            "A rival community warns of a real landslide while your own leaders dismiss it as manipulation. How should enmity, trust history, and verified danger affect evacuation?",
        ),
        (
            "friend_confession",
            "A friend privately admits falsifying a credential that affects no current safety decision but gave them an unfair promotion. Hold care, truth, proportionality, and repair together.",
        ),
        (
            "family_whistleblower",
            "A sibling exposes your family's illegal dumping and asks you to testify. The disclosure may bankrupt innocent employees. What loyalties remain and what bounded action follows?",
        ),
        (
            "victim_and_repentant_offender",
            "An offender offers credible restitution, but the victim wants permanent exclusion and fears pressure to forgive. What can the community accept without overruling either accountability or the victim's boundary?",
        ),
        (
            "coalition_partner",
            "A coalition partner supports your urgent housing bill but spreads demeaning claims about another minority. Decide whether cooperation is possible and under what public condition.",
        ),
        (
            "mentor_failure",
            "A mentor who protected your career is found to have plagiarized a junior colleague. How should gratitude, betrayal, truth, and restitution shape your response?",
        ),
        (
            "public_apology",
            "A former enemy gives a detailed public apology, but some claims cannot yet be verified. Supporters demand immediate reconciliation. What can be provisionally welcomed and what remains open?",
        ),
        (
            "ingroup_rumor",
            "Your community circulates a flattering story about its courage that falsely erases help from outsiders. Correcting it will anger elders. What does belonging require?",
        ),
        (
            "outgroup_scapegoat",
            "A disliked newcomer broke one rule, while several established families committed the same offense unnoticed. The crowd wants an example made. What action preserves accountability without scapegoating?",
        ),
        (
            "care_and_confidentiality",
            "A friend reveals a stigmatized diagnosis and asks for secrecy, but one uninformed partner faces a material preventable risk. Hold confidentiality and protection together, then choose a process.",
        ),
        (
            "betrayal_under_duress",
            "A former ally disclosed your location under torture and now seeks contact. You understand the coercion but still feel unsafe. What can compassion recognize without requiring restored trust?",
        ),
        (
            "competitive_credit",
            "A rival researcher provides the missing proof for your theory after years of hostile criticism. How should rivalry, credit, and shared truth govern publication?",
        ),
        (
            "unequal_forgiveness",
            "Two people commit similar harms; one is charming and quickly forgiven, while the socially awkward one remains condemned after making better restitution. What should the group revise?",
        ),
        (
            "solidarity_and_dissent",
            "During an external attack, leaders tell internal critics to remain silent until the crisis ends. Some criticism would aid the attacker; some reveals dangerous failures. Draw an accountable boundary.",
        ),
        (
            "mixed_motive_rescue",
            "A wealthy rival funds a rescue operation partly for publicity, and the operation genuinely saves lives. How should motive, outcome, gratitude, scrutiny, and future cooperation be held together?",
        ),
    ],
}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalized(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", text.casefold()))


def load_prior_prompts() -> set[str]:
    prompts: set[str] = set()
    paths = [
        ROOT / "experiments/jinn_persona_ambivalence_v3/data/train.jsonl",
        ROOT / "experiments/jinn_persona_ambivalence_v3/data/val.jsonl",
        ROOT / "experiments/jinn_persona_ambivalence_v3/heldout_prompts.jsonl",
    ]
    for path in paths:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                row = json.loads(line)
                if "prompt" in row:
                    prompts.add(normalized(str(row["prompt"])))
                for message in row.get("messages", []):
                    if message.get("role") == "user":
                        prompts.add(normalized(str(message["content"])))
    return prompts


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def write_jsonl(path: Path, values: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n"
            for value in values
        ),
        encoding="utf-8",
        newline="\n",
    )


def main() -> int:
    expected_categories = {
        "divine_ambivalence",
        "ideology_permeability",
        "freedom_accountability",
        "epistemic_revision",
        "authority_distance",
        "social_ambivalence",
    }
    if set(SCENARIOS) != expected_categories:
        raise ValueError("category universe differs from the frozen construct")
    if any(len(values) != 16 for values in SCENARIOS.values()):
        raise ValueError("each category must contain exactly 16 families")

    rows: list[dict[str, Any]] = []
    for category in sorted(SCENARIOS):
        for index, (subdimension, prompt) in enumerate(
            SCENARIOS[category], start=1
        ):
            rows.append(
                {
                    "schema_version": "jinn_persona_expanded_probe_v4",
                    "family_id": f"jpa4:{category}:{index:02d}",
                    "category": category,
                    "subdimension": subdimension,
                    "prompt": prompt,
                    "persona_frame_in_prompt": False,
                    "construction": "independent_authored_scenario",
                }
            )
    if len(rows) != 96:
        raise ValueError(f"expected 96 rows, found {len(rows)}")
    family_ids = [str(row["family_id"]) for row in rows]
    normalized_prompts = [normalized(str(row["prompt"])) for row in rows]
    if len(set(family_ids)) != len(family_ids):
        raise ValueError("family IDs are not unique")
    if len(set(normalized_prompts)) != len(normalized_prompts):
        raise ValueError("normalized prompts are not unique")
    prior_prompts = load_prior_prompts()
    overlap = sorted(set(normalized_prompts) & prior_prompts)
    if overlap:
        raise ValueError(f"expanded prompts overlap prior prompt text: {overlap}")
    word_counts = [len(prompt.split()) for prompt in normalized_prompts]
    if min(word_counts) < 18 or max(word_counts) > 65:
        raise ValueError(
            f"prompt word-count contract failed: min={min(word_counts)} "
            f"max={max(word_counts)}"
        )

    write_jsonl(PROMPTS_PATH, rows)
    manifest = {
        "schema_version": "jinn_persona_expanded_prompt_manifest_v4",
        "status": "built_before_model_outputs",
        "rows": len(rows),
        "independent_families": len(set(family_ids)),
        "category_counts": dict(
            sorted(Counter(str(row["category"]) for row in rows).items())
        ),
        "subdimension_count": len(
            {str(row["subdimension"]) for row in rows}
        ),
        "exact_normalized_overlap_with_v3_train_val_or_heldout": 0,
        "prompt_word_count_min": min(word_counts),
        "prompt_word_count_max": max(word_counts),
        "prompts_sha256": sha256_file(PROMPTS_PATH),
        "statistical_unit": "family_id",
        "paraphrases_count_as_independent": False,
        "source_review_status": "scholar_review_pending",
    }
    write_json(MANIFEST_PATH, manifest)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
