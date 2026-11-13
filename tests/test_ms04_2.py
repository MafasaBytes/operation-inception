from dataclasses import replace
import hashlib
import json
from pathlib import Path

import pytest

from inception.ms04_2 import export_fixture, run_fixture
from inception.rules import (
    GameState,
    IllegalMoveError,
    OrbCell,
    RulesConfig,
    apply_move,
    create_game,
    legal_moves,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures/ms04.2/rules-v1.json"


def play(state, *moves):
    events = []
    for move in moves:
        result = apply_move(state, move)
        state = result.state
        events.extend(result.events)
    return state, tuple(events)


def test_requires_two_to_eight_unique_players():
    with pytest.raises(ValueError):
        create_game(("solo",))
    with pytest.raises(ValueError):
        create_game(tuple(f"p{index}" for index in range(9)))
    with pytest.raises(ValueError):
        create_game(("cyan", "cyan"))
    for count in range(2, 9):
        state = create_game(tuple(f"p{index}" for index in range(count)))
        assert len(state.players) == count and state.current_player == "p0"


def test_placement_is_legal_only_in_empty_or_owned_cells_and_turns_rotate():
    state = create_game(("cyan", "orange"))
    assert len(legal_moves(state)) == 54
    state = apply_move(state, (4, 2)).state
    assert state.current_player == "orange" and state.cell((4, 2)) == OrbCell("cyan", 1)
    assert (4, 2) not in legal_moves(state)
    with pytest.raises(IllegalMoveError, match="empty or owned"):
        apply_move(state, (4, 2))
    state = apply_move(state, (8, 5)).state
    assert state.current_player == "cyan"
    assert (4, 2) in legal_moves(state) and (8, 5) not in legal_moves(state)
    with pytest.raises(IllegalMoveError, match="outside"):
        apply_move(state, (9, 0))


def test_corner_explosion_converts_in_neighbor_order_then_eliminates_and_wins():
    state = create_game(("cyan", "orange"))
    state, _ = play(state, (0, 0), (0, 1))
    result = apply_move(state, (0, 0))
    state = result.state
    captures = [event for event in result.events if event.kind == "neighbor_captured"]
    assert [event.cell for event in captures] == [(0, 1), (1, 0)]
    assert [event.previous_owner for event in captures] == ["orange", None]
    receipts = [event for event in result.events if event.kind == "orb_received"]
    assert [event.cell for event in receipts] == [(0, 1), (1, 0)]
    assert [event.orb_count for event in receipts] == [2, 1]
    assert state.cell((0, 0)) == OrbCell()
    assert state.cell((0, 1)) == OrbCell("cyan", 2)
    assert state.cell((1, 0)) == OrbCell("cyan", 1)
    assert state.outcome == "won" and state.winner == "cyan"
    assert state.eliminated == frozenset({"orange"})
    kinds = [event.kind for event in result.events]
    assert kinds.index("cell_exploded") < kinds.index("player_eliminated") < kinds.index("winner_declared")
    assert legal_moves(state) == ()
    with pytest.raises(IllegalMoveError, match="ended"):
        apply_move(state, (0, 0))


def test_fifo_cascade_depth_and_event_identity_are_reproducible():
    moves = ((0, 0), (8, 5), (0, 1), (8, 4), (0, 1), (7, 5), (0, 0))
    first, first_events = play(create_game(("cyan", "orange")), *moves)
    second, second_events = play(create_game(("cyan", "orange")), *moves)
    assert first == second and first_events == second_events
    explosions = [event for event in first_events if event.kind == "cell_exploded"]
    assert [(event.cell, event.cascade_depth) for event in explosions] == [((0, 0), 0), ((0, 1), 1)]
    depth_events = [event for event in first_events if event.kind == "cascade_depth_increased"]
    assert [(event.cell, event.cascade_depth) for event in depth_events] == [((0, 1), 1)]
    assert [event.sequence for event in first_events] == list(range(len(first_events)))
    assert len({event.id for event in first_events}) == len(first_events)
    assert first.outcome == "active" and first.total_orbs == len(moves)
    assert all(cell.orb_count < len(topology.neighbors) for topology, cell in zip(first.grid.cells, first.cells))


def test_excess_orbs_are_retained_and_total_orbs_are_conserved():
    state = create_game(("cyan", "orange"))
    cells = list(state.cells)
    for coordinate in ((3, 3), (3, 4), (4, 3), (4, 4)):
        index = coordinate[0] * state.grid.columns + coordinate[1]
        cells[index] = OrbCell("cyan", 3)
    cells[8 * state.grid.columns + 5] = OrbCell("orange", 1)
    state = replace(state, cells=tuple(cells), has_played=(True, True))
    before = state.total_orbs
    result = apply_move(state, (3, 3))
    target_explosion = next(
        event for event in result.events
        if event.kind == "cell_exploded" and event.cell == (4, 4)
    )
    assert target_explosion.orb_count == 1
    assert result.state.total_orbs == before + 1
    assert result.state.cell((4, 4)).orb_count == 1


def test_elimination_waits_for_opening_completion_and_skips_eliminated_turns():
    state = create_game(("cyan", "orange", "violet"))
    state, _ = play(state, (0, 0), (0, 1))
    assert not state.opening_complete and not state.eliminated
    state = apply_move(state, (8, 5)).state
    assert state.opening_complete and state.current_player == "cyan"
    result = apply_move(state, (0, 0))
    assert result.state.eliminated == frozenset({"orange"})
    assert result.state.current_player == "violet"
    assert result.state.outcome == "active"


def test_step_limit_is_explicit_draw_and_rolls_back_attempted_move():
    rules = RulesConfig(max_cascade_steps=1)
    moves = ((0, 0), (8, 5), (0, 1), (8, 4), (0, 1), (7, 5))
    state, _ = play(create_game(("cyan", "orange"), rules), *moves)
    before_cells = state.cells
    before_orbs = state.total_orbs
    result = apply_move(state, (0, 0))
    assert result.state.outcome == "draw"
    assert result.state.termination_reason == "cascade_step_limit"
    assert result.state.winner is None and result.state.cells == before_cells
    assert result.state.total_orbs == before_orbs
    assert [event.kind for event in result.events] == ["turn_started", "cascade_aborted"]
    assert result.events[-1].reason == "cascade_step_limit"


def test_conformance_fixture_contains_genuine_legal_rule_sequences(tmp_path):
    record = run_fixture(FIXTURE)
    assert record["synthetic"] is True
    assert record["purpose"].startswith("rules conformance")
    scenarios = {scenario["id"]: scenario for scenario in record["scenarios"]}
    victory = scenarios["corner-capture-victory"]
    assert victory["final_state"]["winner"] == "cyan"
    assert victory["final_state"]["eliminated"] == ["orange"]
    cascade = scenarios["two-depth-cascade"]
    explosions = [event for event in cascade["events"] if event["kind"] == "cell_exploded"]
    assert [(event["cell"], event["cascade_depth"]) for event in explosions] == [([0, 0], 0), ([0, 1], 1)]

    output = tmp_path / "record.json"
    exported = export_fixture(FIXTURE, output)
    assert json.loads(output.read_text()) == exported
    assert exported == record
    assert exported["source_sha256"]["fixture"] == hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
    with pytest.raises(FileExistsError):
        export_fixture(FIXTURE, output)


def test_public_state_rejects_unsettled_cells():
    state = create_game(("cyan", "orange"))
    cells = list(state.cells)
    cells[0] = OrbCell("cyan", 2)
    with pytest.raises(ValueError, match="cascade-settled"):
        GameState(
            rules=state.rules,
            grid=state.grid,
            players=state.players,
            cells=tuple(cells),
            current_player_index=0,
            turn_index=0,
            has_played=(False, False),
            eliminated=frozenset(),
        )
