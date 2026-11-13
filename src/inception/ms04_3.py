"""MS04.3 seeded candidate search over genuine deterministic matches."""

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import tempfile
import tomllib

from .matches import MatchResult, MatchScore, PolicySpec, score_match, simulate_match
from .rules import RulesConfig


CONFIG_SCHEMA = "ms04.3.search-config.v1"
OUTPUT_SCHEMA = "ms04.3.match-search.v1"


@dataclass(frozen=True)
class SearchConfig:
    search_id: str
    base_seed: int
    candidate_count: int
    max_turns: int
    rules: RulesConfig
    players: tuple[str, ...]
    policies: tuple[PolicySpec, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.search_id, str) or not self.search_id:
            raise ValueError("search_id must be nonempty")
        for name in ("base_seed", "candidate_count", "max_turns"):
            value = getattr(self, name)
            minimum = 0 if name == "base_seed" else 1
            if type(value) is not int or value < minimum:
                raise ValueError(f"invalid {name}")
        if self.candidate_count > 1000 or self.max_turns > 10_000:
            raise ValueError("candidate_count or max_turns exceeds the offline search ceiling")
        if type(self.players) is not tuple or not 2 <= len(self.players) <= 8 or len(set(self.players)) != len(self.players):
            raise ValueError("search requires two to eight unique players")
        if type(self.policies) is not tuple or len(self.policies) != len(self.players):
            raise ValueError("one immutable policy is required per player")
        if {policy.player_id for policy in self.policies} != set(self.players):
            raise ValueError("policy assignments must exactly match players")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_search_config(path: str | Path) -> SearchConfig:
    with Path(path).open("rb") as file:
        data = tomllib.load(file)
    if set(data) != {"schema_version", "search", "policies"} or data["schema_version"] != CONFIG_SCHEMA:
        raise ValueError("unsupported MS04.3 search configuration")
    search = data["search"]
    allowed = {"search_id", "base_seed", "candidate_count", "max_turns", "rows",
               "columns", "max_cascade_steps", "players"}
    if not isinstance(search, dict) or set(search) != allowed or not isinstance(data["policies"], list):
        raise ValueError("invalid MS04.3 search sections")
    policy_keys = {"player_id", "kind", "capture_weight", "explosion_weight",
                   "elimination_weight", "victory_weight", "charge_weight", "territory_weight"}
    if any(not isinstance(raw, dict) or set(raw) != policy_keys for raw in data["policies"]):
        raise ValueError("policy keys must match the MS04.3 contract")
    rules = RulesConfig(search["rows"], search["columns"], search["max_cascade_steps"])
    policies = tuple(PolicySpec(**raw) for raw in data["policies"])
    return SearchConfig(
        search_id=search["search_id"],
        base_seed=search["base_seed"],
        candidate_count=search["candidate_count"],
        max_turns=search["max_turns"],
        rules=rules,
        players=tuple(search["players"]),
        policies=policies,
    )


def run_search(config: SearchConfig) -> tuple[tuple[MatchResult, MatchScore], ...]:
    candidates = []
    for index in range(config.candidate_count):
        seed = config.base_seed + index
        match_id = f"{config.search_id}.seed-{seed}"
        match = simulate_match(
            match_id, config.players, config.policies, seed,
            config.max_turns, config.rules,
        )
        candidates.append((match, score_match(match)))
    return tuple(candidates)


def select_candidate(candidates: tuple[tuple[MatchResult, MatchScore], ...]) -> tuple[MatchResult, MatchScore]:
    if not candidates:
        raise ValueError("candidate search cannot be empty")
    completed = tuple(pair for pair in candidates if pair[0].completion_reason == "won")
    eligible = completed or candidates
    return sorted(eligible, key=lambda pair: (-pair[1].total, pair[0].seed))[0]


def _event_record(event) -> dict:
    record = asdict(event)
    if record["cell"] is not None:
        record["cell"] = list(record["cell"])
    return record


