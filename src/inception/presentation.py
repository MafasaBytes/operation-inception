"""MS04.4 absolute-time mapping and event-driven board reconstruction."""

from bisect import bisect_right
from dataclasses import dataclass
import json
import math
from pathlib import Path

from .grid import Coordinate, Grid, build_grid
from .rules import GameEvent, OrbCell


@dataclass(frozen=True)
class PresentationClock:
    intro_seconds: float = 0.0
    team_reveal_turns: int = 3
    team_reveal_turn_seconds: float = .32
    opening_slow_turns: int = 9
    opening_turn_seconds: float = .48
    regular_turn_seconds: float = .20
    placement_delay: float = .035
    first_explosion_delay: float = .11
    explosion_spacing: float = .085
    orb_travel_seconds: float = .045
    neighbor_stagger_seconds: float = .004
    post_event_hold: float = .08
    elimination_pause: float = .16
    winner_pause: float = .24
    winner_hold_seconds: float = 1.60

    def __post_init__(self) -> None:
        for name, value in vars(self).items():
            if name in {"team_reveal_turns", "opening_slow_turns"}:
                if type(value) is not int or value < 0:
                    raise ValueError(f"{name} must be a nonnegative integer")
            elif type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and nonnegative")
        if self.team_reveal_turns > self.opening_slow_turns:
            raise ValueError("team reveal turns cannot exceed opening slow turns")
        if (
            self.team_reveal_turn_seconds <= 0
            or self.opening_turn_seconds <= 0
            or self.regular_turn_seconds <= 0
        ):
            raise ValueError("turn durations must be positive")
        if self.first_explosion_delay <= self.placement_delay:
            raise ValueError("first explosion must follow placement")
        required_spacing = self.orb_travel_seconds + 3 * self.neighbor_stagger_seconds + .012
        if self.explosion_spacing <= required_spacing:
            raise ValueError("explosion spacing must leave time for four ordered receipts")
        if self.winner_hold_seconds < .65:
            raise ValueError("winner hold must contain the complete MS05 resolution cue")


@dataclass(frozen=True)
class TimedGameEvent:
    event: GameEvent
    time_seconds: float
    source_cell: Coordinate | None = None
    source_time_seconds: float | None = None

    def __post_init__(self) -> None:
        if type(self.time_seconds) not in (int, float) or not math.isfinite(self.time_seconds) or self.time_seconds < 0:
            raise ValueError("presentation event time must be finite and nonnegative")
        if self.source_time_seconds is not None and (
            type(self.source_time_seconds) not in (int, float)
            or not 0 <= self.source_time_seconds <= self.time_seconds
        ):
            raise ValueError("transfer source time must precede receipt time")


@dataclass(frozen=True)
class PresentationPlan:
    match_id: str
    players: tuple[str, ...]
    winner: str
    grid: Grid
    events: tuple[TimedGameEvent, ...]
    snapshots: tuple[tuple[OrbCell, ...], ...]
    turn_start_times: tuple[float, ...]
    duration_seconds: float

    def __post_init__(self) -> None:
        if not isinstance(self.match_id, str) or not self.match_id:
            raise ValueError("plan match_id must be nonempty")
        if self.winner not in self.players:
            raise ValueError("plan winner must be a known player")
        if len(self.snapshots) != len(self.events):
            raise ValueError("every timed event requires a reconstructed snapshot")
        if tuple(item.event.sequence for item in self.events) != tuple(range(len(self.events))):
            raise ValueError("presentation requires a complete contiguous logical log")
        times = tuple(item.time_seconds for item in self.events)
        if any(second < first for first, second in zip(times, times[1:])):
            raise ValueError("presentation times must be nondecreasing")
        if self.duration_seconds <= times[-1] or self.duration_seconds - times[-1] < .65:
            raise ValueError("presentation must reserve a complete resolution tail")

    @property
    def event_times(self) -> tuple[float, ...]:
        return tuple(item.time_seconds for item in self.events)

    @property
    def winner_time(self) -> float:
        return next(item.time_seconds for item in reversed(self.events) if item.event.kind == "winner_declared")

    def state_at(self, time_seconds: float) -> tuple[OrbCell, ...]:
        index = bisect_right(self.event_times, time_seconds) - 1
        if index < 0:
            return tuple(OrbCell() for _ in self.grid.cells)
        return self.snapshots[index]


def load_selected_candidate(path: str | Path, match_id: str | None = None) -> tuple[dict, dict]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    required = {"schema_version", "search_id", "genuine_rule_outcomes", "scripted_winner",
                "selected_match_id", "configuration", "candidates"}
    if not isinstance(data, dict) or not required <= set(data):
        raise ValueError("invalid MS04.3 search record")
    if data["schema_version"] != "ms04.3.match-search.v1":
        raise ValueError("unsupported search record version")
    if data["genuine_rule_outcomes"] is not True or data["scripted_winner"] is not False:
        raise ValueError("presentation requires genuine, unscripted rule outcomes")
    expected = match_id or data["selected_match_id"]
    if expected != data["selected_match_id"]:
        raise ValueError("MS04.4 may present only the approved selected match")
    matches = [candidate for candidate in data["candidates"] if candidate.get("match_id") == expected]
    if len(matches) != 1:
        raise ValueError("selected match is missing or duplicated")
    candidate = matches[0]
    final = candidate.get("final_state", {})
    if final.get("completion_reason") != "won" or not final.get("winner"):
        raise ValueError("MS04.4 requires a genuinely completed winning match")
    return data, candidate


