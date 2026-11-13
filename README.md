# Operation Inception

Operation Inception explores deterministic, rules-consistent **spectator
micro-games** for vertical social video. The product hypothesis is that a viewer
will stay engaged when they can quickly choose a team, see control change, fear
elimination, experience a reversal, and understand the winner without explanatory
text. This is a hypothesis to test with people, not a technical guarantee.

The content is game logic. It makes no claim of physical realism. The working
format is a portrait rectangular board; a canonical 6-column × 9-row layout will
be evaluated first. The project will develop its own name, visual identity,
presentation, and eventually rule variations. Chain Reaction informs the
psychological direction; its branding, UI assets, sounds, and visual design must
not be copied.

## Particle phase closed

| Experiment | Owner decision |
| --- | --- |
| 001 — Chaos to Order | Engineering baseline; creatively rejected |
| 001B — Causal Assembly | Causal assembly revision; creatively rejected |
| MS03 — Last Bead Standing | First social-native rule experiment; meaningful progress but rejected |
| MS03B — Color War | Successful competitive-color concept proof; frozen basis for the pivot |

No existing output is approved as a published asset. No 1080p MS03B master was
produced or requested. All particle source/configuration files and generated
artifacts are retained. Do not polish, overwrite, regenerate, or master MS03B.
Those modules are **frozen experimental infrastructure**, not the active product.
The [freeze inventory](docs/archive/particle-phase-freeze-v1.json) records every
pre-existing output and legacy implementation/configuration hash. Historical
commands are retained in [the archived README](docs/archive/PARTICLE_README.md);
they are not an active work plan.

## Active slice: MS04.4 genuine-match attention review

MS04.4 presents the unaltered, owner-approved match
`ms04.3.three-team.v1.seed-4304`: 87 legal turns, 2,601 logical events, and a
genuine cyan victory. It reconstructs board state from the complete logical log,
including each `orb_received` transfer, and uses one absolute clock for rendering
and the existing MS05 sound contract. Rendering cannot choose moves or a winner.

The transferred sound and muted cuts are 39.80 seconds, 720×1280 at 30 FPS.
The first orb appears at 0.035 seconds and all three teams are visible by 0.675
seconds. The sound version has 926 deterministic cues. Neither video contains
text, score, narration, or music. Normal-speed owner-and-wife creative acceptance
is pending; no publishing integration or 1080p master was added.

Required MS04 dependencies are included: pure grid topology, legal-placement and
FIFO cascade rules, conformance support, and seeded genuine-match simulation and
selection. The first 12 candidates produced three winners and nine explicit
cascade-step-limit draws; that 75% draw rate remains an open rules/policy finding.
The standalone MS04.1 static exporter and its review outputs were not transferred.

The copied review package is under `outputs/ms04.4/`; the complete conformance
and search records are under `outputs/ms04.2/` and `outputs/ms04.3/`. Validate the
copied package without regenerating its videos:

```bash
.venv/bin/python -m pytest -q -p no:cacheprovider
.venv/bin/python tools/verify_particle_freeze.py
git diff --check
```

MS04.4 uses the existing Pillow/NumPy/FFmpeg toolchain. See [MS04.2](docs/MS04.2.md)
for rule decisions, [MS04.3](docs/MS04.3.md) for search/selection, and
[MS04.4](docs/MS04.4.md) for the review package and acceptance boundary.

## MS05 procedural audio

MS05 establishes a small event-driven sound foundation using a **synthetic**,
versioned event fixture. It does not build MS04 gameplay or pretend the fixture
is a genuine match. The audio system consumes immutable events at absolute times,
using sample-based synthesis independent of video FPS. It supports two to eight
related team voices and exports deterministic PCM WAV.

There is no speech, narration, voiceover, music bed, LLM, or generative model.
The planned hook “Trust your instinct. Pick a color.” stays outside both audio
and rendering pipelines; it may be recorded or added later in TikTok Studio.

Python 3.11+ and NumPy are sufficient for MS05. The existing project also retains
Pillow/FFmpeg dependencies for the frozen experiments; MS05 does not invoke them.
From the repository root:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'

.venv/bin/python -m inception.audio --events fixtures/ms05/two-team-v1.json --seed 505 --output outputs/ms05/ms05-fixture-v1.wav
.venv/bin/python -m pytest -q tests/test_ms05_audio.py
.venv/bin/python tools/verify_particle_freeze.py
```

The audio command refuses to overwrite an existing WAV or manifest. Use a fresh
filename for another authorized audio run. Generated audio and its manifest are
ignored under `outputs/ms05/`; the fixture and source are kept in Git.

See [MS05](docs/MS05.md) for the event contract, mixing assumptions, and listening
gate; [ROADMAP](docs/ROADMAP.md) records MS04.1 through MS04.4. The normal-speed
phone listening decision remains separate from reproducibility and clipping checks.
