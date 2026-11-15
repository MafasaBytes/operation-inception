"""One directed PB-1.1 setup and nearby robustness audit, not a candidate search."""
from __future__ import annotations

from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path

from .pressure_bloom import Ball, Parameters, Result, encoded, simulate

SCHEMA = "ms06.3.directed-pressure-bloom.v1"
VALID = {"rupture", "containment", "extinction"}


def digest(value) -> str:
    return hashlib.sha256(encoded(value).encode()).hexdigest()


def load_scenario(path: Path) -> dict:
    cfg = json.loads(path.read_text(encoding="utf-8"))
    if cfg["schema"] != SCHEMA or cfg["rules"] != "PB-1.1":
        raise ValueError("Unsupported directed Pressure Bloom scenario")
    if not 30 <= len(cfg["balls"]) <= 48:
        raise ValueError("The directed prototype needs 30–48 initial balls")
    return cfg


def run(cfg: dict, label: str = "base") -> Result:
    return simulate(tuple(Ball(**b) for b in cfg["balls"]), Parameters(**cfg["parameters"]),
                    seed=cfg["seed"], run_id=f"{cfg['id']}.{label}")


def finite_tree(value) -> bool:
    if isinstance(value, dict):
        return all(finite_tree(v) for v in value.values())
    if isinstance(value, (tuple, list)):
        return all(finite_tree(v) for v in value)
    if isinstance(value, float):
        return math.isfinite(value)
    return value not in ("nan", "inf", "-inf")


def summarize(result: Result) -> dict:
    final = json.loads(result.final)
    events = [e.to_dict() for e in result.events]
    times = {kind: [e["time"] for e in events if e["kind"] == kind]
             for kind in sorted({e["kind"] for e in events})}
    splits, crushes = times.get("ball_split", []), times.get("ball_crushed", [])
    samples = [json.loads(s) for s in result.samples]
    finite = finite_tree(final) and finite_tree(json.loads(result.initial))
    finite = finite and all(finite_tree(s) for s in samples)
    return {"outcome": final["outcome"], "reason": final["reason"], "terminal_time": final["time"],
            "presentation_eligible": final["presentation_eligible"], "finite": finite,
            "first_contact": final["first_contact"], "event_times": times,
            "event_counts": dict(sorted(Counter(e.kind for e in result.events).items())),
            "peak_live_count": max([s["live_count"] for s in samples]+[final["live_count"]]),
            "split_then_crush": bool(splits and any(t > splits[0] for t in crushes)),
            "final_by_lineage": dict(sorted(Counter(b["lineage"] for b in final["balls"]).items())),
            "final_by_generation": dict(sorted(Counter(str(b["generation"]) for b in final["balls"]).items())),
            "phase_samples": [{"time": s["time"], "actual_height": s["height"],
                               "live_count": s["live_count"], "occupied_area": s["occupied_area"],
                               "occupied_fraction": s["occupied_area"]/(result.parameters.width*s["height"]),
                               "max_load": max((a["L"] for a in s["loads"].values()), default=0.)}
                              for s in samples if s["tick"] % 120 == 0],
            "simulation_sha256": digest(result.to_dict()),
            "event_sha256": digest(events), "final_state": final}


def nearby_probes(cfg: dict) -> tuple[tuple[str, dict], ...]:
    """Exactly eight declared local perturbations; no ranking or selection."""
    probes = []
    for axis in ("x", "y"):
        for sign in (-1, 1):
            p = deepcopy(cfg)
            for i, b in enumerate(p["balls"]):
                b[axis] += sign*.0015*(-1 if i % 2 else 1)
            probes.append((f"alternating-{axis}-{sign:+d}", p))
    for factor in (.97, 1.03):
        p = deepcopy(cfg)
        p["parameters"]["schedule"] = [[t/factor, h] for t, h in p["parameters"]["schedule"]]
        probes.append((f"piston-speed-{factor:.2f}", p))
    p = deepcopy(cfg)
    mean_y = sum(b["y"] for b in p["balls"])/len(p["balls"])
    for b in p["balls"]:
        b["y"] = mean_y+(b["y"]-mean_y)*1.003
    probes.append(("vertical-gap-plus-0.3-percent", p))
    p = deepcopy(cfg)
    p["parameters"]["schedule"] = [[t+1/120 if t else 0., h]
                                        for t, h in p["parameters"]["schedule"]]
    probes.append(("engagement-plus-one-tick", p))
    return tuple(probes)


