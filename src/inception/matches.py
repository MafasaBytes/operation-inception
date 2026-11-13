"""Seeded offline match simulation and transparent MS04.3 scoring proxies."""

from dataclasses import dataclass
import math
import random
from typing import Literal

from .grid import Coordinate
from .rules import GameEvent, GameState, RulesConfig, apply_move, create_game, legal_moves


POLICY_KINDS = frozenset({"random", "tactical"})
COMPLETION_REASONS = frozenset({"won", "cascade_draw", "turn_limit"})


@dataclass(frozen=True)
class PolicySpec:
    player_id: str
    kind: Literal["random", "tactical"]
    capture_weight: float = 3.0
    explosion_weight: float = 1.5
    elimination_weight: float = 18.0
    victory_weight: float = 40.0
    charge_weight: float = 1.0
    territory_weight: float = 1.25

    def __post_init__(self) -> None:
        if not isinstance(self.player_id, str) or not self.player_id:
            raise ValueError("policy player_id must be nonempty")
        if self.kind not in POLICY_KINDS:
            raise ValueError("policy kind must be random or tactical")
        for name in ("capture_weight", "explosion_weight", "elimination_weight",
                     "victory_weight", "charge_weight", "territory_weight"):
            value = getattr(self, name)
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be a finite nonnegative number")


@dataclass(frozen=True)
class TurnRecord:
    turn_index: int
    player_id: str
    move: Coordinate
    ownership_counts: tuple[int, ...]
    orb_counts: tuple[int, ...]
    eliminated: tuple[str, ...]
    event_sequence_start: int
    event_sequence_end: int
    explosion_count: int
    opponent_capture_count: int
    max_cascade_depth: int
    outcome: str
    winner: str | None


@dataclass(frozen=True)
class MatchResult:
    match_id: str
    seed: int
    policies: tuple[PolicySpec, ...]
    turns: tuple[TurnRecord, ...]
    events: tuple[GameEvent, ...]
    final_state: GameState
    completion_reason: Literal["won", "cascade_draw", "turn_limit"]

    def __post_init__(self) -> None:
        if not isinstance(self.match_id, str) or not self.match_id:
            raise ValueError("match_id must be nonempty")
        if type(self.seed) is not int or self.seed < 0:
            raise ValueError("match seed must be a nonnegative integer")
        if type(self.policies) is not tuple or type(self.turns) is not tuple or type(self.events) is not tuple:
            raise ValueError("match collections must be immutable tuples")
        if self.completion_reason not in COMPLETION_REASONS:
            raise ValueError("unknown match completion reason")
        if tuple(event.sequence for event in self.events) != tuple(range(len(self.events))):
            raise ValueError("complete match events must be contiguous from zero")
        if self.final_state.next_event_sequence != len(self.events):
            raise ValueError("final state event cursor must match the complete log")
        if len(self.turns) != self.final_state.turn_index:
            raise ValueError("turn records must cover every applied turn")
        if self.completion_reason == "won" and self.final_state.outcome != "won":
            raise ValueError("won completion requires a won game state")
        if self.completion_reason == "cascade_draw" and self.final_state.outcome != "draw":
            raise ValueError("cascade_draw requires a draw game state")
        if self.completion_reason == "turn_limit" and self.final_state.outcome != "active":
            raise ValueError("turn_limit must preserve an active unfinished state")


@dataclass(frozen=True)
class MatchScore:
    match_id: str
    total: float
    completion_points: float
    early_identity_points: float
    lead_change_points: float
    threat_points: float
    cascade_points: float
    comeback_points: float
    late_uncertainty_points: float
    capture_points: float
    early_survival_ratio: float
    lead_changes: int
    threat_episodes: int
    max_explosions: int
    max_cascade_depth: int
    winner_max_deficit: int
    late_uncertainty: float
    opponent_captures: int


def _ownership_counts(state: GameState) -> tuple[int, ...]:
    return tuple(sum(cell.owner == player for cell in state.cells) for player in state.players)