def _parse_event(raw: dict) -> GameEvent:
    values = dict(raw)
    if values.get("cell") is not None:
        values["cell"] = tuple(values["cell"])
    return GameEvent(**values)


def build_plan(candidate: dict, clock: PresentationClock) -> PresentationPlan:
    match_id = candidate["match_id"]
    players = tuple(policy["player_id"] for policy in candidate["policies"])
    final = candidate["final_state"]
    winner = final["winner"]
    rows = 9
    columns = 6
    grid = build_grid(rows, columns)
    logical_events = tuple(_parse_event(raw) for raw in candidate["events"])
    if tuple(event.sequence for event in logical_events) != tuple(range(len(logical_events))):
        raise ValueError("selected match logical events are incomplete")

    timed: list[TimedGameEvent] = []
    turn_starts = []
    cursor = clock.intro_seconds
    event_by_sequence = {event.sequence: event for event in logical_events}
    for turn in candidate["turns"]:
        turn_index = turn["turn_index"]
        turn_start = cursor
        turn_starts.append(turn_start)
        if turn_index < clock.team_reveal_turns:
            base_duration = clock.team_reveal_turn_seconds
        elif turn_index < clock.opening_slow_turns:
            base_duration = clock.opening_turn_seconds
        else:
            base_duration = clock.regular_turn_seconds
        first = turn["event_sequence_start"]
        last = turn["event_sequence_end"]
        turn_events = tuple(event_by_sequence[sequence] for sequence in range(first, last + 1))
        next_explosion_time = turn_start + clock.first_explosion_delay
        explosion_time = None
        explosion_source = None
        receipt_index = 0
        last_receipt_time = None
        previous_kind = None
        last_time = turn_start
        for event in turn_events:
            source = None
            source_time = None
            if event.kind == "turn_started":
                event_time = turn_start
            elif event.kind == "orb_placed":
                event_time = turn_start + clock.placement_delay
            elif event.kind == "cascade_depth_increased":
                event_time = max(last_time, next_explosion_time - .008)
            elif event.kind == "cell_exploded":
                event_time = max(last_time, next_explosion_time)
                explosion_time = event_time
                explosion_source = event.cell
                receipt_index = 0
                last_receipt_time = None
                next_explosion_time = event_time + clock.explosion_spacing
            elif event.kind == "orb_received":
                if explosion_time is None or explosion_source is None:
                    raise ValueError("orb_received must follow an explosion")
                event_time = explosion_time + clock.orb_travel_seconds + receipt_index * clock.neighbor_stagger_seconds
                event_time = max(last_time, event_time)
                source = explosion_source
                source_time = explosion_time
                receipt_index += 1
                last_receipt_time = event_time
            elif event.kind == "neighbor_captured":
                if last_receipt_time is None or event.cell != timed[-1].event.cell:
                    raise ValueError("neighbor capture must immediately follow its orb receipt")
                event_time = max(last_time, last_receipt_time + .001)
            elif event.kind in {"cell_charged", "cell_became_critical"}:
                if previous_kind in {"orb_received", "neighbor_captured"}:
                    event_time = last_time + .001
                else:
                    event_time = max(last_time, turn_start + clock.placement_delay + .012)
            elif event.kind == "player_eliminated":
                event_time = last_time + clock.elimination_pause
            elif event.kind == "winner_declared":
                event_time = last_time + clock.winner_pause
            elif event.kind == "cascade_aborted":
                raise ValueError("a cascade draw cannot be presented as a winning match")
            else:
                raise ValueError(f"unmapped logical event kind: {event.kind}")
            event_time = max(last_time, event_time)
            timed.append(TimedGameEvent(event, event_time, source, source_time))
            last_time = event_time
            previous_kind = event.kind
        cursor = max(turn_start + base_duration, last_time + clock.post_event_hold)

    cells = [OrbCell() for _ in grid.cells]
    snapshots = []
    for item in timed:
        event = item.event
        if event.kind in {"orb_placed", "orb_received"}:
            index = event.cell[0] * columns + event.cell[1]
            cells[index] = OrbCell(event.player_id, event.orb_count)
        elif event.kind == "cell_exploded":
            index = event.cell[0] * columns + event.cell[1]
            cells[index] = OrbCell(event.player_id if event.orb_count else None, event.orb_count)
        snapshots.append(tuple(cells))

    expected = {
        tuple(item["cell"]): (item["owner"], item["orb_count"])
        for item in final["occupied_cells"]
    }
    actual = {
        topology.coordinate: (cell.owner, cell.orb_count)
        for topology, cell in zip(grid.cells, cells)
        if cell.owner is not None
    }
    if actual != expected:
        raise ValueError("logical event reconstruction does not match the selected final board")
    duration = timed[-1].time_seconds + clock.winner_hold_seconds
    return PresentationPlan(
        match_id=match_id,
        players=players,
        winner=winner,
        grid=grid,
        events=tuple(timed),
        snapshots=tuple(snapshots),
        turn_start_times=tuple(turn_starts),
        duration_seconds=duration,
    )
