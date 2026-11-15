"""PB-1.1 conformance: genuine transitions, no presentation or fixture overrides."""
import ast
from dataclasses import FrozenInstanceError, replace
import importlib.util
import json
import math
from pathlib import Path

import pytest

from inception.ms06_2 import assert_expected, load_fixture, run_scenario
from inception.pressure_bloom import Ball, Parameters, encoded, simulate

FIXTURE = Path(__file__).parents[1] / "fixtures/ms06.2/conformance-v1.json"


@pytest.fixture(scope="module")
def runs():
    data = load_fixture(FIXTURE)
    return {s["id"]: (s, run_scenario(s)) for s in data["scenarios"]}


def final(runs, name):
    return json.loads(runs[name][1].final)


def events(runs, name, kind):
    return [e.to_dict() for e in runs[name][1].events if e.kind == kind]


def test_all_conformance_expectations(runs):
    for scenario, result in runs.values():
        assert_expected(scenario, result)


def test_reproducible_immutable_log_and_fps_independence(runs):
    # FPS is deliberately absent from the engine input, not a simulation setting.
    s, reference = runs["rupture-release"]
    assert run_scenario(s) == reference
    s, reference = runs["crowding-reversal"]
    assert run_scenario(s) == reference
    # A consumer at any rate reads the same .5-second state, tick60. It cannot
    # introduce half-frames into any of the transition times in the truth log.
    at_half_second = [reference.samples[round((fps/2)/fps*120)-1] for fps in (24, 30, 60)]
    assert len(set(at_half_second)) == 1
    with pytest.raises(FrozenInstanceError):
        reference.events[0].kind = "fabricated"
    with pytest.raises(TypeError):
        Parameters(fps=30)


def test_continuous_earned_load_and_clocks(runs):
    r = runs["ordinary-multiplication"][1]
    initial = json.loads(r.initial)
    assert initial["first_contact"] == {"height": .88, "tick": 0, "time": 0.}
    assert initial["loads"]["r000"]["D"] == initial["loads"]["r000"]["L"] == 0
    samples = [json.loads(s) for s in r.samples[:84]]
    drives = [s["loads"]["r000"]["D"] for s in samples[:-1]]
    assert all(0 <= b-a <= 1/48+1e-12 for a, b in zip(drives, drives[1:]))
    assert sum(0 < d < 1 for d in drives) >= 46
    for s in samples[:-1]:
        a = s["loads"]["r000"]
        assert a["C"] == 1 and a["weight"] == 2
        assert a["D"] == pytest.approx((.88-s["height"])/.16)
        assert a["L"] == a["C"]*a["D"]*min(1, a["weight"]/4)
    split = events(runs, "ordinary-multiplication", "ball_split")[0]
    assert split["tick"] == 84
    assert split["before"]["clocks"]["r000:split"] == 36
    assert samples[47]["clocks"]["r000:split"] == 0


def test_child_geometry_area_lineage_and_relaxation(runs):
    e = events(runs, "ordinary-multiplication", "ball_split")[0]
    p = e["payload"]
    children = p["birth_children"]
    parent = p["parent"]
    a, b = children
    assert math.hypot(a["x"]-b["x"], a["y"]-b["y"]) == pytest.approx(1.3*parent["radius"])
    assert p["initial_overlap"] == pytest.approx(.2*parent["radius"])
    assert p["relaxation_resolved"]
    a, b = p["relaxed_children"]
    assert (a["x"], a["y"], b["x"], b["y"]) == pytest.approx((.44,.64,.56,.64))
    assert sum(c["radius"]**2 for c in children)/parent["radius"]**2 == pytest.approx(1.125)
    for c in children:
        assert c["lineage"] == parent["lineage"]
        assert c["generation"] == parent["generation"]+1
        assert c["parent_generation"] == parent["generation"]
        assert c["parent"] == parent["id"]
        assert c["radius"] == .75*parent["radius"]
    assert e["after"]["retired"][parent["id"]]["status"] == "split"