def _orb_counts(state: GameState) -> tuple[int, ...]:
    return tuple(sum(cell.orb_count for cell in state.cells if cell.owner == player) for player in state.players)


def _tactical_value(state: GameState, coordinate: Coordinate, policy: PolicySpec) -> float:
    player = state.current_player
    topology = state.grid.cell(coordinate)
    before = state.cell(coordinate)
    critical_mass = len(topology.neighbors)
    placed_count = before.orb_count + 1
    will_explode = placed_count >= critical_mass
    neighbors = tuple((neighbor, state.cell(neighbor)) for neighbor in topology.neighbors)
    opponent_cells = tuple(
        neighbor for neighbor, cell in neighbors
        if cell.owner is not None and cell.owner != player
    ) if will_explode else ()
    chain_ready = sum(
        cell.orb_count + 1 >= len(state.grid.cell(neighbor).neighbors)
        for neighbor, cell in neighbors
    ) if will_explode else 0
    predicted_eliminations = 0
    captured = set(opponent_cells)
    if state.opening_complete and captured:
        for opponent in state.active_players:
            if opponent == player:
                continue
            owned = {
                cell.coordinate for cell, contents in zip(state.grid.cells, state.cells)
                if contents.owner == opponent
            }
            if owned and owned <= captured:
                predicted_eliminations += 1
    predicted_victory = (
        state.opening_complete
        and len(state.active_players) - predicted_eliminations == 1
    )
    territory_delta = 1 if before.owner is None else 0
    if will_explode:
        territory_delta = sum(cell.owner != player for _, cell in neighbors) - 1
    charge_ratio = placed_count / critical_mass
    return (
        len(opponent_cells) * policy.capture_weight
        + (will_explode + chain_ready) * policy.explosion_weight
        + predicted_eliminations * policy.elimination_weight
        + predicted_victory * policy.victory_weight
        + charge_ratio * policy.charge_weight
        + territory_delta * policy.territory_weight
    )


def choose_move(state: GameState, policy: PolicySpec, rng: random.Random) -> Coordinate:
    if policy.player_id != state.current_player:
        raise ValueError("policy does not belong to the current player")
    moves = legal_moves(state)
    if not moves:
        raise RuntimeError("active player has no legal moves")
    if policy.kind == "random":
        return moves[rng.randrange(len(moves))]
    values = tuple(_tactical_value(state, move, policy) for move in moves)
    best = max(values)
    candidates = tuple(move for move, value in zip(moves, values) if value == best)
    return candidates[rng.randrange(len(candidates))]


def simulate_match(match_id: str, players: tuple[str, ...], policies: tuple[PolicySpec, ...],
                   seed: int, max_turns: int, rules: RulesConfig | None = None) -> MatchResult:
    if type(seed) is not int or seed < 0:
        raise ValueError("seed must be a nonnegative integer")
    if type(max_turns) is not int or max_turns < 1:
        raise ValueError("max_turns must be a positive integer")
    if type(policies) is not tuple or {policy.player_id for policy in policies} != set(players):
        raise ValueError("exactly one policy is required for every player")
    if len(policies) != len(players):
        raise ValueError("policy player ids must be unique")
    policy_by_player = {policy.player_id: policy for policy in policies}
    rng = random.Random(seed)
    state = create_game(players, rules)
    events: list[GameEvent] = []
    turns: list[TurnRecord] = []
    while state.outcome == "active" and len(turns) < max_turns:
        player = state.current_player
        move = choose_move(state, policy_by_player[player], rng)
        result = apply_move(state, move)
        turn_events = result.events
        state = result.state
        turns.append(TurnRecord(
            turn_index=len(turns),
            player_id=player,
            move=move,
            ownership_counts=_ownership_counts(state),
            orb_counts=_orb_counts(state),
            eliminated=tuple(candidate for candidate in players if candidate in state.eliminated),
            event_sequence_start=turn_events[0].sequence,
            event_sequence_end=turn_events[-1].sequence,
            explosion_count=sum(event.kind == "cell_exploded" for event in turn_events),
            opponent_capture_count=sum(
                event.kind == "neighbor_captured" and event.previous_owner is not None
                for event in turn_events
            ),
            max_cascade_depth=max((event.cascade_depth for event in turn_events), default=0),
            outcome=state.outcome,
            winner=state.winner,
        ))
        events.extend(turn_events)
    completion_reason = "won" if state.outcome == "won" else "cascade_draw" if state.outcome == "draw" else "turn_limit"
    return MatchResult(
        match_id=match_id,
        seed=seed,
        policies=policies,
        turns=tuple(turns),
        events=tuple(events),
        final_state=state,
        completion_reason=completion_reason,
    )


