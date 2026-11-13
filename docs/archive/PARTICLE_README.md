# Frozen particle-phase README

Historical instructions below are retained as a record, not authorization to run
rendering, overwrite outputs, polish MS03B, or produce an MS03B master. The active
direction is spectator micro-games and the MS05 audio foundation; see ../../README.md.

---

# Operation Inception

A small laboratory for deterministic, procedural short-form video. Experiment
001, **Chaos to Order**, turns an irregular field of 169 particles into an exact
hexagonal lattice. Its forces are designed motion, not a real-world physics model.
Audience satisfaction and perceptual fluency remain research hypotheses.

The baseline is an 8.3-second silent vertical animation: brief drifting disorder,
smooth staggered convergence, and a 1.4-second final hold with a subtle light pulse.
Warm and teal particles on a dark field are an initial visual vocabulary to test,
not an established brand identity.

Experiment **001B, Causal Assembly with Final Lock**, was rejected for use by the
owner. Its outputs are preserved: 91 larger beads assemble in neighbor-linked groups
of at most six. One cyan bead completes the missing right tip, triggering a
restrained ripple and compression/release. It lasts 6.2 seconds, including only
about 0.45 seconds of unchanged completed formation. The original videos remain
at `outputs/experiment001-preview.mp4` and `outputs/experiment001-final.mp4`.
See [the phase intentions and review limits](docs/EXPERIMENT001B.md).

**MS03 — Last Bead Standing** is a preserved 24-second, game-like rough cut:
one cyan mover wakes stationary ivory beads on contact. Moving beads compound
until one ivory survivor remains, with two near misses before its final hit.
The primary review video includes procedural impact notes and near-miss sounds;
a muted copy supports legibility testing. Owner-and-wife creative review is
pending. No MS03 1080p master has been exported.

```bash
.venv/bin/python -m inception.ms03 --config configs/ms03.toml
```

This command produces the two 360×640 MP4s, six-frame contact sheet, audio WAV,
and event log under `outputs/ms03/`. Add `--overwrite` to replace that rough cut.
It does not change the Experiment 001 or 001B outputs. Read the
[MS03 review note](docs/MS03.md) for exact timings and the creative gate.

**MS03B — Color War** is the current phone-review cut: two colored movers recruit
40 neutral beads, then capture opposing beads through directed contacts. It has
no text, counters, labels, scores, or explanatory overlays. Delivery is 720×1280
at 30 FPS, high-bitrate H.264 with BT.709 color metadata and stereo team sounds.
Watch the primary cut once before opening the contact sheet or timing notes,
which reveal the outcome. Owner-and-wife creative acceptance is pending.

```bash
.venv/bin/python -m inception.ms03b --config configs/ms03b.toml
```

Outputs are under `outputs/ms03b/`: primary sound MP4, muted copy, contact sheet,
WAV mix, and event log. Add `--overwrite` to replace this cut. This command only
supports the 720p review format; it does not produce a 1080p master or modify any
MS03 or earlier outputs. See [the review note (spoilers)](docs/MS03B.md).

## Install

Use Python 3.11 or newer, plus system **FFmpeg and FFprobe** on `PATH` with the
`libx264` encoder (for example, `sudo apt install ffmpeg` on Ubuntu).
From the repository root:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
ffmpeg -version
ffprobe -version
```

Runtime dependencies are NumPy and Pillow. pytest is a development dependency;
TOML parsing uses the Python standard library. The initial run used Python 3.13.11,
NumPy 2.4.1, Pillow 12.1.0, pytest 9.0.2, and FFmpeg 6.1.1. Dependency ranges in
`pyproject.toml` are compatibility bounds, not a complete environment lock. For
closer replay of this baseline after installation:

```bash
.venv/bin/python -m pip install numpy==2.4.1 Pillow==12.1.0 pytest==9.0.2
```

## Render and test

```bash
# Lightweight development output, 360x640 at 30 FPS.
.venv/bin/inception --config configs/experiment001.toml --output outputs/experiment001-preview.mp4

# Same trajectories, 1080x1920 at 30 FPS.
.venv/bin/inception --config configs/experiment001.toml --quality final --output outputs/experiment001-final.mp4

.venv/bin/python -m pytest -q

# Verify dimensions, codec, duration, and decoded frame count.
ffprobe -v error -count_frames -show_entries stream=codec_name,width,height,pix_fmt,r_frame_rate,nb_read_frames,duration -of json outputs/experiment001-preview.mp4

# Decode every frame to check the stream for errors.
ffmpeg -v error -i outputs/experiment001-preview.mp4 -f null -
```

To reproduce the single 001B treatment with the same renderer and export path:

```bash
.venv/bin/inception --config configs/experiment001b.toml --output outputs/experiment001b-preview.mp4
.venv/bin/inception --config configs/experiment001b.toml --quality final --output outputs/experiment001b-final.mp4
```

Add `--overwrite` when deliberately replacing an existing 001B render. The
360×640 preview and 1080×1920 final use the same seeded choreography, 186 frames
at 30 FPS. The review contact sheet is `outputs/experiment001b-contact-sheet.png`.

`python -m inception` is also supported in the installed environment. Existing
videos or sidecars are protected by default; add `--overwrite` to replace them.
The CLI reports invalid settings or encoder failures with a nonzero exit code.

Each render creates three ignored artifacts:

| File | Purpose |
| --- | --- |
| `outputs/experiment001-preview.mp4` | H.264, YUV420p, 9:16 video |
| `outputs/experiment001-preview.metrics.csv` | Per-frame target error, settlement, spacing, and speed |
| `outputs/experiment001-preview.manifest.json` | Effective configuration, source/config/video hashes, versions, and summary |

## Change an experiment

Copy `configs/experiment001.toml`, change one control, and pass the copy with
`--config`. `simulation.seed` changes the initial field, drift, and path curvature.
`rings` sets particle count using `1 + 3*rings*(rings+1)`. `target_radius`,
`particle_radius`, and `initial_margin` control geometry. Timing, stagger, drift,
and curvature control the motion. The render section controls resolution, FPS,
antialiasing, colors, trails, the final pulse, and encoding quality.

Coordinates use canvas widths: x spans 0..1 and y spans 0..16/9. Preview and final
dimensions must be even and exactly 9:16. More particles may require smaller
particle radii. Configuration validation rejects overlapping target geometry;
initial packing reports an error if its bounded sampling budget is exhausted.

## Design and limits

`config → simulation.sample(time) → numerical snapshot → Pillow → FFmpeg`

Quintic easing blends seeded drifting positions toward fixed targets along
curved paths. Inside-out timing makes the structure emerge progressively. The
simulation does not import rendering libraries. A future simulation can supply
the same particle snapshot; a future renderer can consume it independently.

There is no collision physics, audio, viewer analytics, or publishing integration.
In baseline 001, paths may cross and particles may overlap in transit. Revision
001B uses seeded rejection of short candidate paths against other beads to avoid
core overlaps in its delivered choreography; this is planning, not collision response.
Deterministic positions require the same settings, seed, implementation, and
numerical environment. Encoded bytes may differ across library/FFmpeg versions
and platforms. Numerical target error measures engineering convergence, not
perceived order or satisfaction.

See [VISION](docs/VISION.md), [PSYCHOLOGY](docs/PSYCHOLOGY.md),
[EXPERIMENTS](docs/EXPERIMENTS.md), and [ARCHITECTURE](docs/ARCHITECTURE.md).
The next research step is a paired timing experiment with viewer feedback,
keeping seed, geometry, and palette fixed.