def test_crush_releases_real_area_and_load(runs):
    es = events(runs, "crowding-reversal", "ball_crushed")
    assert [e["tick"] for e in es] == [126,126]
    assert [e["payload"]["ball"]["id"] for e in es] == ["r000.0", "r000.1"]
    for e in es:
        assert e["after"]["occupied_area"] < e["before"]["occupied_area"]
        assert e["after"]["live_count"] == e["before"]["live_count"]-1
        assert e["payload"]["qualification"]["L"] == pytest.approx(1)
    assert es[0]["after"]["loads"]["r000.1"]["L"] == pytest.approx(.75)
    assert es[1]["after"]["loads"]["r001"]["L"] == 0
    f = final(runs, "crowding-reversal")
    assert [b["lineage"] for b in f["balls"]] == ["orange"]
    assert f["outcome"] == "containment"  # no invented orange team victory


def test_latched_crush_cannot_cancel_rupture(runs):
    r = runs["same-tick-crush-rupture"][1]
    es = [e.to_dict() for e in r.events if e.tick == 162 and e.kind in ("ball_crushed", "wall_ruptured")]
    assert [e["kind"] for e in es] == ["ball_crushed", "wall_ruptured"]
    assert es[0]["after"]["walls"]["L0"]["W"] < .8
    assert es[1]["payload"]["qualification"]["W"] >= .8
    assert es[1]["after"]["locked_outcome"] == "rupture"
    assert es[1]["after"]["mode"] == "release"


def test_release_clocks_stop_and_escapes_are_geometric(runs):
    r = runs["rupture-release"][1]
    rupture = events(runs, "rupture-release", "wall_ruptured")[0]
    after = [e for e in r.events if e.sequence > rupture["sequence"]]
    assert {e.kind for e in after} <= {"ball_escaped", "rupture_resolved"}
    for s in map(json.loads, r.samples):
        if s["tick"] >= rupture["tick"]:
            assert s["height"] == rupture["after"]["height"]
            assert not s["clocks"] and not s["wall_clocks"]
            assert all(a["L"] == 0 for a in s["loads"].values())
    es = events(runs, "rupture-release", "ball_escaped")
    assert len(es) == 4
    for e in es:
        b = next(b for b in e["after"]["balls"] if b["id"] == e["payload"]["ball"])
        assert b["x"]+b["radius"] <= 0 and b["status"] == "escaped"
        assert e["payload"]["previous_position"][0]+b["radius"] > 0
    f = final(runs, "rupture-release")
    assert f["tick"]-rupture["tick"] == 72
    assert f["escaped_count"] == f["live_count"] == 4


def test_generation_capacity_and_exclusive_honest_outcomes(runs):
    for name, (_, r) in runs.items():
        f = json.loads(r.final)
        assert f["outcome"] in ("rupture", "containment", "extinction", "draw", "invalid")
        if f["outcome"] in ("draw", "invalid"):
            assert f["reason"] and not f["presentation_eligible"]
            assert not any(e.kind in ("rupture_resolved", "chamber_contained", "population_extinct") for e in r.events)
        for s in map(json.loads, r.samples):
            assert len(s["balls"]) <= 96
            assert all(0 <= b["generation"] <= 3 for b in s["balls"])
    for name in ("generation-limit", "live-cap"):
        assert not events(runs, name, "ball_split")
    assert final(runs, "live-cap")["live_count"] == 96
    assert final(runs, "extinction")["live_count"] == 0
    assert final(runs, "late-valid-containment")["outcome"] == "containment"
    assert not final(runs, "late-valid-containment")["presentation_eligible"]


