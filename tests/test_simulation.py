from dataclasses import replace

import numpy as np
import pytest

from inception.config import Config, RenderConfig, SimulationConfig, WORLD_HEIGHT, load_config
from inception.simulation import ChaosToOrder, hexagonal_targets, measure


@pytest.fixture
def simulation():
    return ChaosToOrder(SimulationConfig())


def test_seed_reproduces_positions_independently_of_sampling_order(simulation):
    expected = simulation.sample(3.1).positions.copy()
    simulation.sample(7)
    np.testing.assert_array_equal(simulation.sample(3.1).positions, expected)
    np.testing.assert_array_equal(ChaosToOrder(simulation.config).sample(3.1).positions, expected)
    other = ChaosToOrder(replace(simulation.config, seed=42))
    assert not np.array_equal(other.initial, simulation.initial)
    np.testing.assert_array_equal(other.targets, simulation.targets)


def test_exact_hexagonal_lattice():
    points, groups = hexagonal_targets(7, 0.4)
    assert len(points) == 169
    assert len(np.unique(points, axis=0)) == 169
    np.testing.assert_allclose(points.mean(axis=0), [0.5, WORLD_HEIGHT / 2])
    assert np.count_nonzero(groups == 0) == 1
    for shell in range(1, 8):
        assert np.count_nonzero(groups == shell) == 6 * shell
    distances = np.linalg.norm(points[:, None] - points[None, :], axis=2)
    np.fill_diagonal(distances, np.inf)
    np.testing.assert_allclose(distances.min(axis=1), 0.4 / 7)


def test_initial_disorder_and_progressive_convergence(simulation):
    times = [0, 2, 3, 4, 5, 6, simulation.config.settle_time]
    errors = [measure(simulation.sample(time))["rms_target_error"] for time in times]
    assert errors[0] > 0.2
    assert all(a > b for a, b in zip(errors, errors[1:]))
    initial = measure(simulation.sample(0))
    assert initial["min_center_distance"] > 2 * simulation.config.particle_radius
    assert initial["settled_fraction"] == 0


@pytest.mark.parametrize("seed", [0, 42, 1001, 2026])
def test_finite_visible_trajectories_and_exact_final_hold(seed):
    model = ChaosToOrder(SimulationConfig(seed=seed))
    for time in np.linspace(0, model.config.duration, 101):
        positions = model.sample(time).positions
        assert np.isfinite(positions).all()
        assert (positions > model.config.particle_radius).all()
        assert (positions[:, 0] < 1 - model.config.particle_radius).all()
        assert (positions[:, 1] < WORLD_HEIGHT - model.config.particle_radius).all()
    for time in [model.config.settle_time, model.config.duration, model.config.duration + 10]:
        np.testing.assert_array_equal(model.sample(time).positions, model.targets)


def test_smooth_arrival_without_a_terminal_snap(simulation):
    end = simulation.config.settle_time
    epsilon = 1e-3
    last_step = np.linalg.norm(simulation.sample(end - epsilon).positions - simulation.targets, axis=1).max()
    assert last_step < 1e-9
    assert measure(simulation.sample(end + 0.1), simulation.sample(end))["max_speed"] == 0
    # C1 continuity at each particle's blend onset, including ongoing drift.
    for index, onset in enumerate(simulation.onsets):
        before, at, after = [simulation.sample(t).positions[index] for t in (onset-epsilon, onset, onset+epsilon)]
        np.testing.assert_allclose((at-before)/epsilon, (after-at)/epsilon, atol=5e-5)


@pytest.mark.parametrize("time", [-1, float("nan"), float("inf")])
def test_invalid_sample_time(simulation, time):
    with pytest.raises(ValueError):
        simulation.sample(time)


@pytest.mark.parametrize("change", [dict(rings=0), dict(seed=-1), dict(rings=True),
    dict(particle_radius=0.04), dict(convergence_seconds=0), dict(hold_seconds=0),
    dict(drift_speed=float("nan")), dict(curve_strength=0.8)])
def test_invalid_simulation_settings(change):
    with pytest.raises(ValueError):
        SimulationConfig(**change)


@pytest.mark.parametrize("change", [dict(fps=0), dict(preview_width=361), dict(final_height=1080),
    dict(background="red"), dict(trail_seconds=float("inf")), dict(supersample=0)])
def test_invalid_render_settings(change):
    with pytest.raises(ValueError):
        RenderConfig(**change)


def test_config_rejects_typos_and_missing_sections(tmp_path):
    path = tmp_path / "invalid.toml"
    path.write_text("[simulation]\nsead = 1\n[render]\n")
    with pytest.raises(ValueError, match="invalid configuration"):
        load_config(path)
    path.write_text("[simulation]\n")
    with pytest.raises(ValueError, match="must contain"):
        load_config(path)
    with pytest.raises(ValueError, match="settled output frame"):
        Config(SimulationConfig(hold_seconds=0.001), RenderConfig())
