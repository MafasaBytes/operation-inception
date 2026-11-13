"""Version 1 immutable timed-event contract. This module does not implement rules."""

from dataclasses import dataclass
import json
import math
from pathlib import Path

SCHEMA_VERSION = "ms05.audio-events.v1"
EVENT_KINDS = frozenset({
    "turn_started", "orb_placed", "cell_charged", "cell_became_critical",
    "cell_exploded", "neighbor_captured", "cascade_depth_increased",
    "player_endangered", "player_eliminated", "winner_declared",
})


def finite_number(value, label):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(f"{label} must be a finite number")


@dataclass(frozen=True)
class Team:
    id: str
    voice: int

    def __post_init__(self):
        if not isinstance(self.id, str) or not self.id:
            raise ValueError("team id must be a nonempty string")
        if type(self.voice) is not int or not 0 <= self.voice < 8:
            raise ValueError("team voice must be an integer in 0..7")


@dataclass(frozen=True)
class AudioEvent:
    id: str
    sequence: int
    time_seconds: float
    kind: str
    team_id: str
    cell: tuple[int, int] | None = None
    orb_count: int | None = None
    critical_mass: int | None = None
    cascade_depth: int = 0
    previous_team_id: str | None = None

    def __post_init__(self):
        if not isinstance(self.id, str) or not self.id:
            raise ValueError("event id must be a nonempty string")
        if type(self.sequence) is not int or self.sequence < 0:
            raise ValueError("event sequence must be a nonnegative integer")
        finite_number(self.time_seconds, "event time_seconds")
        if self.time_seconds < 0 or self.kind not in EVENT_KINDS:
            raise ValueError("invalid event time or kind")
        if not isinstance(self.team_id, str) or not self.team_id:
            raise ValueError("event team_id must be a nonempty string")
        if self.cell is not None and (type(self.cell) is not tuple or len(self.cell) != 2
                                     or any(type(v) is not int or v < 0 for v in self.cell)):
            raise ValueError("cell must be an immutable (row, column) pair")
        for label in ("orb_count", "critical_mass", "cascade_depth"):
            value = getattr(self, label)
            if value is not None and (type(value) is not int or value < (1 if label == "critical_mass" else 0)):
                raise ValueError(f"invalid {label}")
        if self.cascade_depth is None:
            raise ValueError("cascade_depth cannot be null")
        if self.kind in {"cell_charged", "cell_became_critical"} and (self.orb_count is None or self.critical_mass is None):
            raise ValueError("charge/critical events require orb_count and critical_mass")


@dataclass(frozen=True)
class EventLog:
    schema_version: str
    log_id: str
    synthetic: bool
    duration_seconds: float
    teams: tuple[Team, ...]
    events: tuple[AudioEvent, ...]

    def __post_init__(self):
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError("unsupported audio-event schema version")
        if not isinstance(self.log_id, str) or not self.log_id or type(self.synthetic) is not bool:
            raise ValueError("log_id and synthetic provenance are required")
        finite_number(self.duration_seconds, "duration_seconds")
        if self.duration_seconds <= 0:
            raise ValueError("duration_seconds must be positive")
        if type(self.teams) is not tuple or not 2 <= len(self.teams) <= 8 or not all(isinstance(t, Team) for t in self.teams):
            raise ValueError("event log requires an immutable tuple of two to eight teams")
        ids = {t.id for t in self.teams}
        if len(ids) != len(self.teams) or len({t.voice for t in self.teams}) != len(self.teams):
            raise ValueError("team ids and voice assignments must be unique")
        if type(self.events) is not tuple or not self.events or not all(isinstance(e, AudioEvent) for e in self.events):
            raise ValueError("events must be a nonempty immutable tuple")
        previous_sequence, previous_time = -1, -1.
        seen = set()
        for event in self.events:
            if event.id in seen or event.sequence <= previous_sequence or event.time_seconds < previous_time:
                raise ValueError("event ids must be unique, sequences increasing, and times nondecreasing")
            if event.time_seconds >= self.duration_seconds:
                raise ValueError("event time must precede the output window end")
            if event.team_id not in ids or (event.previous_team_id is not None and event.previous_team_id not in ids):
                raise ValueError("event references an unknown team")
            if event.kind == "neighbor_captured" and event.previous_team_id == event.team_id:
                raise ValueError("capture must not name the incoming team as the previous owner")
            seen.add(event.id)
            previous_sequence, previous_time = event.sequence, event.time_seconds


def parse_event_log(data: dict) -> EventLog:
    """Annotations in metadata never affect synthesis, including display-FPS hints."""
    allowed = {"schema_version", "log_id", "synthetic", "duration_seconds", "teams", "events", "metadata"}
    if not isinstance(data, dict) or set(data)-allowed:
        raise ValueError("unknown audio log field")
    try:
        teams = tuple(Team(**team) for team in data["teams"])
        events = []
        for raw in data["events"]:
            values = dict(raw)
            if values.get("cell") is not None:
                values["cell"] = tuple(values["cell"])
            events.append(AudioEvent(**values))
        return EventLog(data["schema_version"], data["log_id"], data["synthetic"],
                        data["duration_seconds"], teams, tuple(events))
    except (KeyError, TypeError) as error:
        raise ValueError(f"invalid event-log structure: {error}") from error


def load_event_log(path: str | Path) -> EventLog:
    return parse_event_log(json.loads(Path(path).read_text()))
