# Procedural spectator-format roadmap

**Owner-approved direction:** a pipeline of internally consistent procedural
spectator formats, not exclusively a Chain Reaction generator. MS04.4 remains
the first genuine rules-format proof. MS06 — **Pressure Bloom** is the
second format concept, exploring compression, limited space, and ball
multiplication with an original stylized identity. This direction does not
approve a new master, publication, or changes to an existing output.

**Current authorization:** the PO closed MS06.3C and retired PB-1.x as the production
candidate. No further PB-1.x scenario or geometry tuning is allowed. One bounded
[MS06.3D](MS06.3D.md) PB-2.0 capacity-based prototype is authorized, gated by rule
conformance, scenario acceptance, eight deterministic probes and layout success
before rendering. PB-1.1/PB-1.2 research and all artifacts remain preserved.
MS06.4 batch production, publication and 1080p mastering remain unauthorized.

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

**Owner-approved PB-1.1 rule card.** Pressure Bloom asks “How many will they
become before the chamber breaks?” It uses a populated transparent chamber,
descending piston and persistent lineages; no grid or color capture. Compression
begins by about .5 s, first meaningful split by about 1.5 s; target 14–18 s.
The revised [rule card](MS06.md) replaces PB-1.0's inconsistent drive/timing and
tangent births with genuine travel and deterministic relaxation. Thresholds remain
.30 s moderate split, .15 s extreme crush, .40 s wall rupture, generation 3/cap 96.

## MS06.2 — Deterministic simulation

**Authorized and implemented for technical review.** Pure 120 Hz state logic
records C/D/contact weight/L, immutable events and tick states, stable latched
crush → rupture → split transitions, .60 s genuine release, bounds and explicit
outcomes. The versioned conformance record covers the three revised traces and
focused containment/extinction/cap/generation/draw/invalid/late-result scenarios.
Neither rendering nor sound influences truth. See [MS06.2](MS06.2.md).

## MS06.3 — Visual and sound prototype

**Technically valid; owner creatively rejected for use.** The original
15.066667-second containment cut and all MS06.3 artifacts remain byte-identical.
Its frozen records retain the historical review-pending status; the subsequent
owner decision is recorded here. See [MS06.3](MS06.3.md) for the preserved technical
record. Do not polish or overwrite that cut.

### MS06.3B — Focused whole-bed rupture revision

**Closed — blocked by PB-1.1 pressure reachability; no creative review artifact
produced.** Three directed setups drew; one contained after 11 splits and 8 crushes.
No setup ruptured or escaped; no successful base existed for the eight-probe audit.
No review video, image or audio was produced. The render gate worked correctly.
The saved report records one sub-rupture wall-strain event in setup A; setup C
had none. Preserve that evidence rather than claiming no strain in any setup.
Exact outcomes, limited lower-cohort activity and the distinction between evidence
and inference are in [MS06.3B](MS06.3B.md); hashes are in the
[closure inventory](archive/ms06.3b-closure-v1.json). No further PB-1.1 geometry
tuning is authorized.

### MS06.2B — PB-1.2 Pressure Reachability (simulation-only reachability)

**PO-approved; simulation-only implementation technically complete.** A narrow
PB-1.2 module reuses the untouched PB-1.1 kernel and implements derived compression
debt, bounded piston catch-up, deterministic pre-settling and auditable side-wall
contributions. The complete reachability matrix includes genuine L0 rupture and
eight escapes, separate containment, jam/crush release, draw and invalid results.
The same-tick crush/rupture proof retains its latched wall failure. All 14 PB-1.2
scenarios replay byte-identically, and all 16 PB-1.1 result records reproduce in
memory without overwriting outputs. Thirteen focused and 109 full-suite tests pass.
See [MS06.2B](MS06.2B.md). Whole-bed prototype authoring, rendering/audio integration,
creative validation and MS06.4 remain separate PO gates; no media was generated.

### MS06.3C — First PB-1.2 directed rupture prototype

**Closed before rendering by PO decision.** A 36-ball gravity-settled base
reached a finite-packing-stall draw at 4.066667 seconds after 19 splits, with no
crush, rupture or escape. Whole-bed load improved, but twelve simultaneous first
splits and the unresolved-overlap duration failed the teaching/numerical gates.
The eight nearby probes were not run because no qualifying base existed. No
video, image or audio was produced; the unchanged PB-1.2 reachability proofs and
all historical artifacts are preserved. See [MS06.3C](MS06.3C.md) and its logical
failed-gate report and [closure inventory](archive/ms06.3c-closure-v1.json).
PB-1.2 is valid research but PB-1.x is retired for production; no tuning is allowed.

### MS06.3D — PB-2.0 capacity prototype

**PO-authorized staged execution.** Pressure derives from occupied area / effective
capacity. Seeded lineage-neutral resistance and global split/crush cadences replace
contact-based qualification. Four logical wall sections sustain auditable overload;
rules determine rupture and discharge. Independent deterministic layout may fail
presentation but cannot change truth. Freeze conformance constants before scenario
authoring; stop on a failed scenario, robustness or layout gate. See
[MS06.3D](MS06.3D.md). Technical success never substitutes for phone review.

## MS06.4 — Batch generation and selection

Generate genuine deterministic candidates from different seeds and controlled
parameters. Transparently score first-transformation timing, occupied-space
pressure, multiplication escalation, reversal/threatened failure, color balance
and growth/loss, peak event intensity, late uncertainty, and terminal
clarity. Preserve failures/draws and true outcomes. These are engineering proxies,
not proof of audience satisfaction or permission to fabricate a better ending.

## MS06.5 — Format-family compatibility

Only after the second format exists and is creatively accepted, compare the
MS04 Chain Reaction-inspired rules format with Pressure Bloom. Assess
actual common needs around seeds, event identity, absolute timing, rendering/
export contracts, audio cues, manifests, and review gates. Extract only what is
demonstrably shared. Do not design a general plugin system before this comparison.