def timing_gate(summary: dict) -> dict:
    t = summary["event_times"]
    splits, crushes = t.get("ball_split", []), t.get("ball_crushed", [])
    first_contact = summary["first_contact"]
    # This gate checks opportunities to review, never audience satisfaction.
    return {"valid_decisive_base": summary["outcome"] in {"rupture", "containment"},
            "contact_by_half_second": bool(first_contact and first_contact["time"] <= .5),
            "first_split_1_to_1_5": bool(splits and 1. <= splits[0] <= 1.5),
            "continued_early_middle_splits": sum(1.5 < t <= 7 for t in splits) >= 3,
            "danger_by_5_to_7": any(5 <= s["time"] <= 7 and s["max_load"] >= .9
                                      for s in summary["phase_samples"]),
            "genuine_reversal": bool(splits and any(splits[0] < t < summary["terminal_time"] for t in crushes)),
            "resolution_13_to_16": 13 <= summary["terminal_time"] <= 16,
            "video_duration_14_to_18": 14 <= math.ceil((summary["terminal_time"]+.6)*30)/30 <= 18}


def _check_case(item):
    name, scenario = item
    print(f"PB robustness: {name} simulation", flush=True)
    result = run(scenario, name)
    summary = summarize(result)
    print(f"PB robustness: {name} replay ({summary['outcome']}, {summary['terminal_time']:.3f}s)", flush=True)
    replay = run(scenario, name)
    record = {"probe": name, "configuration": scenario, "parameters": asdict(result.parameters),
              "deterministic": result == replay, **summary,
              "semantic_events": [{"id": e.id, "sequence": e.sequence, "tick": e.tick,
                                   "kind": e.kind, "payload": json.loads(e.payload)} for e in result.events]}
    print(f"PB robustness: {name} checked", flush=True)
    return record, result if name == "base" else None


def robustness_audit(cfg: dict) -> tuple[dict, Result]:
    # Four local processes bound this single fixed audit's runtime. There is no
    # seed search, candidate ranking, policy or reusable generation framework.
    with ProcessPoolExecutor(max_workers=4) as pool:
        checked = list(pool.map(_check_case, (("base", cfg), *nearby_probes(cfg))))
    results = [record for record, _ in checked]
    base = checked[0][1]
    probes = results[1:]
    base_timing = timing_gate(results[0])
    gate = {"base_valid": results[0]["outcome"] in VALID,
            "base_timing": all(base_timing.values()),
            "base_deterministic": results[0]["deterministic"],
            "all_probes_deterministic": all(p["deterministic"] for p in probes),
            "all_finite": all(p["finite"] for p in results),
            "six_valid_probes": sum(p["outcome"] in VALID for p in probes) >= 6,
            "no_more_than_two_failed_probes": sum(p["outcome"] not in VALID for p in probes) <= 2,
            "five_split_then_crush_probes": sum(p["split_then_crush"] for p in probes) >= 5}
    return {"schema": "ms06.3.robustness.v1", "rules": "PB-1.1", "scenario_sha256": digest(cfg),
            "engine_sha256": hashlib.sha256(Path(__file__).with_name("pressure_bloom.py").read_bytes()).hexdigest(),
            "status": "directed PB-1.1 prototype; not automatically generated candidate",
            "passed": all(gate.values()), "gate": gate, "base_timing": base_timing,
            "results": results}, base
