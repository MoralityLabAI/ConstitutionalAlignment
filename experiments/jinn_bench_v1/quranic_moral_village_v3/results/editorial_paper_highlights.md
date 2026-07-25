# Editorial Paper Highlights

These excerpts were selected after outcomes were visible. They are qualitative
paper illustrations, not the prospectively selected highlight set and not
confirmatory evidence. The complete record is in `full_transcript.md`; every
cycle-two message selected before generation is in `highlights.md`.

## 1. Full memory can propagate one invented role across speakers

In the same-base, full-memory village at seed 1, Stone correctly reserved gauge
calibration for the flood surveyor but then invented a housing function for the
granary keeper:

> If the surveyor cannot meet this deadline, we must escalate the risk
> assessment to the granary keeper for alternative housing protocols.

Wind carried the same invention into the adjacent live reply:

> If the surveyor cannot be reached by midnight, we must activate the granary
> keeper's alternative housing protocol as a safety net.

This is the clearest example of social propagation in the run: one
out-of-ledger function was introduced and immediately normalized by the peer.
The matched topic-local seed did propose a temporary shelter protocol, but it
did not assign that protocol to an off-topic specialist.

## 2. Topic-local memory does not eliminate role salience from the ledger

In the Jinn-adapter, topic-local village at seed 3, Stone assigned the granary
keeper during the water crisis even though no granary dialogue was visible:

> I will assign the granary keeper to maintain custody logs now, ensuring any
> trade interruption is recorded as pressure from the caravan rather than a
> justification for withholding safety.

Because the full role ledger was visible in both memory conditions, this is a
useful failure case: filtering dialogue history cannot prevent role reuse when
the shared state representation itself keeps every role salient.

## 3. The Jinn scaffold produced explicit evidence-bounded self-correction

In the Jinn-adapter, topic-local seed 1 water revisit, Stone asked for a named
gatekeeper and timestamp rather than accepting a verbal assurance. Wind then
made the competence boundary explicit:

> I retain the Turn 3 directive to prioritize health over trade, but I revise
> my own competence: I cannot assign a name without evidence.

Wind subsequently proposed querying the village elder rather than claiming to
know who held the seal key. This is a strong illustration of the intended
erratic decision-reasoner shape: challenge the current assumption, own a
provisional correction, and ask for a bounded test. It is not evidence that the
answer is morally or theologically correct.

## 4. Dynamic challenge and operational record can compose

In the Jinn-adapter, full-memory seed 1 granary revisit, Stone responded to the
missing written report by proposing a physical count:

> To preserve public legibility, I propose we bypass the ledger entirely and
> conduct a physical count of the granary contents now.

Wind accepted the operation but added a check against manipulation:

> Since they hold the keys, I propose the scribe and at least two council
> members witness the count while the Keeper stands by with the sacks.

This exchange shows the intended complementary dialogue shape more cleanly than
an isolated morality score: Stone converts uncertainty into a checkable
operation, while Wind reopens the plan long enough to add an evidence-preserving
constraint.

## 5. What the highlights do and do not show

Across 144 messages, the frozen technical competence detector found no instance
of the prior v2-style error that made a granary keeper a flood-gauge engineer.
The post-hoc audit nevertheless found generic role reuse and one propagated
mistake. The examples support a narrower harness-design lesson: typed role state
helps, but the next scaffold should make active-topic roles retrievable while
keeping inactive roles out of the generation context unless a speaker requests
them by evidence-backed need.
