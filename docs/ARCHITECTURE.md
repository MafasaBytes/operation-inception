# Architecture: spectator games and procedural audio

## Active boundary

```text
MS04.1 grid topology → MS04.2 pure rules → MS04.3 genuine match log
                                                ↓
                                  MS04.4 absolute-time plan
                                      ↙                  ↘
                          event-only renderer       MS05 sound adapter
                                      ↘                  ↙
                                  H.264/AAC review cut
```

`inception.grid` supplies immutable row-major topology and stable orthogonal
adjacency from MS04.1. Its separate static review renderer was not transferred.
`inception.rules` owns MS04.2 game truth: immutable settled state, legal placement,
FIFO cascades, ownership, elimination, victory, and explicit rollback draws.
It imports only pure grid topology, with no clock, renderer, audio, or policy.
`inception.ms04_2` runs the versioned conformance fixture and records logical JSON.

`inception.matches` and `inception.ms04_3` supply seeded offline policies,
complete simulation, transparent proxy scoring, and genuine-result selection.
They cannot bypass the authoritative rules or rewrite a winner. The complete
search record includes honest unfinished/draw outcomes as well as the selection.

`inception.presentation` maps the selected immutable log to absolute times and
reconstructs every board state. Individual `orb_received` facts preserve every
transfer, including same-owner arrivals. Incomplete logs, draws, mismatched final
states, and a match other than the approved selection are rejected.

`inception.ms04_4` renders only the frozen presentation plan. Its sound adapter
maps selected semantic facts to the existing MS05 contract on the same clock.
Neither rendering nor sound selects a move or changes game truth. The module
exports review media, a reconstructable timeline, and a hash/probe manifest;
it does not publish or produce a 1080p master.

The initial `inception.audio` package owns the event contract and procedural
sound only. `events.py` parses a versioned fixture into frozen dataclasses and
tuples. `synthesis.py` maps event kinds and team voices to sampled cues, mixes
phase-aligned stereo, applies shared peak attenuation, and writes PCM WAV.
`__main__.py` is a small offline fixture-to-WAV command. It imports no particle
model, game engine, renderer, FFmpeg, or voice/model service. The standalone
fixture remains synthetic; MS04.4 now supplies a separate genuine-match adapter
without changing the audio package. [MS05](MS05.md) defines the contract.

## Frozen experimental infrastructure

Existing top-level particle modules (`simulation.py`, `causal.py`, `ms03.py`,
`ms03b.py`, rendering/configuration/export/CLI support) and their configurations
are retained unchanged. They are historical experiments, not the active product
architecture. Their scripted contact outcomes must not become the future game's
rules engine or match selector. MS03B is frozen exactly as delivered; there is
no authorized polish, regeneration, overwrite, or 1080p master.

The former pipeline and engineering decisions remain in the
[archived architecture](archive/ARCHITECTURE-particle-phase.md). Its render
verification instructions are historical, not a current authorization to render.
Pre-existing outputs and source/configuration hashes are recorded in
[the freeze inventory](archive/particle-phase-freeze-v1.json). The read-only
`tools/verify_particle_freeze.py` check detects missing or changed listed bytes.

MS04.4 uses existing Pillow/NumPy/FFmpeg; the audio slice remains NumPy and the
standard library. No new service,
publishing integration, UI, general event bus, or game framework is needed.
Do not add speech, narration, voiceover, music, LLMs, or generative models.
