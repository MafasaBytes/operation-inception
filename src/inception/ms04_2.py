"""Run versioned, hand-authored MS04.2 rule-conformance scenarios."""

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import tempfile

from .rules import RulesConfig, apply_move, create_game


FIXTURE_SCHEMA = "ms04.2.rules-fixture.v1"
OUTPUT_SCHEMA = "ms04.2.rules-conformance.v1"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_fixture(path: str | Path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or set(data) != {"schema_version", "fixture_id", "synthetic", "scenarios"}:
        raise ValueError("invalid MS04.2 fixture fields")
    if data["schema_version"] != FIXTURE_SCHEMA or data["synthetic"] is not True:
        raise ValueError("MS04.2 conformance fixtures must be versioned and synthetic")
    if not isinstance(data["fixture_id"], str) or not data["fixture_id"]:
        raise ValueError("fixture_id must be nonempty")
    if not isinstance(data["scenarios"], list) or not data["scenarios"]:
        raise ValueError("fixture requires scenarios")
    for scenario in data["scenarios"]:
        if set(scenario) != {"id", "players", "max_cascade_steps", "moves"}:
            raise ValueError("invalid conformance scenario fields")
        if not isinstance(scenario["id"], str) or not scenario["id"]:
            raise ValueError("scenario id must be nonempty")
        if not isinstance(scenario["players"], list) or not isinstance(scenario["moves"], list):
            raise ValueError("scenario players and moves must be lists")
        for move in scenario["moves"]:
            if set(move) != {"player_id", "cell"} or not isinstance(move["cell"], list) or len(move["cell"]) != 2:
                raise ValueError("each move requires player_id and a two-value cell")
    return data


def _state_record(state) -> dict:
    occupied = []
    for topology, cell in zip(state.grid.cells, state.cells):
        if cell.owner is not None:
            occupied.append({"cell": list(topology.coordinate), "owner": cell.owner, "orb_count": cell.orb_count})
    return {
        "turn_count": state.turn_index,
        "outcome": state.outcome,
        "winner": state.winner,
        "termination_reason": state.termination_reason,
        "current_player": state.current_player,
        "eliminated": [player for player in state.players if player in state.eliminated],
        "total_orbs": state.total_orbs,
        "occupied_cells": occupied,
    }


def run_fixture(path: str | Path) -> dict:
    path = Path(path)
    fixture = load_fixture(path)
    records = []
    for scenario in fixture["scenarios"]:
        rules = RulesConfig(max_cascade_steps=scenario["max_cascade_steps"])
        state = create_game(tuple(scenario["players"]), rules)
        events = []
        for move_number, move in enumerate(scenario["moves"]):
            if move["player_id"] != state.current_player:
                raise ValueError(
                    f"scenario {scenario['id']} move {move_number} expected {state.current_player}, "
                    f"not {move['player_id']}"
                )
            result = apply_move(state, tuple(move["cell"]))
            state = result.state
            for event in result.events:
                event_record = asdict(event)
                if event_record["cell"] is not None:
                    event_record["cell"] = list(event_record["cell"])
                events.append(event_record)
        records.append({
            "id": scenario["id"],
            "players": scenario["players"],
            "moves": scenario["moves"],
            "final_state": _state_record(state),
            "events": events,
        })
    return {
        "schema_version": OUTPUT_SCHEMA,
        "fixture_id": fixture["fixture_id"],
        "synthetic": True,
        "purpose": "rules conformance only; not a content candidate or automated match",
        "decisions": {
            "coordinates": "zero-based row,column",
            "neighbor_order": ["north", "east", "south", "west"],
            "cascade_order": "FIFO",
            "excess_orbs": "subtract critical mass per explosion and retain residual",
            "ownership": "incoming orb converts the receiving cell immediately",
            "elimination": "after settlement and only once every player has completed a first turn",
            "victory": "sole active player after settlement",
            "non_termination": "repeat detection or step limit; attempted move rolled back as explicit draw",
        },
        "source_sha256": {
            "fixture": _sha256(path),
            "grid": _sha256(Path(__file__).with_name("grid.py")),
            "rules": _sha256(Path(__file__).with_name("rules.py")),
            "runner": _sha256(Path(__file__)),
        },
        "scenarios": records,
    }


def export_fixture(fixture: str | Path, output: str | Path, overwrite: bool = False) -> dict:
    output = Path(output)
    if output.exists() and not overwrite:
        raise FileExistsError("MS04.2 conformance output exists; use --overwrite for this output only")
    record = run_fixture(fixture)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".ms04.2-", dir=output.parent) as temporary:
        staged = Path(temporary) / output.name
        staged.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        staged.replace(output)
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description="Run static MS04.2 rule-conformance scenarios")
    parser.add_argument("--fixture", type=Path, default=Path("fixtures/ms04.2/rules-v1.json"))
    parser.add_argument("--output", type=Path, default=Path("outputs/ms04.2/ms04.2-conformance-v1.json"))
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    record = export_fixture(args.fixture, args.output, args.overwrite)
    print(f"Saved {len(record['scenarios'])} MS04.2 conformance scenarios to {args.output}")


if __name__ == "__main__":
    main()