def test_sequences_reconstruct_transitions_and_replay_state(runs):
    for _, r in runs.values():
        assert [e.sequence for e in r.events] == list(range(len(r.events)))
        assert len({e.id for e in r.events}) == len(r.events)
        assert [e.tick for e in r.events] == sorted(e.tick for e in r.events)
        for e in r.events:
            b, a = json.loads(e.before), json.loads(e.after)
            if e.kind == "ball_split":
                p = json.loads(e.payload)
                assert p["parent"]["id"] in {x["id"] for x in b["balls"]}
                assert p["parent"]["id"] not in {x["id"] for x in a["balls"]}
                assert {x["id"] for x in p["birth_children"]} <= {x["id"] for x in a["balls"]}
            elif e.kind == "ball_crushed":
                k = json.loads(e.payload)["ball"]["id"]
                assert k in {x["id"] for x in b["balls"]}
                assert k not in {x["id"] for x in a["balls"]}
        if r.samples:
            assert r.samples[-1] == r.final
        assert len(r.events) <= r.parameters.max_events


def test_reordering_input_cannot_rewrite_results(runs):
    s = runs["rupture-release"][0]
    assert run_scenario({**s, "balls": list(reversed(s["balls"]))}) == runs["rupture-release"][1]


def test_invalid_numeric_diagnostics_do_not_repair_input(runs):
    f = final(runs, "invalid-nonfinite")
    assert f["balls"][0]["x"] == "nan"
    assert f["outcome"] == "invalid"
    r = simulate((Ball("r000", "cyan", .5, .8),), replace(Parameters(), drive_ramp_distance=float("nan")))
    assert json.loads(r.final)["outcome"] == "invalid"
    json.loads(encoded(r.to_dict()))  # portable JSON diagnostics, not NaN JSON


def test_incomplete_release_cannot_masquerade_as_resolved_rupture(runs):
    scenario = runs["rupture-release"][0]
    r = run_scenario({**scenario, "parameters": {**scenario["parameters"], "max_ticks": 200}})
    f = json.loads(r.final)
    assert f["outcome"] == "draw" and f["locked_outcome"] == "rupture"
    assert f["reason"] == "duration_limit" and not f["presentation_eligible"]
    assert f["escaped_count"] == 3
    assert not any(e.kind == "rupture_resolved" for e in r.events)
    assert json.loads(r.events[-1].payload)["release_incomplete"]


def test_birth_crowding_has_bounded_honest_failure():
    # Symmetric horizontal projection stalls below the severe penetration
    # threshold. Do not rotate/shrink children to manufacture a valid packing.
    p = Parameters(width=.22, schedule=((0., .88), (.4, .72)), max_ticks=240)
    r = simulate((Ball("r000", "cyan", .11, .8),), p)
    f = json.loads(r.final)
    assert f["outcome"] == "draw" and f["reason"] == "finite_packing_stall"
    birth = next(e.to_dict() for e in r.events if e.kind == "ball_split")
    assert not birth["payload"]["relaxation_resolved"]
    assert f["tick"]-birth["tick"] == 30
    assert len(f["balls"]) == 2 and all(b["radius"] == .06 for b in f["balls"])


def test_finite_diagnostic_budgets_and_ancestry():
    balls = (Ball("r000", "cyan", .5, .8),)
    cases = (replace(Parameters(), schedule=()), replace(Parameters(), max_ticks=2161),
             replace(Parameters(), max_events=20001))
    for p in cases:
        r = simulate(balls, p)
        assert json.loads(r.final)["outcome"] == "invalid"
    bad = replace(balls[0], generation=3, parent="r000.0.0", parent_generation=2)
    assert json.loads(simulate((bad,)).final)["reason"] == "invalid_generation_radius"


def test_rules_imports_only_standard_library():
    source = Path(importlib.util.find_spec("inception.pressure_bloom").origin).read_text()
    tree = ast.parse(source)
    imports = {node.module.split('.')[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    imports |= {n.name.split('.')[0] for node in ast.walk(tree) if isinstance(node, ast.Import) for n in node.names}
    assert imports <= {"__future__", "dataclasses", "json", "math"}
