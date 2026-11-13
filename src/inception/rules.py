"""Pure deterministic rules for MS04.2 spectator micro-games.

The engine owns logical state and semantic event order only.  It has no clock,
randomness, rendering, audio, match selection, or presentation concerns.
"""

from collections import deque
from dataclasses import dataclass
from typing import Literal

from .grid import Coordinate, Grid, build_grid


RULE_EVENT_KINDS = frozenset({
    "turn_started",
    "orb_placed",
    "cell_charged",
    "cell_became_critical",
    "cell_exploded",
    "orb_received",
    "neighbor_captured",
    "cascade_depth_increased",
    "player_eliminated",
    "winner_declared",
    "cascade_aborted",
})
OUTCOMES = frozenset({"active", "won", "draw"})
DRAW_REASONS = frozenset({"cascade_cycle", "cascade_step_limit"})


class IllegalMoveError(ValueError):
    """Raised when a move cannot be applied to the current settled state."""


@dataclass(frozen=True)
class RulesConfig:
    rows: int = 9
    columns: int = 6
    max_cascade_steps: int = 10_000

    def __post_init__(self) -> None:
        if type(self.rows) is not int or type(self.columns) is not int:
            raise ValueError("grid dimensions must be integers")
        if self.rows < 2 or self.columns < 2:
            raise ValueError("grid dimensions must each be at least two")
        if type(self.max_cascade_steps) is not int or not 1 <= self.max_cascade_steps <= 1_000_000:
            raise ValueError("max_cascade_steps must be an integer in 1..1,000,000")


@dataclass(frozen=True)
class OrbCell:
    owner: str | None = None
    orb_count: int = 0

    def __post_init__(self) -> None:
        if self.owner is not None and (not isinstance(self.owner, str) or not self.owner):
            raise ValueError("cell owner must be null or a nonempty player id")
        if type(self.orb_count) is not int or self.orb_count < 0:
            raise ValueError("orb_count must be a nonnegative integer")
        if (self.owner is None) != (self.orb_count == 0):
            raise ValueError("empty cells have no owner; nonempty cells require one")


@dataclass(frozen=True)
class GameEvent:
    id: str
    sequence: int
    turn_index: int
    kind: str
    player_id: str
    cell: Coordinate | None = None
    orb_count: int | None = None
    critical_mass: int | None = None
    cascade_depth: int = 0
    previous_owner: str | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id:
            raise ValueError("event id must be nonempty")
        if type(self.sequence) is not int or self.sequence < 0:
            raise ValueError("event sequence must be nonnegative")
        if type(self.turn_index) is not int or self.turn_index < 0:
            raise ValueError("event turn_index must be nonnegative")
        if self.kind not in RULE_EVENT_KINDS:
            raise ValueError("unknown rule event kind")
        if not isinstance(self.player_id, str) or not self.player_id:
            raise ValueError("event player_id must be nonempty")
        if self.cell is not None and (type(self.cell) is not tuple or len(self.cell) != 2
                                     or any(type(value) is not int or value < 0 for value in self.cell)):
            raise ValueError("event cell must be a nonnegative coordinate")
        for name in ("orb_count", "critical_mass", "cascade_depth"):
            value = getattr(self, name)
            minimum = 1 if name == "critical_mass" else 0
            if value is not None and (type(value) is not int or value < minimum):
                raise ValueError(f"invalid event {name}")
        if self.cascade_depth is None:
            raise ValueError("cascade_depth cannot be null")