def _unique_leader(counts: tuple[int, ...]) -> int | None:
    greatest = max(counts)
    leaders = tuple(index for index, count in enumerate(counts) if count == greatest)
    return leaders[0] if len(leaders) == 1 else None


def score_match(match: MatchResult) -> MatchScore:
    player_count = len(match.final_state.players)
    turns = match.turns
    checkpoint = min(len(turns) - 1, player_count * 2 - 1)
    early_counts = turns[checkpoint].ownership_counts
    early_survival_ratio = sum(count > 0 for count in early_counts) / player_count

    settled_turns = turns[player_count - 1:]
    leaders = tuple(_unique_leader(turn.ownership_counts) for turn in settled_turns)
    last_leader = None
    lead_changes = 0
    for leader in leaders:
        if leader is None:
            continue
        if last_leader is not None and leader != last_leader:
            lead_changes += 1
        last_leader = leader

    previous_threats: set[int] = set()
    threat_episodes = 0
    for turn in settled_turns:
        greatest = max(turn.ownership_counts)
        threats = {
            index for index, count in enumerate(turn.ownership_counts)
            if 0 < count <= 2 and greatest >= count * 2 and count < greatest
        }
        threat_episodes += len(threats - previous_threats)
        previous_threats = threats

    max_explosions = max((turn.explosion_count for turn in turns), default=0)
    max_depth = max((turn.max_cascade_depth for turn in turns), default=0)
    captures = sum(turn.opponent_capture_count for turn in turns)

    winner_deficit = 0
    if match.final_state.winner is not None:
        winner_index = match.final_state.players.index(match.final_state.winner)
        winner_deficit = max(
            (max(turn.ownership_counts) - turn.ownership_counts[winner_index] for turn in settled_turns),
            default=0,
        )

    late_start = max(0, math.floor(len(turns) * .75))
    late_margins = []
    for turn in turns[late_start:]:
        ranked = sorted(turn.ownership_counts, reverse=True)
        late_margins.append((ranked[0] - ranked[1]) / max(1, ranked[0]))
    late_uncertainty = 1 - sum(late_margins) / len(late_margins) if late_margins else 0

    completion_points = 25.0 if match.completion_reason == "won" else -12.0 if match.completion_reason == "turn_limit" else -20.0
    early_points = 10.0 * early_survival_ratio
    lead_points = 3.0 * min(lead_changes, 6)
    threat_points = 2.0 * min(threat_episodes, 6)
    cascade_points = 1.2 * min(max_explosions, 12) + 1.5 * min(max_depth, 6)
    comeback_points = 1.2 * min(winner_deficit, 15)
    late_points = 12.0 * late_uncertainty
    capture_points = .4 * min(captures, 20)
    total = round(sum((completion_points, early_points, lead_points, threat_points,
                       cascade_points, comeback_points, late_points, capture_points)), 6)
    return MatchScore(
        match_id=match.match_id,
        total=total,
        completion_points=completion_points,
        early_identity_points=early_points,
        lead_change_points=lead_points,
        threat_points=threat_points,
        cascade_points=cascade_points,
        comeback_points=comeback_points,
        late_uncertainty_points=late_points,
        capture_points=capture_points,
        early_survival_ratio=early_survival_ratio,
        lead_changes=lead_changes,
        threat_episodes=threat_episodes,
        max_explosions=max_explosions,
        max_cascade_depth=max_depth,
        winner_max_deficit=winner_deficit,
        late_uncertainty=late_uncertainty,
        opponent_captures=captures,
    )
