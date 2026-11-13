"""Pure MS04 grid geometry and immutable presentation snapshots.

This module deliberately contains no turns, ownership rules, cascades, timing,
rendering, or audio.  It establishes only the board topology needed by MS04.1.
"""

from dataclasses import dataclass
from enum import Enum


Coordinate = tuple[int, int]

# Filtering this fixed order at the board boundary makes adjacency deterministic.
ORTHOGONAL_DIRECTIONS: tuple[tuple[str, Coordinate], ...] = (
    ("north", (-1, 0)),
    ("east", (0, 1)),
    ("south", (1, 0)),
    ("west", (0, -1)),
)


class CellClass(str, Enum):
    CORNER = "corner"
    EDGE = "edge"
    INTERIOR = "interior"


@dataclass(frozen=True)
class Cell:
    coordinate: Coordinate
    cell_class: CellClass
    neighbors: tuple[Coordinate, ...]

    def __post_init__(self) -> None:
        if (type(self.coordinate) is not tuple or len(self.coordinate) != 2
                or any(type(value) is not int or value < 0 for value in self.coordinate)):
            raise ValueError("cell coordinate must be a nonnegative (row, column) tuple")
        if not isinstance(self.cell_class, CellClass):
            raise ValueError("cell_class must be a CellClass")
        if (type(self.neighbors) is not tuple
                or any(type(item) is not tuple or len(item) != 2
                       or any(type(value) is not int or value < 0 for value in item)
                       for item in self.neighbors)):
            raise ValueError("neighbors must be an immutable sequence of coordinates")

    @property
    def row(self) -> int:
        return self.coordinate[0]

    @property
    def column(self) -> int:
        return self.coordinate[1]


@dataclass(frozen=True)
class Grid:
    """A row-major rectangular grid with stable orthogonal adjacency."""

    rows: int
    columns: int
    cells: tuple[Cell, ...]

    def __post_init__(self) -> None:
        if type(self.rows) is not int or type(self.columns) is not int:
            raise ValueError("grid dimensions must be integers")
        if self.rows < 2 or self.columns < 2:
            raise ValueError("grid dimensions must each be at least two")
        expected = tuple((row, column) for row in range(self.rows) for column in range(self.columns))
        if type(self.cells) is not tuple or tuple(cell.coordinate for cell in self.cells) != expected:
            raise ValueError("grid cells must be an immutable complete row-major sequence")
        for cell in self.cells:
            row, column = cell.coordinate
            expected_neighbors = tuple(
                (row + dr, column + dc)
                for _, (dr, dc) in ORTHOGONAL_DIRECTIONS
                if 0 <= row + dr < self.rows and 0 <= column + dc < self.columns
            )
            expected_class = {
                2: CellClass.CORNER,
                3: CellClass.EDGE,
                4: CellClass.INTERIOR,
            }[len(expected_neighbors)]
            if cell.neighbors != expected_neighbors or cell.cell_class != expected_class:
                raise ValueError("grid cells must preserve canonical adjacency and classification")

    def cell(self, coordinate: Coordinate) -> Cell:
        row, column = coordinate
        if not (0 <= row < self.rows and 0 <= column < self.columns):
            raise IndexError(f"coordinate outside grid: {coordinate}")
        return self.cells[row * self.columns + column]


def build_grid(rows: int = 9, columns: int = 6) -> Grid:
    """Construct a grid without attaching any gameplay meaning to its degree."""
    if type(rows) is not int or type(columns) is not int or rows < 2 or columns < 2:
        raise ValueError("grid dimensions must be integers of at least two")
    cells = []
    for row in range(rows):
        for column in range(columns):
            neighbors = tuple(
                (row + dr, column + dc)
                for _, (dr, dc) in ORTHOGONAL_DIRECTIONS
                if 0 <= row + dr < rows and 0 <= column + dc < columns
            )
            classification = {
                2: CellClass.CORNER,
                3: CellClass.EDGE,
                4: CellClass.INTERIOR,
            }[len(neighbors)]
            cells.append(Cell((row, column), classification, neighbors))
    return Grid(rows, columns, tuple(cells))


@dataclass(frozen=True)
class CellDisplay:
    """One non-gameplay visual cell state used by the readability review."""

    coordinate: Coordinate
    orb_count: int
    team_index: int | None

    def __post_init__(self) -> None:
        if (type(self.coordinate) is not tuple or len(self.coordinate) != 2
                or any(type(value) is not int or value < 0 for value in self.coordinate)):
            raise ValueError("coordinate must be a nonnegative (row, column) tuple")
        if type(self.orb_count) is not int or not 0 <= self.orb_count <= 3:
            raise ValueError("MS04.1 display states support zero to three orbs")
        if self.orb_count == 0 and self.team_index is not None:
            raise ValueError("an empty display cell cannot have a team")
        if self.orb_count > 0 and (type(self.team_index) is not int or not 0 <= self.team_index < 8):
            raise ValueError("a nonempty display cell requires a team index in 0..7")


@dataclass(frozen=True)
class BoardSnapshot:
    """Immutable renderer input; it cannot advance or resolve a game."""

    grid: Grid
    cells: tuple[CellDisplay, ...]
    synthetic: bool = True

    def __post_init__(self) -> None:
        expected = tuple(cell.coordinate for cell in self.grid.cells)
        if type(self.cells) is not tuple or tuple(cell.coordinate for cell in self.cells) != expected:
            raise ValueError("snapshot cells must exactly match the grid in row-major order")
        if self.synthetic is not True:
            raise ValueError("MS04.1 contains only synthetic readability snapshots")

    def cell(self, coordinate: Coordinate) -> CellDisplay:
        row, column = coordinate
        self.grid.cell(coordinate)
        return self.cells[row * self.grid.columns + column]


def readability_snapshot(grid: Grid, team_count: int = 4) -> BoardSnapshot:
    """Create a deterministic diagnostic pattern, explicitly not a match state."""
    if type(team_count) is not int or not 2 <= team_count <= 8:
        raise ValueError("team_count must be an integer from two to eight")
    states = []
    for cell in grid.cells:
        row, column = cell.coordinate
        count = (row + 2 * column) % 4
        team = None if count == 0 else (row // 3 + column // 2) % team_count
        states.append(CellDisplay(cell.coordinate, count, team))
    return BoardSnapshot(grid, tuple(states))