@dataclass(frozen=True)
class GameState:
    rules: RulesConfig
    grid: Grid
    players: tuple[str, ...]
    cells: tuple[OrbCell, ...]
    current_player_index: int
    turn_index: int
    has_played: tuple[bool, ...]
    eliminated: frozenset[str]
    next_event_sequence: int = 0
    outcome: Literal["active", "won", "draw"] = "active"
    winner: str | None = None
    termination_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.rules, RulesConfig) or not isinstance(self.grid, Grid):
            raise ValueError("state requires RulesConfig and Grid")
        if (self.grid.rows, self.grid.columns) != (self.rules.rows, self.rules.columns):
            raise ValueError("grid dimensions must match the rule configuration")
        if (type(self.players) is not tuple or not 2 <= len(self.players) <= 8
                or any(not isinstance(player, str) or not player for player in self.players)
                or len(set(self.players)) != len(self.players)):
            raise ValueError("players must be two to eight unique nonempty ids")
        if (type(self.cells) is not tuple or len(self.cells) != len(self.grid.cells)
                or not all(isinstance(cell, OrbCell) for cell in self.cells)):
            raise ValueError("cells must be an immutable complete board")
        if type(self.has_played) is not tuple or len(self.has_played) != len(self.players):
            raise ValueError("has_played must align with players")
        if any(type(value) is not bool for value in self.has_played):
            raise ValueError("has_played values must be booleans")
        if type(self.eliminated) is not frozenset or not self.eliminated <= set(self.players):
            raise ValueError("eliminated must be an immutable subset of players")
        if any(self.players[index] in self.eliminated and not played
               for index, played in enumerate(self.has_played)):
            raise ValueError("an eliminated player must have completed a turn")
        if type(self.current_player_index) is not int or not 0 <= self.current_player_index < len(self.players):
            raise ValueError("current_player_index is outside players")
        if type(self.turn_index) is not int or self.turn_index < 0:
            raise ValueError("turn_index must be nonnegative")
        if type(self.next_event_sequence) is not int or self.next_event_sequence < 0:
            raise ValueError("next_event_sequence must be nonnegative")
        owners = {cell.owner for cell in self.cells if cell.owner is not None}
        if not owners <= set(self.players) or owners & self.eliminated:
            raise ValueError("board ownership must reference active known players")
        for topology, cell in zip(self.grid.cells, self.cells):
            if cell.orb_count >= len(topology.neighbors):
                raise ValueError("public game states must be cascade-settled")
        if self.outcome not in OUTCOMES:
            raise ValueError("unknown game outcome")
        active = tuple(player for player in self.players if player not in self.eliminated)
        if not active:
            raise ValueError("at least one player must remain")
        if self.outcome == "active":
            if self.winner is not None or self.termination_reason is not None:
                raise ValueError("an active game has no winner or termination reason")
            if self.current_player in self.eliminated:
                raise ValueError("current player cannot be eliminated")
            if all(self.has_played) and len(active) < 2:
                raise ValueError("a settled one-player state must be marked won")
        elif self.outcome == "won":
            if (self.winner is None or self.winner not in active or active != (self.winner,)
                    or self.termination_reason != "last_player_remaining" or not all(self.has_played)):
                raise ValueError("won state must name the sole active player after opening protection")
        else:
            if self.winner is not None or self.termination_reason not in DRAW_REASONS:
                raise ValueError("draw state requires an explicit cascade termination reason")

    @property
    def current_player(self) -> str:
        return self.players[self.current_player_index]

    @property
    def active_players(self) -> tuple[str, ...]:
        return tuple(player for player in self.players if player not in self.eliminated)

    @property
    def opening_complete(self) -> bool:
        return all(self.has_played)

    @property
    def total_orbs(self) -> int:
        return sum(cell.orb_count for cell in self.cells)

    def cell(self, coordinate: Coordinate) -> OrbCell:
        topology = self.grid.cell(coordinate)
        return self.cells[topology.row * self.grid.columns + topology.column]


@dataclass(frozen=True)
class MoveResult:
    state: GameState
    events: tuple[GameEvent, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.state, GameState) or type(self.events) is not tuple or not self.events:
            raise ValueError("move result requires a state and immutable events")
        if not all(isinstance(event, GameEvent) for event in self.events):
            raise ValueError("move events must be GameEvent values")
        sequences = tuple(event.sequence for event in self.events)
        if any(second != first + 1 for first, second in zip(sequences, sequences[1:])):
            raise ValueError("move event sequences must be contiguous")
        if len({event.id for event in self.events}) != len(self.events):
            raise ValueError("move event ids must be unique")
        if self.state.next_event_sequence != sequences[-1] + 1:
            raise ValueError("state event cursor must follow the move events")


class _EventBuilder:
    def __init__(self, turn_index: int, first_sequence: int):
        self.turn_index = turn_index
        self.next_sequence = first_sequence
        self.events: list[GameEvent] = []

    def emit(self, kind: str, player_id: str, **values) -> None:
        sequence = self.next_sequence
        self.events.append(GameEvent(
            id=f"ms04.2.turn-{self.turn_index:06d}.event-{sequence:08d}",
            sequence=sequence,
            turn_index=self.turn_index,
            kind=kind,
            player_id=player_id,
            **values,
        ))
        self.next_sequence += 1


