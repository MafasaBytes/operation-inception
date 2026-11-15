"""Run the versioned logical PB conformance fixtures; never imports media tools."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from .pressure_bloom import Ball, Parameters, Result, encoded, simulate


def load_fixture(path: Path) -> dict:
    fixture = json.loads(path.read_text(encoding="utf-8"))
    if fixture["schema"] != "pressure-bloom-conformance-v1" or fixture["rules"] != "PB-1.1":
        raise ValueError("Unsupported Pressure Bloom fixture")
    return fixture


def run_scenario(scenario: dict) -> Result:
    params = dict(scenario["parameters"])
    params["schedule"] = tuple(tuple(pair) for pair in params["schedule"])
    balls = []
    for spec in scenario["balls"]:
        fields = dict(spec)
        if fields["x"] == "nan":
            fields["x"] = float("nan")  # Explicit invalid-input probe, never hidden pressure.
        balls.append(Ball(**fields))
    return simulate(tuple(balls), Parameters(**params), seed=scenario["seed"], run_id=scenario["id"])


def assert_expected(scenario: dict, result: Result) -> None:
    final = json.loads(result.final)
    for key, expected in scenario["expected"].items():
        if key.endswith("_ticks"):
            kind = {"split_ticks": "ball_split", "crush_ticks": "ball_crushed",
                    "rupture_ticks": "wall_ruptured", "escape_ticks": "ball_escaped"}[key]
            actual = [e.tick for e in result.events if e.kind == kind]
        else:
            actual = final["tick" if key == "final_tick" else key]
        if actual != expected:
            raise AssertionError(f"{scenario['id']} {key}: {actual!r} != {expected!r}")


def conformance(path: Path) -> dict:
    fixture = load_fixture(path)
    results = []
    for scenario in fixture["scenarios"]:
        result = run_scenario(scenario)
        assert_expected(scenario, result)
        results.append(result.to_dict())
    return {"schema": "pressure-bloom-conformance-result-v1", "rules": "PB-1.1",
            "fixture_sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "runs": results}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=Path("fixtures/ms06.2/conformance-v1.json"))
    parser.add_argument("--output", type=Path, default=Path("outputs/ms06.2/ms06.2-conformance-v1.json"))
    args = parser.parse_args()
    record = conformance(args.fixture)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(encoded(record)+"\n", encoding="utf-8")
    print(f"{len(record['runs'])} conformance scenarios passed: {args.output}")


if __name__ == "__main__":
    main()
