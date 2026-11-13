# Procedural spectator-format roadmap

**Owner-approved direction:** a pipeline of internally consistent procedural
spectator formats, not exclusively a Chain Reaction generator. MS04.4 remains
the first genuine rules-format proof. MS06 — Pressure Multiplication is the
second proposed format, exploring compression, limited space, and ball
multiplication with an original stylized identity. This direction does not
approve a new master, publication, or changes to an existing output.

**Current authorization:** MS06 objectives, rule questions, milestone boundaries,
and acceptance criteria only. No simulation, rendering, generated outputs,
dependency installation, or generalized plugin framework. Owner approval of the
MS06.1 rule objectives is required before MS06.2. See [MS06](MS06.md).

MS04.1 through MS04.3 are owner-approved foundations. MS04.4 has produced the
first genuine-match end-to-end review and awaits normal-speed owner-and-wife
phone judgment. This checkout includes only the MS04.1 topology needed by the
later milestones, not its standalone static renderer or output package. The
working game name and visual identity remain undecided; Chain Reaction is an
inspiration for psychological strengths, not branding or assets to copy.

## MS04.1 — Grid construction

Evaluate a canonical **6-column × 9-row** portrait rectangular board. Establish
cell coordinates, orthogonal adjacency, and corner/edge/interior classification.
Explore phone-safe composition and readable zero-to-three-orb cell states.
No gameplay automation belongs in this milestone.

**Owner-approved foundation:** immutable topology is available in `inception.grid`
as an MS04.4 dependency. The standalone MS04.1 static review remains outside the
current transfer.

## MS04.2 — Rules engine

Keep pure game-state logic independent of rendering and audio. Support legal
placement into an empty or owned cell and configurable two-to-eight competitors.
Use critical mass equal to neighbor count: corner 2, edge 3, interior 4. Explosions
distribute to orthogonal neighbors and convert ownership. Resolve cascades
deterministically and define elimination/victory explicitly.

Before implementing, decide and test:

- Excess orbs: repeated threshold subtraction versus another documented policy;
  never silently discard orbs without an explicit rule.
- Cascade ordering: stable queue/neighbor order versus simultaneous waves; define
  ownership and event order when several sources reach the same cell.
- Elimination protection: when a player becomes eligible for elimination, including
  the initial rounds and players who have not placed yet.
- Victory timing: settle a cascade before deciding the winner; define terminal
  ownership semantics and treatment of eliminated turns.
- Pathological non-termination: detect repeated states or enforce an explicit
  deterministic limit/outcome. A truncated cascade must not be disguised as victory.

**Owner-approved:** these decisions are explicit and implemented in a pure,
immutable rules engine with focused conformance scenarios. There is no rendering,
audio timing, or move policy in this layer. See [MS04.2](MS04.2.md).

## MS04.3 — Automated gameplay

Add deterministic move selection with configurable player policies, offline
match simulation, reproducible seeds, and complete event logs. Score candidate
matches for allegiance, lead changes, threatened elimination, cascade strength,
comeback quality, and late uncertainty. These are selection proxies requiring
human validation. Select compelling **genuine matches**, not fabricated winners.
No agent framework, LLM, or cloud infrastructure is implied.

**Owner-approved:** deterministic random and bounded tactical policies, seeded
offline simulation, complete logs, transparent scoring, and genuine-result
selection are implemented. The first 12 three-team candidates produced three
winners and nine explicit cascade-step-limit draws; seed 4304 is the selected
genuine winner. The high draw-rate product/rule decision remains open. See
[MS04.3](MS04.3.md).

## MS04.4 — End-to-end attention test

Render the vertical game using event-driven animation and the shared absolute
presentation clock. Review on a phone, with clean outputs without explanatory
UI and a winner readable through board state and color. Evaluate TikTok-compatible
safe areas and encoding. Human validation precedes any publishing master;
no publishing integration is authorized.

**Technically complete; creative gate open:** the 39.80-second 720×1280 review
presents the genuine seed 4304 match, integrates the MS05 sound contract, starts
the first placement at 0.035 seconds, and reveals all three teams by 0.675 seconds.
The copied review videos retain their recorded hashes; no regeneration or 1080p
master was needed. See [MS04.4](MS04.4.md).

## MS05 — Separate procedural audio foundation

Use immutable semantic events, related team identities, absolute event times,
and sample-based synthesis. The initial two-team fixture exercises placements,
charge/critical cues, explosions, a multi-step cascade, capture reversal,
elimination, and resolution. It establishes an audio contract for MS04; it does
not implement any milestone above. See [MS05](MS05.md).

## MS06.1 — Format and rule specification

Define the chamber/safe areas, approaching compression boundary, pressure proxy,
identity semantics, multiplication trigger/transformation, space and collision
handling, population bounds, reversal mechanism, and explicit terminal/draw
outcomes. Recommend one small rule card and hand-worked traces, not a simulator.
The opening promises visible danger immediately, meaningful compression by about
0.5 s, and multiplication or a major state change by about 1.5 s. Owner approval
of this specification gates implementation; no implementation belongs here.

## MS06.2 — Deterministic simulation

After MS06.1 approval, implement seeded reproducible rules and immutable semantic
event logs, genuine outcomes, and explicit failure/draw states. Neither rendering
nor audio may influence truth. This is planned and is not authorized by the
current documentation turn.

## MS06.3 — Visual and sound prototype

Plan one 12–20-second, phone-safe vertical prototype: already-populated chamber,
approaching boundary, two or three legible identities, escalating compression,
readable multiplication, and a decisive genuine ending. Keep explanatory text,
score counters, narration, captions, and music integration out of the generated
video. Validate at normal speed on a phone before polish or a master.

## MS06.4 — Batch generation and selection

Generate genuine deterministic candidates from different seeds and controlled
parameters. Transparently score first-transformation timing, occupied-space
pressure, multiplication escalation, reversal/threatened failure, color balance
and changing dominance, peak event intensity, late uncertainty, and terminal
clarity. Preserve failures/draws and true outcomes. These are engineering proxies,
not proof of audience satisfaction or permission to fabricate a better ending.

## MS06.5 — Format-family compatibility

Only after the second format exists and is creatively accepted, compare the
MS04 Chain Reaction-inspired rules format with Pressure Multiplication. Assess
actual common needs around seeds, event identity, absolute timing, rendering/
export contracts, audio cues, manifests, and review gates. Extract only what is
demonstrably shared. Do not design a general plugin system before this comparison.
