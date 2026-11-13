from pathlib import Path
from types import SimpleNamespace

import pytest

from inception.matches import PolicySpec, choose_move, score_match, simulate_match
from inception.ms04_3 import (
    build_search_record,
    export_search,
    load_search_config,
    select_candidate,
)
from inception.rules import RulesConfig, apply_move, create_game


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/ms04.3.toml"


def policies(players, kind="random"):
    return tuple(PolicySpec(player, kind) for player in players)


def small_config(path: Path, *, base_seed=700, candidate_count=2, max_turns=12):
    path.write_text(f'''schema_version = "ms04.3.search-config.v1"

[search]
search_id = "test.search.v1"
base_seed = {base_seed}
candidate_count = {candidate_count}
max_turns = {max_turns}
rows = 9
columns = 6
max_cascade_steps = 1000
players = ["cyan", "orange"]

[[policies]]
player_id = "cyan"
kind = "random"
capture_weight = 3.0
explosion_weight = 1.5
elimination_weight = 18.0
victory_weight = 40.0
charge_weight = 1.0
territory_weight = 1.25

[[policies]]
player_id = "orange"
kind = "random"
capture_weight = 3.0
explosion_weight = 1.5
elimination_weight = 18.0
victory_weight = 40.0
charge_weight = 1.0
territory_weight = 1.25
''', encoding="utf-8")


def test_search_configuration_assigns_equal_tactical_policies():
    config = load_search_config(CONFIG)
    assert config.players == ("cyan", "orange", "violet")
    assert config.candidate_count == 12 and config.max_turns == 240
    assert {policy.kind for policy in config.policies} == {"tactical"}
    weights = {
        (policy.capture_weight, policy.explosion_weight, policy.elimination_weight,
         policy.victory_weight, policy.charge_weight, policy.territory_weight)
        for policy in config.policies
    }
    assert len(weights) == 1


def test_same_seed_reproduces_complete_match_and_different_seed_changes_moves():
    players = ("cyan", "orange", "violet")
    specs = policies(players)
    first = simulate_match("same", players, specs, 91, 30)
    second = simulate_match("same", players, specs, 91, 30)
    different = simulate_match("different", players, specs, 92, 30)
    assert first == second
    assert tuple(turn.move for turn in first.turns) != tuple(turn.move for turn in different.turns)
    assert tuple(event.sequence for event in first.events) == tuple(range(len(first.events)))


def test_complete_log_replays_to_identical_final_state_and_events():
    players = ("cyan", "orange")
    match = simulate_match("replay", players, policies(players, "tactical"), 123, 50)
    state = create_game(players)
    replayed_events = []
    for turn in match.turns:
        assert state.current_player == turn.player_id
        result = apply_move(state, turn.move)
        state = result.state
        replayed_events.extend(result.events)
    assert state == match.final_state
    assert tuple(replayed_events) == match.events


def test_turn_limit_is_preserved_without_invented_winner():
    players = ("cyan", "orange")
    match = simulate_match("short", players, policies(players), 11, 1)
    assert match.completion_reason == "turn_limit"
    assert match.final_state.outcome == "active" and match.final_state.winner is None
    assert all(event.kind != "winner_declared" for event in match.events)
    score = score_match(match)
    assert score.completion_points == -12


def test_simulation_supports_two_to_eight_competitors():
    for count in range(2, 9):
        players = tuple(f"p{index}" for index in range(count))
        match = simulate_match(f"players-{count}", players, policies(players), 100 + count, count + 2)
        assert match.final_state.players == players
        assert len(match.turns) == count + 2
        assert match.final_state.total_orbs == count + 2


def test_tactical_choice_is_seeded_and_legal():
    import random

    state = create_game(("cyan", "orange"))
    policy = PolicySpec("cyan", "tactical")
    first = choose_move(state, policy, random.Random(9))
    second = choose_move(state, policy, random.Random(9))
    assert first == second
    assert first in tuple(cell.coordinate for cell in state.grid.cells)
    with pytest.raises(ValueError, match="current player"):
        choose_move(state, PolicySpec("orange", "tactical"), random.Random(9))


def test_selection_prefers_completed_genuine_match_over_higher_unfinished_proxy():
    unfinished = SimpleNamespace(completion_reason="turn_limit", seed=1)
    completed = SimpleNamespace(completion_reason="won", seed=2)
    high = SimpleNamespace(total=100.0)
    lower = SimpleNamespace(total=20.0)
    assert select_candidate(((unfinished, high), (completed, lower))) == (completed, lower)


def test_export_is_deterministic_complete_and_refuses_overwrite(tmp_path):
    config = tmp_path / "search.toml"
    small_config(config)
    first_path = tmp_path / "first.json"
    second_path = tmp_path / "second.json"
    first = export_search(config, first_path)
    second = export_search(config, second_path)
    assert first == second
    assert first_path.read_bytes() == second_path.read_bytes()
    assert first["genuine_rule_outcomes"] is True and first["scripted_winner"] is False
    assert len(first["candidates"]) == 2
    for candidate in first["candidates"]:
        sequences = [event["sequence"] for event in candidate["events"]]
        assert sequences == list(range(len(sequences)))
        assert len(candidate["turns"]) == candidate["final_state"]["turn_count"]
    with pytest.raises(FileExistsError):
        export_search(config, first_path)


def test_build_record_preserves_unfinished_selection_if_no_candidate_finishes(tmp_path):
    config = tmp_path / "search.toml"
    small_config(config, candidate_count=3, max_turns=1)
    record = build_search_record(config)
    assert all(item["completion_reason"] == "turn_limit" for item in record["ranking"])
    selected = next(item for item in record["ranking"] if item["match_id"] == record["selected_match_id"])
    assert selected["winner"] is None
    assert record["selection_basis"].endswith("unfinished outcome preserved")
