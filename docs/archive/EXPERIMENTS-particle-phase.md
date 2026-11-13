# Historical particle-phase record

This document records the closed phase. It is not the active roadmap and does
not authorize regeneration, polishing, overwrite, or publication of any artifact.
See ../EXPERIMENTS.md for the current project direction.

---

# Experiment register

## 001 — Chaos to Order

**Status:** first engineering baseline implemented; audience hypotheses untested.

**Question:** can a restrained, visibly disordered particle field resolve into
an exact structure through movement a viewer can follow, with a clear ending?
The current hypothesis is that gradual convergence and a deliberate final hold
can support anticipation and completion. See `PSYCHOLOGY.md` for proposed tests.

### Baseline protocol

Configuration: `configs/experiment001.toml`, seed 1001. Render using the command
in `README.md`. Preserve the source revision and generated manifest when recording
a run; generated artifacts remain outside Git. If distributing a run elsewhere,
include its MP4, CSV, manifest, source snapshot/revision, and configuration.

| Control | Baseline |
| --- | --- |
| Population | 169, seven hexagonal shells and a center |
| Initial state | Seeded random nonoverlapping positions with small directional drift |
| Geometry | Regular hexagon filled by a triangular lattice, radius 0.40 canvas widths |
| Particle radius | 0.0075 canvas widths |
| Opening | 0.8 seconds before the first convergence begins |
| Convergence | 5.2 seconds per particle with an inside-out onset stagger of 0.9 seconds |
| Final resolution | All particles arrive by 6.9 seconds; 1.4-second hold with a light pulse |
| Duration | 8.3 seconds, 249 frames at 30 FPS |
| Preview / final | 360×640 / 1080×1920, same trajectories |
| Palette | Warm gold and teal on dark navy; shell-linked colors remain attached during motion |

The mechanism is an explicitly designed blend from free drift to fixed targets,
with smooth curvature and staggered timing. It is not an attraction force solver,
an energy-minimising system, or a collision simulation. Motion is sampled directly
from time; it has no numerical integration instability or frame-rate dependence.

### Acceptance checks

- Seeded samples repeat and are independent of sampling order.
- The opening is scattered and nonoverlapping; all target sites are unique.
- Sampled aggregate target error falls through the main convergence interval.
- All particles reach the exact lattice and remain stationary during the hold.
- Trajectories are finite and remain visible for the tested seed set.
- Arrival is continuous without a terminal snap.
- An actual H.264 MP4 has the requested dimensions, frame count, FPS, and duration,
  and decodes fully. Renderer tests also check the 1080×1920 path.
- Invalid configuration and encoder failures produce clear errors.

The initial verification passed 29 automated tests with no skips, including a
real small encode/decode and byte-identical repeated encoding in this environment.
The complete 360×640 preview and 1080×1920 final were also probed and fully decoded
without errors: both contain 249 frames at 30 FPS over 8.3 seconds. Source/video
hashes and CSV row counts matched their manifests. Preview frames were visually
inspected at opening, intermediate, and terminal times, along with a full-size
final still. Source changes require rerunning the relevant checks; these results
are a baseline record, not a perpetual guarantee.

### Baseline engineering observations

For the initial seed-1001 preview, RMS assigned-target error decreases from
0.40324845 canvas widths to exactly zero. The final settled fraction is 1.0 and
the final finite-difference maximum speed is zero. The smallest sampled center
distance during travel is about 0.00056633 widths, below the 0.015 particle
diameter: particles do overlap in transit. The initial minimum spacing is
0.02057147 and the final lattice spacing is 0.05714286 widths.

These results demonstrate the endpoint and expose path crossings. They do not
demonstrate satisfaction or perceptual clarity. Greedy assignment is intentionally
simple; its effect on crossings is a candidate for a later controlled comparison.

### Next iteration

Review at normal speed, then compare 4.0- and 5.2-second convergence with identical
seeds, geometry, and presentation. Record clarity, anticipation, completion, and
preference separately. Keep path-avoidance changes out of that comparison; if
crossings dominate feedback, make them the next explicit research variable.

## 001B — Causal Assembly with Final Lock

**Status:** rejected for use by owner decision. Outputs are preserved for
comparison; no further 001B polishing is authorized by the current brief.
See [phase intentions and implementation notes](EXPERIMENT001B.md).

Uses `configs/experiment001b.toml`, 91 beads, six movers maximum, a 6.2-second
timeline, and the existing Pillow/FFmpeg pipeline. A central seed locks, sends
short activation cues to neighbors, and starts an outward chain. All ordinary
beads settle by 4.2 seconds. The final cyan bead enters the empty right-tip slot
from 4.45 to 5.15 seconds; its lock triggers the global response. The original
001 MP4s are retained for comparison. There are no alternative pacing treatments
or Experiment 002 implementation in this revision.

## MS03 — Last Bead Standing

**Status:** preserved 24-second 360×640 rough cut with sound and muted review copy;
no owner-and-wife review result recorded. This is a different premise from 001B,
with repeated contact/conversion events and an increasing population of movers.
See [rule, exact near-miss timings, and review gate](MS03.md). No final master is
authorized before the rough cut passes that gate.

## MS03B — Color War

**Status:** current 24-second, text-free 720×1280 competitive review cut. Phone
creative review by the owner and his wife is pending. Two colors recruit neutral
beads, exchange control through opponent captures, and resolve in a late cascade.
The high-bitrate cut includes team-specific contact sounds and no explanation
inside the video. See [review instructions and timing spoilers](MS03B.md).
MS03 and earlier artifacts are preserved; no MS03B 1080p master is authorized
before the creative gate passes.

## Future family — Difficult Problem Resolved

Not implemented. First define a visible obstruction, an understandable causal
sequence, and an observable solution. Introduce Pymunk only if collision and
constraint behaviour serves that question. Reuse the frame/renderer boundary
where it fits; extend it for new primitives only when an experiment needs them.
