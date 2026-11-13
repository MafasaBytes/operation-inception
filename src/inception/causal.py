"""Experiment 001B: a fixed neighbor-driven choreography, not a new engine."""

import numpy as np

from .config import CausalConfig, WORLD_HEIGHT
from .simulation import ParticleFrame, hexagonal_targets


def smooth(value):
    u = np.clip(value, 0, 1)
    return u**3 * (10 + u * (-15 + 6*u))


class CausalAssembly:
    def __init__(self, config: CausalConfig):
        self.config = config
        rng = np.random.Generator(np.random.PCG64(config.seed))
        self.center = np.array([config.center_x, config.center_y])
        self.targets, self.groups = hexagonal_targets(5, config.target_radius)
        self.targets += self.center - [0.5, WORLD_HEIGHT / 2]
        self.seed_index = int(np.flatnonzero(self.groups == 0)[0])
        self.hero = int(np.argmax(self.targets[:, 0]))
        self.radii = np.full(91, config.particle_radius)
        self.starts = np.zeros(91)
        self.locks = np.zeros(91)
        self.parents = np.full(91, -1, dtype=int)
        self.locks[self.seed_index] = config.seed_lock_seconds
        self.batches = [[self.seed_index]]
        # Six sectors advance together; each later shell waits for the previous one.
        batches = []
        for shell in range(1, 6):
            ids = np.flatnonzero(self.groups == shell)
            delta = self.targets[ids] - self.center
            ids = ids[np.argsort(np.arctan2(delta[:, 1], delta[:, 0]), kind="stable")]
            for offset in range(shell):
                batches.append([int(ids[side*shell + offset]) for side in range(6)
                                if ids[side*shell + offset] != self.hero])
        interval = (config.main_lock_seconds - config.neighbors_lock_seconds) / 14
        for batch_index, batch in enumerate(batches):
            start = (config.neighbors_start_seconds if batch_index == 0 else
                     config.neighbors_lock_seconds + (batch_index-1)*interval)
            lock = config.neighbors_lock_seconds if batch_index == 0 else start + interval
            for index in batch:
                self.starts[index], self.locks[index] = start, lock
                distances = np.linalg.norm(self.targets - self.targets[index], axis=1)
                candidates = np.flatnonzero((distances < config.target_radius / 5 * 1.01)
                                            & (self.groups == self.groups[index]-1))
                self.parents[index] = int(candidates[np.argmin(self.locks[candidates])])
                assert self.locks[self.parents[index]] <= start + 1e-10
            self.batches.append(batch)
        self.starts[self.hero] = config.hero_start_seconds
        self.locks[self.hero] = config.hero_lock_seconds
        self.parents[self.hero] = int(np.argmin(np.linalg.norm(self.targets - self.targets[self.hero], axis=1)
                                              + np.where(self.groups == 4, 0, 100)))
        self.initial = self.targets.copy()
        self.bends = np.zeros_like(self.targets)
        self.initial[self.hero] = self.center + [0.39, -0.35]
        self.initial[self.seed_index] = self.center + [-0.055, 0.095]
        self.bends[self.seed_index] = [0.025, 0.012]
        # Plan short paths backwards in arrival order. Later waiting beads are
        # obstacles; earlier beads' locked targets are obstacles after their lock.
        # This bounded rejection is choreography clearance, not a collision solver.
        times = np.arange(0, config.hero_lock_seconds + 1/120, 1/120)
        known = [self.hero]
        paths = {self.hero: self._hero_path(times)}
        minimum = config.particle_radius * 2.16
        order = [index for batch in self.batches for index in batch]
        for index in reversed(order):
            earlier = np.array([j for j in order if self.locks[j] < self.locks[index]-1e-9], dtype=int)
            known_paths = np.stack([paths[j] for j in known], axis=1)
            for attempt in range(2400):
                if index != self.seed_index:
                    outward = self.targets[index] - self.center
                    outward /= np.linalg.norm(outward)
                    tangent = np.array([-outward[1], outward[0]])
                    self.initial[index] = (self.targets[index] + outward*rng.uniform(0.045, 0.145)
                                           + tangent*rng.uniform(-0.040, 0.040))
                    self.bends[index] = tangent * rng.uniform(-0.018, 0.018)
                candidate = self._path(index, times)
                if np.any(candidate[:, 0] < .025) or np.any(candidate[:, 0] > .94):
                    continue
                if np.any(np.linalg.norm(candidate[:, None] - known_paths, axis=2) < minimum):
                    continue
                if len(earlier):
                    distances = np.linalg.norm(candidate[:, None] - self.targets[earlier][None], axis=2)
                    if np.any((distances < minimum) & (times[:, None] >= self.locks[earlier][None])):
                        continue
                paths[index] = candidate
                known.append(index)
                break
            else:
                raise ValueError(f"001B path clearance failed for bead {index}; try a smaller bead radius or another seed")
        for array in (self.targets, self.groups, self.radii, self.starts, self.locks,
                      self.parents, self.initial, self.bends):
            array.setflags(write=False)

    def _path(self, index, times):
        start = self.starts[index]
        signal = 0 if index == self.seed_index else 1/30
        u = np.clip((np.asarray(times) - start - signal) / (self.locks[index]-start-signal), 0, 1)
        ease = smooth(u)
        position = ((1-ease[..., None])*self.initial[index] + ease[..., None]*self.targets[index]
                    + (16*u*u*(1-u)**2)[..., None]*self.bends[index])
        return np.where((np.asarray(times) >= self.locks[index])[..., None], self.targets[index], position)

    def _hero_path(self, times):
        cfg = self.config
        times = np.asarray(times)
        turn = cfg.hero_lock_seconds - 0.14
        u = smooth((times - cfg.hero_start_seconds) / (turn - cfg.hero_start_seconds))
        a = self.initial[self.hero]
        b, c = self.center + [0.47, -.24], self.center + [0.46, .015]
        overshoot = self.targets[self.hero] + [-.010, 0]
        position = ((1-u)[..., None]**3*a + (3*(1-u)**2*u)[..., None]*b
                    + (3*(1-u)*u*u)[..., None]*c + u[..., None]**3*overshoot)
        correction = smooth((times-turn) / (cfg.hero_lock_seconds-turn))
        position = np.where((times >= turn)[..., None],
                            (1-correction[..., None])*overshoot + correction[..., None]*self.targets[self.hero], position)
        return np.where((times >= cfg.hero_lock_seconds)[..., None], self.targets[self.hero], position)

    def sample(self, time):
        if not np.isfinite(time) or time < 0:
            raise ValueError("sample time must be finite and nonnegative")
        cfg = self.config
        positions = np.array([self._path(i, time) if i != self.hero else self._hero_path(time) for i in range(91)])
        age = time - self.locks
        active = (time >= self.starts) & (age < 0)
        activation = active.astype(float)
        activation += .65 * (1-smooth(age/(5/30))) * (age >= 0)
        activation[self.hero] = float(smooth((time - (cfg.hero_start_seconds-.85))/.25)) if age[self.hero] < 0 else max(0, 1-age[self.hero]/.10)
        brightness = np.where(age >= 0, 1.0, .46)
        brightness[active] = 1.18
        brightness[self.hero] = max(brightness[self.hero], .55 + .6*activation[self.hero])
        scales = np.ones(91)
        bounce = np.clip(age/(5/30), 0, 1)
        scales += np.where((age >= 0) & (age < 5/30), -.18*np.cos(2*np.pi*bounce)*(1-bounce)**2, 0)
        brightness += np.where((age >= 0) & (age < 5/30), .32*(1-bounce), 0)
        # Before lock, a seed-sized cue and short parent-to-child signals expose causality.
        links = []
        for index in np.flatnonzero(active):
            parent = self.parents[index]
            phase = (time-self.starts[index]) / (2/30)
            if parent >= 0 and phase < 1 and index != self.hero:
                links.append([self.targets[parent], positions[index], np.array([phase, 0])])
                brightness[parent] = 1.35
            if index == self.seed_index:
                scales[index] *= 1.12
        payoff_age = time - cfg.hero_lock_seconds
        if 0 <= payoff_age < .60:
            radial = np.linalg.norm(self.targets-self.center, axis=1) / cfg.target_radius
            wave_age = payoff_age - radial*.32
            brightness += .62*np.exp(-((wave_age-.07)/.065)**2)
            compression = .018*np.sin(np.pi*np.clip(payoff_age/.40, 0, 1))**2
            positions = self.center + (positions-self.center)*(1-compression)
        slot = np.r_[self.targets[self.hero], smooth((time-3.45)/.20)] if 3.45 <= time < cfg.hero_lock_seconds else None
        completion = (age >= 0).astype(float)
        for array in (positions, activation, brightness, scales, completion):
            array.setflags(write=False)
        return ParticleFrame(time, positions, self.targets, self.radii, self.groups, completion,
                             float(np.clip(payoff_age/.6, 0, 1)), activation, brightness, scales,
                             np.array(links) if links else None, slot)
