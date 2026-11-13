# Operation Inception engineering guide

The active direction is deterministic spectator micro-games for vertical social
video. Game logic, rendering, and audio are independent concerns. Do not claim
physical realism or infer audience engagement from technical checks.

## Frozen particle phase

Experiment 001 and 001B were creatively rejected. MS03 made meaningful progress
but was rejected. MS03B is the successful competitive-color concept proof that
closes the particle phase and motivates the pivot. No existing output is approved
for publication. No 1080p MS03B master was produced or requested.

- Preserve every existing output byte-for-byte. The freeze inventory is
  `docs/archive/particle-phase-freeze-v1.json`.
- Do not polish, regenerate, overwrite, or master MS03B. Do not delete or refactor
  the legacy particle implementations or configurations listed in the inventory.
- Existing particle modules are frozen experimental infrastructure, not the active
  product. Historical reproduction commands are records, not authorization to run.
- Do not rewrite Git history. Inspect status and applicable instructions before work.
- Keep generated outputs and caches out of Git; record hashes when closing work.

## Active engineering rules

- Research questions justify scope. Prefer a small working slice and focused changes.
- MS04 game rules must be pure state logic, independent of rendering and sound.
  Do not fabricate a match winner in the future automated game product.
- MS05 consumes an immutable timed event log after offline simulation. It must not
  import game engines, renderers, video tools, or use FPS as an audio clock.
- MS04.4 may adapt an approved immutable match to timing, rendering, and the MS05
  sound contract. Its renderer must not select moves, call the rules engine, or
  change the winner. Keep one absolute clock for visual and sound events.
- Preserve seed/event reproducibility; put meaningful controls in explicit inputs.
- Add focused behavioural checks. Technical success is separate from normal-speed
  phone creative acceptance.
- Do not add speech, narration, voiceover, music, LLMs, Hugging Face models, or
  other generative models to MS05. The planned social hook stays outside both
  rendering and audio pipelines and may be recorded later in TikTok Studio.
- No publishing integrations, TikTok APIs, cloud services, dashboards, or agents.
- Do not copy Chain Reaction branding, interface assets, audio, or visual design.

Read `docs/VISION.md`, `docs/ROADMAP.md`, `docs/MS04.2.md`, `docs/MS04.3.md`,
`docs/MS04.4.md`, and `docs/MS05.md`. The owner-approved MS04 grid topology,
rules, and seeded genuine-match selection are dependencies of the transferred
MS04.4 presentation. Preserve unfinished/draw outcomes and never rewrite a winner.
The standalone MS04.1 static renderer and review package are outside this transfer.
The initial audio fixture is synthetic and is not a genuine game or rules oracle.

## Verification

```bash
.venv/bin/python -m pytest -q tests/test_ms05_audio.py
.venv/bin/python -m pytest -q tests/test_ms04_2.py
.venv/bin/python -m pytest -q tests/test_ms04_3.py
.venv/bin/python -m pytest -q tests/test_ms04_4.py
.venv/bin/python tools/verify_particle_freeze.py
```

Archived tests may run in temporary workspaces; they must not replace frozen
artifacts. Never run an archived render command as a routine verification step.
