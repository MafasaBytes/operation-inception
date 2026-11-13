# Historical particle-phase record

This document records the closed phase. It is not the active roadmap and does
not authorize regeneration, polishing, overwrite, or publication of any artifact.
See ../ARCHITECTURE.md for the current project direction.

---

# Architecture and engineering decisions

## Single vertical slice

```text
TOML → validated Config → ChaosToOrder.sample(time) → ParticleFrame
                                                       ↓
                                              PillowRenderer → RGB bytes
                                                       ↓
                                              FFmpeg → vertical MP4
                       numerical frames → CSV measurements + JSON manifest
```

`config.py` defines immutable settings and validation using only the standard
library. `simulation.py` owns the seeded initial state, target construction,
trajectory sampling, and numerical measurements. It depends on NumPy and config,
and imports no drawing or encoding code. `rendering.py` turns snapshots into
Pillow RGB images without advancing or mutating the model. `pipeline.py` handles
frame times, streaming encoding, measurements, provenance, and file lifecycle.
`cli.py` exposes this path with actionable errors and nonzero failure exits.

`ParticleFrame` contains time, positions, targets, radii, shell groups,
per-particle eased completion, and final-resolution progress. Arrays exposed by
the baseline model are read-only. These semantic numerical values allow a
different renderer to show the same motion. Another particle family can supply
the same snapshot without inheriting this algorithm. We defer a plugin registry,
abstract base classes, and support for non-particle primitives until a second
family needs them. The current renderer depends on the snapshot type, not the
concrete `ChaosToOrder` implementation.

## Motion model

World coordinates span x=0..1 and y=0..16/9, so simulation values are independent
of output resolution. A local NumPy PCG64 generator supplies all randomness.
Rejection sampling enforces initial center spacing greater than 2.5 particle
radii. A bounded sampling budget fails clearly if the requested population
cannot be packed. Stable outer-first greedy nearest matching assigns each point
to one unique target; it is neither globally optimal nor collision-aware.

For particle i, let u be time normalised between its onset and arrival, clipped
to [0,1]. Set s(u)=10u³−15u⁴+6u⁵ and b(u)=64u³(1−u)³. Then:

```text
free(t) = initial + drift * sin(1.7*t) / 1.7
position(t) = (1-s(u))*free(t) + s(u)*target + b(u)*bend
```

`bend` is a seeded perpendicular fraction of the initial-to-target displacement.
The blend has zero first and second derivatives at both ends, matching the free
motion at onset and zero velocity/acceleration at arrival. Endpoints are assigned
explicitly to remove floating-point residue. The free-drift frequency 1.7 rad/s,
quintic degree, and bend envelope define model version 1; they are fixed design
constants, not exposed experiment controls. Changing these requires a documented
model revision. Core controls, including drift amplitude and curvature, are TOML
settings. Stagger is proportional to target shell index, producing an inside-out
emergence. After the final shell arrives, geometry stays fixed while a smooth
brightness pulse marks resolution.

This is stylised kinematic choreography. There is no mass, force balance,
collision response, or claim of physical fidelity. It was chosen over a spring
integrator to obtain an exact endpoint, smooth pacing, and small implementation.
Pymunk would add value for real mechanical constraints in a later experiment.

## Rendering and encoding

Pillow provides antialiased circles, restrained halos, short trails, and a cached
background gradient without a window or GPU. Supersampling defaults to 2× per
dimension. Final rendering therefore uses more memory and CPU than preview;
change `supersample` to 1 for faster drafts. Rendering is intentionally 9:16 in
this milestone. Both width and height must be even for YUV420p.

Frames use t=index/FPS with count=ceil(duration*FPS), so encoded duration can
exceed requested duration by less than one frame. Validation reserves at least
one output interval for the final hold. FFmpeg receives RGB24 via stdin and
encodes H.264/YUV420p with faststart. Encoding uses one thread to reduce one source
of variation. There is no intermediate frame directory or audio track.

