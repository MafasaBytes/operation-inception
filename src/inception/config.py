"""Strict TOML configuration, independent of numerical and drawing libraries."""

from dataclasses import dataclass, fields
import math
from pathlib import Path
import re
import tomllib

WORLD_HEIGHT = 16 / 9


@dataclass(frozen=True)
class SimulationConfig:
    seed: int = 1001
    rings: int = 7
    target_radius: float = 0.40
    particle_radius: float = 0.0075
    initial_margin: float = 0.075
    drift_speed: float = 0.025
    curve_strength: float = 0.12
    intro_seconds: float = 0.8
    convergence_seconds: float = 5.2
    stagger_seconds: float = 0.9
    hold_seconds: float = 1.4

    def __post_init__(self):
        for field in fields(self):
            value = getattr(self, field.name)
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError(f"simulation.{field.name} must be a finite number")
        if type(self.seed) is not int or self.seed < 0:
            raise ValueError("seed must be a nonnegative integer")
        if type(self.rings) is not int or not 1 <= self.rings <= 20:
            raise ValueError("rings must be an integer from 1 to 20")
        if not 0 < self.particle_radius < self.target_radius < 0.48:
            raise ValueError("require 0 < particle_radius < target_radius < 0.48")
        if self.target_radius / self.rings <= 2.5 * self.particle_radius:
            raise ValueError("target spacing must exceed 2.5 particle radii")
        if not self.particle_radius < self.initial_margin < 0.25:
            raise ValueError("initial_margin must lie between particle_radius and 0.25")
        if not 0 <= self.drift_speed <= 0.05 or not 0 <= self.curve_strength <= 0.25:
            raise ValueError("drift_speed must be in [0, .05], curve_strength in [0, .25]")
        if min(self.intro_seconds, self.stagger_seconds) < 0:
            raise ValueError("intro and stagger durations cannot be negative")
        if self.convergence_seconds <= 0 or self.hold_seconds <= 0:
            raise ValueError("convergence and hold durations must be positive")

    @property
    def particle_count(self):
        return 1 + 3 * self.rings * (self.rings + 1)

    @property
    def settle_time(self):
        return self.intro_seconds + self.stagger_seconds + self.convergence_seconds

    @property
    def duration(self):
        return self.settle_time + self.hold_seconds


@dataclass(frozen=True)
class CausalConfig:
    """Only the composition and story beats of the 91-bead 001B choreography."""

    model: str = "causal-assembly"
    seed: int = 1001
    target_radius: float = 0.32
    particle_radius: float = 0.0125
    center_x: float = 0.445
    center_y: float = 0.78
    seed_lock_seconds: float = 0.43
    neighbors_start_seconds: float = 0.47
    neighbors_lock_seconds: float = 0.90
    main_lock_seconds: float = 4.20
    hero_start_seconds: float = 4.45
    hero_lock_seconds: float = 5.15
    duration_seconds: float = 6.20

    def __post_init__(self):
        if self.model != "causal-assembly":
            raise ValueError("unknown causal model")
        for field in fields(self):
            if field.name == "model":
                continue
            value = getattr(self, field.name)
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError(f"simulation.{field.name} must be finite")
        if type(self.seed) is not int or self.seed < 0:
            raise ValueError("seed must be a nonnegative integer")
        if not 0.28 <= self.target_radius <= 0.34 or not 0.010 <= self.particle_radius <= 0.014:
            raise ValueError("001B requires radius .28..34 and bead radius .010..014")
        if not 0.42 <= self.center_x <= 0.46 or not 0.72 <= self.center_y <= 0.84:
            raise ValueError("001B center must retain its overlay clearance")
        beats = [0, self.seed_lock_seconds, self.neighbors_start_seconds,
                 self.neighbors_lock_seconds, self.main_lock_seconds,
                 self.hero_start_seconds, self.hero_lock_seconds, self.duration_seconds]
        if any(a >= b for a, b in zip(beats, beats[1:])):
            raise ValueError("001B story beats must be strictly increasing")
        if (self.main_lock_seconds - self.neighbors_lock_seconds) / 14 < 0.20:
            raise ValueError("001B assembly batches need at least .20 seconds")
        if not 6 <= self.duration_seconds <= 6.4:
            raise ValueError("001B duration must be 6.0..6.4 seconds")
        if self.duration_seconds - self.hero_lock_seconds < 0.8:
            raise ValueError("001B requires time for the lock response and clean settling")

    @property
    def particle_count(self):
        return 91

    @property
    def duration(self):
        return self.duration_seconds

    @property
    def hold_seconds(self):
        return self.duration_seconds - self.hero_lock_seconds


@dataclass(frozen=True)
class RenderConfig:
    preview_width: int = 360
    preview_height: int = 640
    final_width: int = 1080
    final_height: int = 1920
    fps: int = 30
    supersample: int = 2
    background: str = "#0b1420"
    particle_color: str = "#f5d9a0"
    accent_color: str = "#79c9c0"
    trail_seconds: float = 0.045
    resolution_pulse: float = 0.18
    crf: int = 18
    background_bloom: float = 1.0

    def __post_init__(self):
        for name in ("preview_width", "preview_height", "final_width", "final_height",
                     "fps", "supersample", "crf"):
            if type(getattr(self, name)) is not int:
                raise ValueError(f"render.{name} must be an integer")
        for width, height in (self.dimensions("preview"), self.dimensions("final")):
            if min(width, height) < 2 or width % 2 or height % 2 or width * 16 != height * 9:
                raise ValueError("dimensions must be positive, even, and exactly 9:16")
        if not 1 <= self.fps <= 120 or not 1 <= self.supersample <= 4 or not 0 <= self.crf <= 51:
            raise ValueError("require fps 1..120, supersample 1..4, crf 0..51")
        for name, maximum in (("trail_seconds", 0.2), ("resolution_pulse", 0.5), ("background_bloom", 1)):
            value = getattr(self, name)
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= maximum:
                raise ValueError(f"render.{name} must be in [0, {maximum}]")
        for color in (self.background, self.particle_color, self.accent_color):
            if not isinstance(color, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
                raise ValueError("colors must use #RRGGBB")

    def dimensions(self, quality):
        if quality not in ("preview", "final"):
            raise ValueError("quality must be preview or final")
        return getattr(self, f"{quality}_width"), getattr(self, f"{quality}_height")


@dataclass(frozen=True)
class Config:
    simulation: SimulationConfig | CausalConfig
    render: RenderConfig

    def __post_init__(self):
        if self.simulation.hold_seconds < 1 / self.render.fps:
            raise ValueError("hold_seconds must allow at least one settled output frame")


def load_config(path: str | Path) -> Config:
    with Path(path).open("rb") as file:
        data = tomllib.load(file)
    if set(data) != {"simulation", "render"}:
        raise ValueError("configuration must contain only [simulation] and [render]")
    try:
        model = data["simulation"].get("model") if isinstance(data["simulation"], dict) else None
        simulation_type = CausalConfig if model == "causal-assembly" else SimulationConfig
        return Config(simulation_type(**data["simulation"]), RenderConfig(**data["render"]))
    except TypeError as error:
        raise ValueError(f"invalid configuration key or section: {error}") from error
