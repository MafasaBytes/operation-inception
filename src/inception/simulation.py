"""Seeded, stylised convergence. No renderer, integration loop, or physical claims."""

from dataclasses import dataclass
import numpy as np

from .config import SimulationConfig, WORLD_HEIGHT


@dataclass(frozen=True)
class ParticleFrame:
    time: float
    positions: np.ndarray
    targets: np.ndarray
    radii: np.ndarray
    groups: np.ndarray
    completion: np.ndarray
    resolution: float
    # Optional numerical presentation cues used by 001B; baseline snapshots omit them.
    activation: np.ndarray | None = None
    brightness: np.ndarray | None = None
    scales: np.ndarray | None = None
    links: np.ndarray | None = None
    slot: np.ndarray | None = None


def hexagonal_targets(rings: int, radius: float):
    """Axial triangular lattice, including every shell of a regular hexagon."""
    axial = [(q, r) for q in range(-rings, rings + 1)
             for r in range(-rings, rings + 1) if abs(q + r) <= rings]
    groups = np.array([max(abs(q), abs(r), abs(q + r)) for q, r in axial])
    points = np.array([(q + r / 2, np.sqrt(3) * r / 2) for q, r in axial])
    return points * (radius / rings) + [0.5, WORLD_HEIGHT / 2], groups


class ChaosToOrder:
    def __init__(self, config: SimulationConfig):
        self.config = config
        rng = np.random.Generator(np.random.PCG64(config.seed))
        self.targets, self.groups = hexagonal_targets(config.rings, config.target_radius)
        # Rejection sampling removes initial overlaps without creating a visible grid.
        points = []
        lower = np.array([config.initial_margin, config.initial_margin])
        upper = np.array([1, WORLD_HEIGHT]) - lower
        for _ in range(config.particle_count * 2000):
            candidate = rng.uniform(lower, upper)
            if not points or np.min(np.linalg.norm(np.array(points) - candidate, axis=1)) > 2.5 * config.particle_radius:
                points.append(candidate)
                if len(points) == config.particle_count:
                    break
        else:
            raise ValueError("initial particles cannot be packed; reduce rings or particle_radius")
        points = np.array(points)
        # Deterministic greedy matching reduces travel; no global optimum is claimed.
        # Fill outer targets first, reserving central points for central targets.
        self.initial = np.empty_like(points)
        available = np.ones(len(points), dtype=bool)
        for index in np.argsort(-self.groups, kind="stable"):
            distances = np.sum((points - self.targets[index]) ** 2, axis=1)
            distances[~available] = np.inf
            chosen = np.argmin(distances)
            self.initial[index] = points[chosen]
            available[chosen] = False
        angles = rng.uniform(0, 2 * np.pi, config.particle_count)
        self.drift = np.column_stack((np.cos(angles), np.sin(angles))) * config.drift_speed
        displacement = self.targets - self.initial
        self.bend = np.column_stack((-displacement[:, 1], displacement[:, 0]))
        self.bend *= rng.uniform(-1, 1, (config.particle_count, 1)) * config.curve_strength
        # Inside-out stagger makes emergence legible; the last shell lands together.
        self.onsets = config.intro_seconds + config.stagger_seconds * self.groups / config.rings
        self.radii = np.full(config.particle_count, config.particle_radius)
        for array in (self.targets, self.groups, self.initial, self.drift, self.bend, self.onsets, self.radii):
            array.setflags(write=False)

    def sample(self, time: float) -> ParticleFrame:
        if not np.isfinite(time) or time < 0:
            raise ValueError("sample time must be finite and nonnegative")
        cfg = self.config
        u = np.clip((time - self.onsets) / cfg.convergence_seconds, 0, 1)
        ease = u ** 3 * (10 + u * (-15 + 6 * u))
        envelope = 64 * u ** 3 * (1 - u) ** 3
        free = self.initial + self.drift * np.sin(1.7 * time) / 1.7
        positions = ((1 - ease[:, None]) * free + ease[:, None] * self.targets
                     + envelope[:, None] * self.bend)
        # Explicit endpoints prevent floating-point residue and preserve an exact hold.
        positions[u >= 1] = self.targets[u >= 1]
        positions.setflags(write=False)
        ease.setflags(write=False)
        resolution = float(np.clip((time - cfg.settle_time) / cfg.hold_seconds, 0, 1))
        return ParticleFrame(time, positions, self.targets, self.radii, self.groups, ease, resolution)


def measure(frame: ParticleFrame, previous: ParticleFrame | None = None):
    """Engineering measurements in canvas-width units, not psychological scores."""
    errors = np.linalg.norm(frame.positions - frame.targets, axis=1)
    distances = np.linalg.norm(frame.positions[:, None] - frame.positions[None, :], axis=2)
    np.fill_diagonal(distances, np.inf)
    speed = 0.0
    if previous is not None:
        dt = frame.time - previous.time
        if dt <= 0:
            raise ValueError("measurement frames must increase in time")
        speed = float(np.max(np.linalg.norm(frame.positions - previous.positions, axis=1)) / dt)
    return {"time_seconds": frame.time,
            "rms_target_error": float(np.sqrt(np.mean(errors ** 2))),
            "settled_fraction": float(np.mean(errors <= 1e-8)),
            "min_center_distance": float(distances.min()),
            "max_speed": speed}