def _turn_record(turn) -> dict:
    record = asdict(turn)
    record["move"] = list(record["move"])
    record["ownership_counts"] = list(record["ownership_counts"])
    record["orb_counts"] = list(record["orb_counts"])
    record["eliminated"] = list(record["eliminated"])
    return record


def _final_state_record(match: MatchResult) -> dict:
    state = match.final_state
    occupied = []
    for topology, cell in zip(state.grid.cells, state.cells):
        if cell.owner is not None:
            occupied.append({"cell": list(topology.coordinate), "owner": cell.owner, "orb_count": cell.orb_count})
    return {
        "engine_outcome": state.outcome,
        "completion_reason": match.completion_reason,
        "winner": state.winner,
        "termination_reason": state.termination_reason,
        "turn_count": state.turn_index,
        "current_player": state.current_player,
        "eliminated": [player for player in state.players if player in state.eliminated],
        "total_orbs": state.total_orbs,
        "occupied_cells": occupied,
    }


def _candidate_record(match: MatchResult, score: MatchScore) -> dict:
    return {
        "match_id": match.match_id,
        "seed": match.seed,
        "policies": [asdict(policy) for policy in match.policies],
        "score": asdict(score),
        "final_state": _final_state_record(match),
        "turns": [_turn_record(turn) for turn in match.turns],
        "events": [_event_record(event) for event in match.events],
    }


def build_search_record(config_path: str | Path) -> dict:
    config_path = Path(config_path)
    config = load_search_config(config_path)
    candidates = run_search(config)
    selected_match, selected_score = select_candidate(candidates)
    ranking = sorted(candidates, key=lambda pair: (-pair[1].total, pair[0].seed))
    return {
        "schema_version": OUTPUT_SCHEMA,
        "search_id": config.search_id,
        "generated_offline": True,
        "genuine_rule_outcomes": True,
        "scripted_winner": False,
        "selected_match_id": selected_match.match_id,
        "selection_basis": (
            "highest transparent proxy score among completed matches; if none complete, "
            "highest score with unfinished outcome preserved"
        ),
        "configuration": {
            "base_seed": config.base_seed,
            "candidate_count": config.candidate_count,
            "max_turns": config.max_turns,
            "rules": asdict(config.rules),
            "players": list(config.players),
            "policies": [asdict(policy) for policy in config.policies],
        },
        "ranking": [
            {
                "rank": rank,
                "match_id": match.match_id,
                "seed": match.seed,
                "score": score.total,
                "completion_reason": match.completion_reason,
                "winner": match.final_state.winner,
                "turn_count": len(match.turns),
            }
            for rank, (match, score) in enumerate(ranking, start=1)
        ],
        "selected_score": asdict(selected_score),
        "candidates": [_candidate_record(match, score) for match, score in candidates],
        "source_sha256": {
            "config": _sha256(config_path),
            "grid": _sha256(Path(__file__).with_name("grid.py")),
            "rules": _sha256(Path(__file__).with_name("rules.py")),
            "matches": _sha256(Path(__file__).with_name("matches.py")),
            "search": _sha256(Path(__file__)),
        },
    }


def export_search(config: str | Path, output: str | Path, overwrite: bool = False) -> dict:
    output = Path(output)
    if output.exists() and not overwrite:
        raise FileExistsError("MS04.3 search output exists; use --overwrite for this output only")
    record = build_search_record(config)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".ms04.3-", dir=output.parent) as temporary:
        staged = Path(temporary) / output.name
        staged.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        staged.replace(output)
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description="Search seeded genuine MS04.3 matches")
    parser.add_argument("--config", type=Path, default=Path("configs/ms04.3.toml"))
    parser.add_argument("--output", type=Path, default=Path("outputs/ms04.3/ms04.3-search-v1.json"))
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    record = export_search(args.config, args.output, args.overwrite)
    selected = next(item for item in record["ranking"] if item["match_id"] == record["selected_match_id"])
    print(
        f"Selected {selected['match_id']} from {len(record['ranking'])} genuine candidates: "
        f"{selected['completion_reason']}, {selected['turn_count']} turns, score {selected['score']:.3f}"
    )


if __name__ == "__main__":
    main()
