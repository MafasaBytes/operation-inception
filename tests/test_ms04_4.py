from pathlib import Path

import pytest

from inception.ms04_4 import GameRenderer, build_audio_log, load_settings
from inception.presentation import PresentationClock, build_plan, load_selected_candidate


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/ms04.4.toml"


def prepared():
    settings = load_settings(CONFIG)
    _, candidate = load_selected_candidate(ROOT / settings.search_output, settings.match_id)
    plan = build_plan(candidate, settings.clock)
    return settings, candidate, plan


def test_selected_genuine_match_maps_to_one_absolute_timeline():
    settings, candidate, plan = prepared()
    assert plan.match_id == settings.match_id
    assert plan.winner == candidate["final_state"]["winner"] == "cyan"
    assert len(plan.turn_start_times) == 87
    assert len(plan.events) == len(candidate["events"]) == 2601
    assert 39 < plan.duration_seconds < 41
    assert plan.events[1].time_seconds < .05
    first_placements = [item.time_seconds for item in plan.events if item.event.kind == "orb_placed"][:3]
    assert first_placements == pytest.approx([.035, .355, .675])
    assert tuple(item.event.sequence for item in plan.events) == tuple(range(len(plan.events)))
    assert all(b.time_seconds >= a.time_seconds for a, b in zip(plan.events, plan.events[1:]))


def test_event_reconstruction_matches_final_all_winner_board():
    _, candidate, plan = prepared()
    final = plan.state_at(plan.duration_seconds)
    expected = {
        tuple(item["cell"]): (item["owner"], item["orb_count"])
        for item in candidate["final_state"]["occupied_cells"]
    }
    actual = {
        topology.coordinate: (cell.owner, cell.orb_count)
        for topology, cell in zip(plan.grid.cells, final)
        if cell.owner is not None
    }
    assert actual == expected
    assert {cell.owner for cell in final if cell.owner is not None} == {"cyan"}
    assert sum(cell.orb_count for cell in final) == 87


def test_every_visual_transfer_has_an_adjacent_source_and_ordered_time():
    _, _, plan = prepared()
    receipts = [item for item in plan.events if item.event.kind == "orb_received"]
    assert len(receipts) == 780
    for item in receipts:
        assert item.source_cell in plan.grid.cell(item.event.cell).neighbors
        assert item.source_time_seconds is not None
        assert item.source_time_seconds < item.time_seconds


def test_audio_adapter_uses_real_match_and_filters_dense_redundancy():
    settings, _, plan = prepared()
    log = build_audio_log(plan, settings.audio)
    assert log.synthetic is False
    assert tuple(team.id for team in log.teams) == plan.players
    assert tuple(team.voice for team in log.teams) == (0, 1, 2)
    assert log.duration_seconds == plan.duration_seconds
    assert log.events[-1].kind == "winner_declared" and log.events[-1].team_id == "cyan"
    assert all(event.kind not in {"turn_started", "orb_received"} for event in log.events)
    assert all(event.previous_team_id is not None for event in log.events if event.kind == "neighbor_captured")
    assert all(
        event.orb_count / event.critical_mass >= settings.audio.charged_ratio_minimum
        for event in log.events if event.kind == "cell_charged"
    )
    assert len(log.events) < len(plan.events)


def test_renderer_is_deterministic_text_free_and_exact_phone_size():
    settings, _, plan = prepared()
    renderer = GameRenderer(plan, settings.render)
    opening = renderer.render(0)
    repeated = renderer.render(0)
    active = renderer.render(plan.turn_start_times[20] + .12)
    final = renderer.render(plan.winner_time + .55)
    assert opening.size == active.size == final.size == (720, 1280)
    assert opening.mode == active.mode == final.mode == "RGB"
    assert opening.tobytes() == repeated.tobytes()
    assert opening.tobytes() != active.tobytes() != final.tobytes()


def test_presentation_clock_is_independent_of_video_fps():
    settings, candidate, first = prepared()
    second = build_plan(candidate, PresentationClock(**vars(settings.clock)))
    assert first.events == second.events
    assert first.duration_seconds == second.duration_seconds