def create_game(players: tuple[str, ...], rules: RulesConfig | None = None) -> GameState:
    rules = rules or RulesConfig()
    grid = build_grid(rules.rows, rules.columns)
    cells = tuple(OrbCell() for _ in grid.cells)
    return GameState(
        rules=rules,
        grid=grid,
        players=players,
        cells=cells,
        current_player_index=0,
        turn_index=0,
        has_played=tuple(False for _ in players),
        eliminated=frozenset(),
    )


def legal_moves(state: GameState) -> tuple[Coordinate, ...]:
    if state.outcome != "active":
        return ()
    player = state.current_player
    return tuple(
        topology.coordinate
        for topology, cell in zip(state.grid.cells, state.cells)
        if cell.owner in (None, player)
    )


def _cell_index(grid: Grid, coordinate: Coordinate) -> int:
    topology = grid.cell(coordinate)
    return topology.row * grid.columns + topology.column


def _emit_level(builder: _EventBuilder, player: str, coordinate: Coordinate,
                before: int, after: int, critical_mass: int, depth: int) -> None:
    if before < critical_mass <= after:
        builder.emit(
            "cell_became_critical", player, cell=coordinate, orb_count=after,
            critical_mass=critical_mass, cascade_depth=depth,
        )
    elif after < critical_mass:
        builder.emit(
            "cell_charged", player, cell=coordinate, orb_count=after,
            critical_mass=critical_mass, cascade_depth=depth,
        )


def _cascade_fingerprint(cells: list[OrbCell], queue: deque[tuple[Coordinate, int]]) -> tuple:
    return tuple((cell.owner, cell.orb_count) for cell in cells), tuple(queue)


def _next_active_index(players: tuple[str, ...], eliminated: frozenset[str], current: int) -> int:
    for offset in range(1, len(players) + 1):
        candidate = (current + offset) % len(players)
        if players[candidate] not in eliminated:
            return candidate
    raise RuntimeError("no active player remains")


def _aborted_result(state: GameState, coordinate: Coordinate, reason: str) -> MoveResult:
    builder = _EventBuilder(state.turn_index, state.next_event_sequence)
    builder.emit("turn_started", state.current_player)
    builder.emit("cascade_aborted", state.current_player, cell=coordinate, reason=reason)
    rolled_back = GameState(
        rules=state.rules,
        grid=state.grid,
        players=state.players,
        cells=state.cells,
        current_player_index=state.current_player_index,
        turn_index=state.turn_index + 1,
        has_played=tuple(
            True if index == state.current_player_index else played
            for index, played in enumerate(state.has_played)
        ),
        eliminated=state.eliminated,
        next_event_sequence=builder.next_sequence,
        outcome="draw",
        winner=None,
        termination_reason=reason,
    )
    return MoveResult(rolled_back, tuple(builder.events))