The encoder writes to a temporary directory on the output filesystem. Encoder
failure cleans up temporary files and preserves an existing destination. The
video and metrics are renamed into place after success, with the manifest last.
An old manifest is removed immediately before publishing a replacement run.
Each rename is atomic; the group is not a filesystem transaction. On interruption
during publication, verify the manifest's video hash or rerun. Overwriting
requires an explicit CLI flag. Concurrent writers to the same destination are
not supported.

## Measurements and reproducibility

Each output has a CSV and manifest. CSV rows contain RMS assigned-target error,
fraction within 1e-8 canvas widths of its target, minimum pairwise center
distance, and maximum finite-difference speed. The first speed is defined as zero
because no previous frame exists. Spacing and speed are sampled diagnostics,
not continuous-time extrema or measures of perceived order. Pairwise spacing
uses O(N²) memory and work per frame; this is acceptable for 169 particles.

The manifest contains effective configuration, a hash of its canonical sorted
JSON representation, a hash of the package's Python source files, dependency and
encoder versions, dimensions, timing, output SHA-256, and initial/final metrics.
It has no timestamp, avoiding irrelevant run-to-run differences. A source hash
identifies code but cannot reconstruct it: preserve the source revision or
snapshot too. The source hash excludes docs, packaging metadata, and dependencies;
those versions and effective settings are recorded separately.

Seeded numerical reproduction assumes identical code and numerical environment.
Bit-identical MP4 output is checked locally but is not promised across operating
systems, CPU architectures, Pillow, NumPy, Python, or FFmpeg builds. Dependency
ranges permit compatible updates; recorded versions enable closer replay. No
cross-platform deterministic maths library or full environment lock is included.

## Narrow 001B revision

`causal.py` implements the specific 91-bead neighbor-lock treatment. The existing
pipeline selects it when the simulation TOML says `model = "causal-assembly"`;
there is no registry, editor, or new simulation framework. Its small dedicated
configuration describes composition and story beats instead of reinterpreting
the baseline's convergence controls. Baseline motion equations are unchanged.

Snapshots optionally carry numerical activation, brightness, scale, short link,
and empty-slot cues. The same Pillow renderer consumes these cues for bead
shading and event light; the FFmpeg export path is shared. Models do not import
Pillow or draw their cues. For each ordinary bead, its parent is an already-locked
nearest neighbor from the previous shell. Six-sector batches are staged after
their parents lock, with an initial signal followed by a short curved approach.
This is scheduled visual causality, not physical force transmission.

A bounded reverse-order candidate search checks paths at 120 Hz against later
waiting/moving beads and earlier locked targets. This is a small scene-specific
clearance planner. It does not prove separation at every continuous timestamp,
model halo collisions, or add collision dynamics. Final collective compression
is explicit choreography; bead centers return exactly to their targets and all
presentation cues terminate before the final stillness.

The focused 001B reliability check covers neighbor eligibility, deterministic
sampling, a six-mover cap, actual render-frame core separation including scale,
distinct lock counts through the story, and exact terminal geometry/appearance.
Technical checks support reliable output; they do not establish creative success.

## Testing strategy

pytest verifies deterministic sampling, changed seeds, exact shell counts and
spacing, initial disorder, sampled convergence, terminal equality and stillness,
smooth onset/arrival, finite visible paths over four fixed seeds, validation,
and render dimensions without mutation. A small FFmpeg integration test probes
and fully decodes a real video, checks sidecars and overwrite protection, and
compares repeated encoding hashes. An encoder-failure test checks cleanup and
preservation. Tool-dependent tests explicitly skip when tools are unavailable.

For delivery, also render the full baseline preview, probe and decode it, inspect
selected frames, and check Git ignores. Behavioural checks do not establish
visual polish or audience effects; frame review and the proposed viewer study
address those separately. Future collision avoidance would need tests for minimum
separation throughout motion, not only for final geometry.
