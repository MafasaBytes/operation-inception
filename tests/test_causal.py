"""One focused reliability check for the delivered 001B choreography."""

import numpy as np

from inception.causal import CausalAssembly
from inception.config import load_config


def test_causal_delivery_clearance_and_final_settling():
    cfg = load_config("configs/experiment001b.toml")
    model = CausalAssembly(cfg.simulation)
    repeat = CausalAssembly(cfg.simulation)
    np.testing.assert_array_equal(model.sample(2.5).positions, repeat.sample(2.5).positions)
    assert [int(model.sample(t).completion.sum()) for t in (1, 2.5, 4)] == [7, 43, 85]
    for i, parent in enumerate(model.parents):
        if parent >= 0:
            assert model.locks[parent] <= model.starts[i] + 1e-10
            assert np.linalg.norm(model.targets[i]-model.targets[parent]) <= cfg.simulation.target_radius/5*1.001
    for time in np.arange(186)/30:
        frame = model.sample(time)
        assert np.sum((time >= model.starts) & (time < model.locks)) <= 6
        distances = np.linalg.norm(frame.positions[:, None]-frame.positions[None, :], axis=2)
        diameters = frame.radii*frame.scales
        np.fill_diagonal(distances, np.inf)
        assert np.all(distances > diameters[:, None]+diameters[None, :])
    assert int(model.sample(4.3).completion.sum()) == 90
    for time in (5.8, 6.0, 6.2):
        frame = model.sample(time)
        np.testing.assert_array_equal(frame.positions, model.targets)
        np.testing.assert_array_equal(frame.activation, 0)
        np.testing.assert_array_equal(frame.scales, 1)
        np.testing.assert_array_equal(frame.brightness, 1)