def apply_move(state: GameState, coordinate: Coordinate) -> MoveResult:
    """Apply one legal turn and completely settle its deterministic cascade."""
    if state.outcome != "active":
        raise IllegalMoveError("cannot move after the game has ended")
    try:
        index = _cell_index(state.grid, coordinate)
    except (IndexError, TypeError, ValueError) as error:
        raise IllegalMoveError(f"coordinate outside the board: {coordinate}") from error
    player = state.current_player
    original = state.cells[index]
    if original.owner not in (None, player):
        raise IllegalMoveError("a player may place only in an empty or owned cell")

    builder = _EventBuilder(state.turn_index, state.next_event_sequence)
    builder.emit("turn_started", player)
    cells = list(state.cells)
    placed_count = original.orb_count + 1
    cells[index] = OrbCell(player, placed_count)
    critical_mass = len(state.grid.cell(coordinate).neighbors)
    builder.emit(
        "orb_placed", player, cell=coordinate, orb_count=placed_count,
        critical_mass=critical_mass, previous_owner=original.owner,
    )
    _emit_level(builder, player, coordinate, original.orb_count, placed_count, critical_mass, 0)

    queue: deque[tuple[Coordinate, int]] = deque()
    queued: set[Coordinate] = set()
    if placed_count >= critical_mass:
        queue.append((coordinate, 0))
        queued.add(coordinate)

    seen = set()
    explosion_steps = 0
    greatest_depth = 0
    while queue:
        fingerprint = _cascade_fingerprint(cells, queue)
        if fingerprint in seen:
            return _aborted_result(state, coordinate, "cascade_cycle")
        seen.add(fingerprint)
        if explosion_steps >= state.rules.max_cascade_steps:
            return _aborted_result(state, coordinate, "cascade_step_limit")

        exploding_coordinate, depth = queue.popleft()
        queued.remove(exploding_coordinate)
        exploding_index = _cell_index(state.grid, exploding_coordinate)
        exploding = cells[exploding_index]
        exploding_mass = len(state.grid.cell(exploding_coordinate).neighbors)
        if exploding.orb_count < exploding_mass or exploding.owner is None:
            raise RuntimeError("cascade queue contained a noncritical cell")
        exploding_player = exploding.owner
        if depth > greatest_depth:
            greatest_depth = depth
            builder.emit(
                "cascade_depth_increased", exploding_player, cell=exploding_coordinate,
                orb_count=exploding.orb_count, critical_mass=exploding_mass,
                cascade_depth=depth,
            )

        residual = exploding.orb_count - exploding_mass
        cells[exploding_index] = OrbCell(exploding_player if residual else None, residual)
        builder.emit(
            "cell_exploded", exploding_player, cell=exploding_coordinate,
            orb_count=residual, critical_mass=exploding_mass, cascade_depth=depth,
        )
        explosion_steps += 1

        for neighbor in state.grid.cell(exploding_coordinate).neighbors:
            neighbor_index = _cell_index(state.grid, neighbor)
            before = cells[neighbor_index]
            after_count = before.orb_count + 1
            cells[neighbor_index] = OrbCell(exploding_player, after_count)
            neighbor_mass = len(state.grid.cell(neighbor).neighbors)
            builder.emit(
                "orb_received", exploding_player, cell=neighbor,
                orb_count=after_count, critical_mass=neighbor_mass,
                cascade_depth=depth, previous_owner=before.owner,
            )
            if before.owner != exploding_player:
                builder.emit(
                    "neighbor_captured", exploding_player, cell=neighbor,
                    orb_count=after_count, critical_mass=neighbor_mass,
                    cascade_depth=depth, previous_owner=before.owner,
                )
            _emit_level(
                builder, exploding_player, neighbor, before.orb_count,
                after_count, neighbor_mass, depth,
            )
            if after_count >= neighbor_mass and neighbor not in queued:
                queue.append((neighbor, depth + 1))
                queued.add(neighbor)

        if residual >= exploding_mass and exploding_coordinate not in queued:
            queue.append((exploding_coordinate, depth))
            queued.add(exploding_coordinate)

    has_played = tuple(
        True if index == state.current_player_index else played
        for index, played in enumerate(state.has_played)
    )
    eliminated = set(state.eliminated)
    if all(has_played):
        owners = {cell.owner for cell in cells if cell.owner is not None}
        for candidate in state.players:
            if candidate not in eliminated and candidate not in owners:
                eliminated.add(candidate)
                builder.emit(
                    "player_eliminated", candidate,
                    reason="zero_owned_cells_after_settlement",
                )
    eliminated_frozen = frozenset(eliminated)
    active = tuple(candidate for candidate in state.players if candidate not in eliminated_frozen)
    if all(has_played) and len(active) == 1:
        outcome: Literal["active", "won", "draw"] = "won"
        winner = active[0]
        termination_reason = "last_player_remaining"
        builder.emit("winner_declared", winner, reason=termination_reason)
        current_player_index = state.players.index(winner)
    else:
        outcome = "active"
        winner = None
        termination_reason = None
        current_player_index = _next_active_index(state.players, eliminated_frozen, state.current_player_index)

    settled = GameState(
        rules=state.rules,
        grid=state.grid,
        players=state.players,
        cells=tuple(cells),
        current_player_index=current_player_index,
        turn_index=state.turn_index + 1,
        has_played=has_played,
        eliminated=eliminated_frozen,
        next_event_sequence=builder.next_sequence,
        outcome=outcome,
        winner=winner,
        termination_reason=termination_reason,
    )
    return MoveResult(settled, tuple(builder.events))
