# MS03B — Color War: review note

**Closed phase: successful competitive-color concept proof, accepted by owner
decision as the basis for the spectator micro-game pivot. Freeze exactly as
delivered. Do not polish, overwrite, regenerate, or produce a 1080p master.**

No existing output is approved as a published asset. No 1080p MS03B master was
produced or requested. The implementation and all artifacts are frozen experimental
infrastructure. The descriptions, review questions, and commands below are
historical records, not permission to run them. See [the current register](EXPERIMENTS.md).

The video contains geometry and color only: no headline, rule text, counters,
score, labels, instructions, or captions. Both teams begin moving immediately
among 40 stationary ivory beads. Separate first conversions at 0.800 and 1.800 s
are intended to teach contact-based recruitment visually. Early populations stay
approximately balanced. Opponent captures begin after neutral recruitment ends.

## Timing and outcome spoilers

| Beat | Authored result |
| --- | --- |
| 0–3 s | One neutral conversion per side; each team has two moving beads by 1.8 s. |
| 3–8 s | Separated repetitions bring each side to five movers. |
| 8–16 s | Recruitment accelerates; the field reaches 21 cyan / 21 orange with no neutrals left. |
| 16.12–17.20 s | Cyan captures create a 26 / 16 advantage. |
| 17.46–19.02 s | Orange counterattacks reverse control to 14 cyan / 28 orange. |
| 19.16–21.06 s | Cyan reverses control again, reaching 34 cyan / 8 orange. |
| 21.23–23.18 s | The threatened orange team produces an accelerating 34-capture comeback. The populations return to parity around 22.2 s before orange takes the field. |
| 23.18–23.90 s | All 42 beads and the arena border are orange. Motion continues during the short victorious color hold. |
| 23.90–24 s | Reset to the two-mover, neutral-field opening state. |

Non-frame-aligned contact times are rounded upward to the 120 Hz choreography
step; exact realized times and counts are in `outputs/ms03b/ms03b-events.json`.
The comeback is conveyed by actual local color changes and new attackers, not
by a decorative full-field flash. A faster incoming attacker and briefly slowed
victim are intended to make capture direction readable.

This is a deterministic, **authored contest**, not an unbiased stochastic match.
The winner and contact schedule are choreographed; the research question is
whether a first-time viewer experiences uncertainty and follows the reversals.
Colors persist between pictured contacts. Guided paths avoid unsignaled opponent
overlaps. Source/target contact distances and state changes are checked, but
perceived causality and surprise require the human viewing.

Cyan uses a bright upper-register note family; orange uses related lower,
warmer notes. Captures add a stronger transient than neutral recruitment. The
decisive sequence accelerates, then resolves in the winning team's timbre.
There is no speech or ambient music bed.

Review delivery is native 720×1280, 30 FPS, with a 2× antialiased working canvas,
solid saturated fills, six-pixel bead edges, a nine-pixel arena border, explicit
BT.709 conversion/metadata, and an 8 Mb/s H.264 target. The tall hexagonal arena
spans about 94% of frame width and 76% of frame height. Beads are 42 pixels across.

## Historical review questions

After one unexplained normal-speed viewing, record each person's response:
can they infer contact-based spreading, spontaneously favor a side, notice a
lead change, remain unsure of the winner until late, understand the cascade,
identify the winner immediately, and describe the image as vivid? At least one
should want a replay to inspect the turning point. These were the original
questions. The owner has subsequently accepted the concept proof; no individual
survey answers are invented. That decision does not authorize a master or publication.

Historical command record — do not execute:

```bash
.venv/bin/python -m inception.ms03b --config configs/ms03b.toml
```

The original command's overwrite capability must not be used. The primary sound
and muted MP4s, spoiler contact sheet, WAV mix, and event log under `outputs/ms03b/`
are frozen exactly as delivered. No regeneration or master is authorized.
