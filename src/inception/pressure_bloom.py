"""PB-1.1 deterministic, stylized packing rules. No presentation dependencies.

All mutation is private to one run. Inputs, events and returned logs are frozen;
JSON strings make nested records immutable without a shared event framework.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import json
import math

HZ = 120
EPS = 1e-6
RULES = "PB-1.1"


def encoded(value):
    # Non-finite rejected inputs remain explicit diagnostics, never JSON NaN or
    # numeric placeholders that could be mistaken for a repaired valid state.
    def diagnostic(v):
        if isinstance(v, float) and not math.isfinite(v):
            return str(v)
        if isinstance(v, dict):
            return {k: diagnostic(x) for k, x in v.items()}
        if isinstance(v, (tuple, list)):
            return [diagnostic(x) for x in v]
        return v
    return json.dumps(diagnostic(value), sort_keys=True, separators=(",", ":"), allow_nan=False)


@dataclass(frozen=True)
class Ball:
    id: str
    lineage: str
    x: float
    y: float
    radius: float = .08
    generation: int = 0
    parent: str | None = None
    parent_generation: int | None = None
    vx: float = 0.
    vy: float = 0.
    status: str = "inside"


@dataclass(frozen=True)
class Parameters:
    width: float = 1.
    height: float = 2.2
    reference_radius: float = .08
    drive_ramp_distance: float = .16
    schedule: tuple[tuple[float, float], ...] = ((0., 2.2), (.5, 2.04), (4., 1.45),
                                               (8., .9), (11.5, .48), (13.8, .24))
    max_ticks: int = 2160
    max_events: int = 20000
    nonprogress_ticks: int = 240
    projection_passes: int = 64
    overlap_ticks: int = 30
    excessive_overlap_ratio: float = .5

    def __post_init__(self):
        object.__setattr__(self, "schedule", tuple(tuple(pair) for pair in self.schedule))


@dataclass(frozen=True)
class Event:
    sequence: int
    id: str
    tick: int
    kind: str
    payload: str
    before: str
    after: str

    def to_dict(self):
        d = asdict(self)
        d["time"] = self.tick / HZ
        for key in ("payload", "before", "after"):
            d[key] = json.loads(d[key])
        return d


@dataclass(frozen=True)
class Result:
    run_id: str
    seed: int
    parameters: Parameters
    initial: str
    events: tuple[Event, ...]
    samples: tuple[str, ...]
    final: str

    def to_dict(self):
        return {"schema": "pressure-bloom-log-v1", "rules": RULES,
                "run_id": self.run_id, "seed": self.seed, "hz": HZ,
                "parameters": asdict(self.parameters), "initial": json.loads(self.initial),
                "events": [e.to_dict() for e in self.events],
                "samples": [json.loads(s) for s in self.samples],
                "final": json.loads(self.final)}


def command(p, tick):
    if not p.schedule:
        return p.height  # Allows the validator to report an invalid empty schedule.
    t = tick / HZ
    for (t0, h0), (t1, h1) in zip(p.schedule, p.schedule[1:]):
        if t <= t1:
            return h0 + (h1 - h0) * max(0., (t - t0) / (t1 - t0))
    return p.schedule[-1][1]


class _Budget(Exception):
    pass


class _Engine:
    def __init__(self, balls, p, seed, run_id):
        self.p, self.seed, self.run_id = p, seed, run_id
        self.balls = {b.id: b for b in balls}
        self.input_count = len(balls)
        self.tick = 0
        self.height = command(p, 0)
        self.first_contact = None
        self.mode = "compression"
        self.outcome = None
        self.locked_outcome = None
        self.reason = None
        self.opening = None
        self.rupture_tick = None
        self.clocks = {}
        self.previous_conditions = set()
        self.wall_clocks = {}
        self.previous_walls = set()
        self.bands = {}
        self.wall_bands = {}
        self.events = []
        self.samples = []
        self.stable_ticks = 0
        self.old_stable = None
        self.stalled = False
        self.overlap_age = 0
        self.overlap_start = None
        self.idle = 0
        self.old_idle = None
        self.extinct = set()
        self.lineages = sorted({b.lineage for b in balls})
        self.audit = {}
        self.walls = {}
        self.retired = {}
        self.last_valid = None

    def inside(self):
        return [b for _, b in sorted(self.balls.items()) if b.status == "inside"]

    def state(self):
        return {"tick": self.tick, "time": self.tick / HZ, "height": self.height,
                "command_height": command(self.p, self.tick), "first_contact": self.first_contact,
                "mode": self.mode, "outcome": self.outcome, "locked_outcome": self.locked_outcome,
                "reason": self.reason, "opening": self.opening,
                "balls": [asdict(b) for _, b in sorted(self.balls.items())],
                "retired": dict(sorted(self.retired.items())), "loads": self.audit,
                "walls": self.walls, "clocks": self.clocks, "wall_clocks": self.wall_clocks,
                "stable_ticks": self.stable_ticks,
                "occupied_area": sum(math.pi*b.radius**2 for b in self.inside()),
                "live_count": len(self.balls),
                "escaped_count": sum(b.status == "escaped" for b in self.balls.values()),
                "presentation_eligible": self.outcome in ("rupture", "containment", "extinction")
                                         and self.tick <= 2088}

    def emit(self, kind, payload, before=None):
        if len(self.events) >= self.p.max_events - 1:
            raise _Budget
        self.events.append(Event(len(self.events), f"{self.run_id}:{len(self.events):05d}",
                                 self.tick, kind, encoded(payload),
                                 before if before is not None else encoded(self.state()),
                                 encoded(self.state())))

    def finish(self, outcome, reason, kind, payload=None):
        before = encoded(self.state())
        self.outcome, self.reason = outcome, reason
        self.mode = "terminal"
        # Reserved diagnostic slot is always available; no recursive budget check.
        diagnostic = dict(payload or {"reason": reason})
        if outcome == "invalid":
            diagnostic["last_valid_state"] = json.loads(self.last_valid) if self.last_valid else None
        self.events.append(Event(len(self.events), f"{self.run_id}:{len(self.events):05d}",
                                 self.tick, kind, encoded(diagnostic),
                                 before, encoded(self.state())))

    def invalid_reason(self):
        p = self.p
        nums = [p.width, p.height, p.reference_radius, p.drive_ramp_distance]
        nums += [n for pair in p.schedule for n in pair]
        if not all(math.isfinite(v) for v in nums) or min(nums[:4]) <= 0:
            return "nonfinite_or_nonpositive_parameters"
        if not p.schedule or p.schedule[0][0] != 0 or p.schedule[0][1] > p.height or any(
            t1 <= t0 or h1 > h0 or h1 <= 0
            for (t0, h0), (t1, h1) in zip(p.schedule, p.schedule[1:])
        ):
            return "invalid_piston_schedule"
        if not (1 <= p.max_ticks <= 2160 and 2 <= p.max_events <= 20000
                and 1 <= p.projection_passes <= 64 and 1 <= p.nonprogress_ticks
                and 1 <= p.overlap_ticks and 0 < p.excessive_overlap_ratio <= .5):
            return "invalid_bounds"
        if self.input_count != len(self.balls):
            return "duplicate_ball_identity"
        if not 1 <= len(self.balls) <= 96:
            return "invalid_population"
        for b in self.balls.values():
            if not all(math.isfinite(v) for v in (b.x, b.y, b.radius, b.vx, b.vy)):
                return "nonfinite_ball"
            if b.radius <= 0 or b.generation not in range(4) or b.status != "inside":
                return "invalid_ball_identity_or_radius"
            if b.parent_generation != (b.generation - 1 if b.generation else None):
                return "invalid_ancestry"
            expected_radius = p.reference_radius * .75**b.generation
            if abs(b.radius-expected_radius) > 1e-12:
                return "invalid_generation_radius"
            if b.generation and not b.parent:
                return "missing_ancestry"
        if self.penetration(self.balls, self.height) > EPS:
            return "initial_overlap_or_impossible_placement"
        return None

    def fits_opening(self, b):
        if not self.opening:
            return False
        _, lo, hi = self.opening
        return b.y - b.radius >= lo - EPS and b.y + b.radius <= hi + EPS

    def solid(self, b, side):
        return not (self.opening and self.opening[0][0] == side and self.fits_opening(b))

    def penetration(self, balls, height):
        bs = [b for _, b in sorted(balls.items()) if b.status == "inside"]
        depth = 0.
        for i, b in enumerate(bs):
            depth = max(depth, b.radius-b.y, b.y+b.radius-height)
            if self.solid(b, "L"):
                depth = max(depth, b.radius-b.x)
            if self.solid(b, "R"):
                depth = max(depth, b.x+b.radius-self.p.width)
            for c in bs[i+1:]:
                depth = max(depth, b.radius+c.radius-math.hypot(b.x-c.x, b.y-c.y))
        return depth

    def project(self, balls, height):
        bs = {k: b for k, b in balls.items()}
        ids = sorted(k for k, b in bs.items() if b.status == "inside")
        self.projection_iterations = 0
        for iteration in range(self.p.projection_passes):
            self.projection_iterations = iteration+1
            # Boundary class first, then identity; pairs lexicographically ordered.
            for boundary in ("piston", "floor", "L", "R"):
                for k in ids:
                    b = bs[k]
                    if boundary == "piston":
                        b = replace(b, y=min(b.y, height-b.radius))
                    elif boundary == "floor":
                        b = replace(b, y=max(b.y, b.radius))
                    elif boundary == "L" and self.solid(b, "L"):
                        b = replace(b, x=max(b.x, b.radius))
                    elif boundary == "R" and self.solid(b, "R"):
                        b = replace(b, x=min(b.x, self.p.width-b.radius))
                    bs[k] = b
            for i, k in enumerate(ids):
                for j in ids[i+1:]:
                    b, c = bs[k], bs[j]
                    dx, dy = c.x-b.x, c.y-b.y
                    d = math.hypot(dx, dy)
                    overlap = b.radius+c.radius-d
                    if overlap > 0:
                        nx, ny = (dx/d, dy/d) if d else (1., 0.)
                        bs[k] = replace(b, x=b.x-nx*overlap/2, y=b.y-ny*overlap/2)
                        bs[j] = replace(c, x=c.x+nx*overlap/2, y=c.y+ny*overlap/2)
            if self.penetration(bs, height) <= EPS:
                return bs, True
        return bs, False

    def contacts(self):
        bs = self.inside()
        contacts, normals = {}, {}
        roots = set()
        for b in bs:
            ns = [c.id for c in bs if c.id != b.id and
                  math.hypot(b.x-c.x, b.y-c.y) <= b.radius+c.radius+EPS]
            piston = b.y+b.radius >= self.height-EPS
            left = self.solid(b, "L") and b.x-b.radius <= EPS
            right = self.solid(b, "R") and b.x+b.radius >= self.p.width-EPS
            floor = b.y-b.radius <= EPS
            contacts[b.id] = (ns, int(piston), int(left)+int(right), int(floor))
            n = []
            for k in ns:
                c = self.balls[k]
                dx, dy = c.x-b.x, c.y-b.y
                d = math.hypot(dx, dy)
                n.append((dx/d if d else 1., dy/d if d else 0., 1))
            if piston:
                roots.add(b.id)
                n.append((0., 1., 2))
            if floor:
                n.append((0., 1., 1))
            if left or right:
                n.append((1., 0., int(left)+int(right)))
            normals[b.id] = n
        connected = set(roots)
        frontier = sorted(roots)
        while frontier:
            k = frontier.pop(0)
            for j in contacts[k][0]:
                if j not in connected:
                    connected.add(j)
                    frontier.append(j)
        if roots and self.first_contact is None and self.mode == "compression":
            self.first_contact = {"tick": self.tick, "time": self.tick/HZ, "height": self.height}
        drive = (min(1., max(0., (self.first_contact["height"]-self.height)
                               / self.p.drive_ramp_distance)) if self.first_contact else 0.)
        self.audit = {}
        for b in bs:
            ns, piston, side, floor = contacts[b.id]
            weight = len(ns)+2*piston+side+floor
            c = int(b.id in connected and self.mode == "compression")
            self.audit[b.id] = {"C": c, "D": drive if self.mode == "compression" else 0.,
                                "neighbors": ns, "piston": piston, "side_walls": side,
                                "floor": floor, "weight": weight,
                                "L": c*drive*min(1., weight/4)}
        self.walls = {f"{side}{i}": {"W": 0., "contacts": []}
                      for side in ("L", "R") for i in range(4)}
        for b in bs:
            section = max(0, min(3, int(b.y/(self.p.height/4))))
            for side in ("L", "R"):
                touch = b.x-b.radius <= EPS if side == "L" else b.x+b.radius >= self.p.width-EPS
                if touch and self.solid(b, side):
                    w = self.walls[f"{side}{section}"]
                    w["contacts"].append(b.id)
                    w["W"] = min(1., w["W"]+self.audit[b.id]["L"]/2)
        return normals

    @staticmethod
    def axis(normals):
        a = sum(w*x*x for x, y, w in normals)
        b = sum(w*x*y for x, y, w in normals)
        d = sum(w*y*y for x, y, w in normals)
        angle = math.pi/2 if math.hypot(a-d, 2*b) <= 1e-9 else .5*math.atan2(2*b, a-d)
        tx, ty = -math.sin(angle), math.cos(angle)
        if tx < -1e-12 or (abs(tx) <= 1e-12 and ty < 0):
            tx, ty = -tx, -ty
        return tx, ty

    def qualifications(self):
        latched = {"crush": [], "rupture": [], "split": []}
        now = set()
        for b in self.inside():
            load = self.audit[b.id]["L"]
            split = .5-1e-12 <= load < .9-1e-12 and b.generation < 3 and len(self.balls) < 96
            crush = load >= .9-1e-12
            for kind, condition, duration in (("split", split, 36), ("crush", crush, 18)):
                key = f"{b.id}:{kind}"
                self.clocks[key] = self.clocks.get(key, 0)+1 if condition and key in self.previous_conditions else 0
                if condition:
                    now.add(key)
                if self.clocks[key] >= duration:
                    latched[kind].append(b.id)
        self.previous_conditions = now
        wall_now = set()
        for k, w in sorted(self.walls.items()):
            condition = w["W"] >= .8-1e-12
            self.wall_clocks[k] = self.wall_clocks.get(k, 0)+1 if condition and k in self.previous_walls else 0
            if condition:
                wall_now.add(k)
            if self.wall_clocks[k] >= 48:
                latched["rupture"].append(k)
        self.previous_walls = wall_now
        return latched

    def bands_changed(self):
        for k, a in sorted(self.audit.items()):
            band = "extreme" if a["L"] >= .9-1e-12 else "moderate" if a["L"] >= .5-1e-12 else "normal"
            old = self.bands.get(k, "normal")
            if old != band:
                self.emit("ball_strained", {"ball": k, "old": old, "new": band, "load": a})
            self.bands[k] = band
        for k, a in sorted(self.walls.items()):
            band = a["W"] >= .6-1e-12
            old = self.wall_bands.get(k, False)
            if old != band:
                self.emit("wall_strained", {"section": k, "strained": band, "wall": a})
            self.wall_bands[k] = band

    def retire(self, k, status):
        b = self.balls.pop(k)
        self.retired[k] = {**asdict(b), "status": status, "death_tick": self.tick}
        for kind in ("split", "crush"):
            self.clocks.pop(f"{k}:{kind}", None)
            self.previous_conditions.discard(f"{k}:{kind}")
        return b

    def extinctions(self):
        for lineage in self.lineages:
            if lineage not in self.extinct and not any(b.lineage == lineage for b in self.balls.values()):
                self.extinct.add(lineage)
                self.emit("lineage_extinct", {"lineage": lineage})

    def transitions(self, latched, normals):
        qualified = {k: dict(v) for k, v in self.audit.items()}
        qualified_walls = {k: dict(v) for k, v in self.walls.items()}
        for k in latched["crush"]:
            before = encoded(self.state())
            b = self.retire(k, "crushed")
            self.contacts()
            self.emit("ball_crushed", {"ball": asdict(b), "qualification": qualified[k],
                      "duration_ticks": 18, "removed_area": math.pi*b.radius**2,
                      "cohort": latched["crush"]}, before)
        self.extinctions()
        # Wall qualification is immutable: crushing cannot cancel this cohort.
        if latched["rupture"]:
            k = latched["rupture"][0]
            before = encoded(self.state())
            index = int(k[1])
            self.opening = (k, index*self.p.height/4, (index+1)*self.p.height/4)
            self.rupture_tick = self.tick
            self.locked_outcome = "rupture"
            self.mode = "release"
            release_ids = []
            for id, b in sorted(self.balls.items()):
                active = qualified.get(id, {}).get("C", 0) and self.fits_opening(b)
                speed = (-.4 if k[0] == "L" else .4) if active else 0.
                if active:
                    release_ids.append(id)
                self.balls[id] = replace(b, vx=speed, vy=0.)
            self.clocks, self.wall_clocks = {}, {}
            self.previous_conditions, self.previous_walls = set(), set()
            self.contacts()
            self.emit("wall_ruptured", {"section": k, "qualification": qualified_walls[k],
                      "duration_ticks": 48, "release_ids": release_ids,
                      "release_ticks": 72}, before)
            return
        if not self.balls:
            self.finish("extinction", "all_balls_crushed", "population_extinct")
            return
        for k in latched["split"]:
            if len(self.balls) >= 96:
                break
            if k not in self.balls:
                continue
            before = encoded(self.state())
            b = self.retire(k, "split")
            tx, ty = self.axis(normals[k])
            children = []
            for i, sign in enumerate((-1, 1)):
                child = Ball(f"{k}.{i}", b.lineage, b.x+sign*.65*b.radius*tx,
                             b.y+sign*.65*b.radius*ty, .75*b.radius,
                             b.generation+1, k, b.generation)
                self.balls[child.id] = child
                children.append(asdict(child))
            raw = self.penetration(self.balls, self.height)
            self.balls, resolved = self.project(self.balls, self.height)
            passes = self.projection_iterations
            self.contacts()
            self.emit("ball_split", {"parent": asdict(b), "qualification": qualified[k],
                      "duration_ticks": 36, "perpendicular": [tx, ty],
                      "birth_children": children, "initial_overlap": raw,
                      "relaxation_resolved": resolved,
                      "relaxation_passes": passes,
                      "residual_overlap": self.penetration(self.balls, self.height),
                      "relaxed_children": [asdict(self.balls[c["id"]]) for c in children],
                      "area_ratio": 1.125}, before)
            # Newly born children have no inherited strain history.

    def movement(self):
        before = encoded(self.state())
        old = self.balls
        target = command(self.p, self.tick)
        trial, ok = self.project(self.balls, target)
        changed_stall = self.stalled != (not ok)
        self.stalled = not ok
        if ok:
            self.height = target
            self.balls = {k: replace(b, vx=(b.x-old[k].x)*HZ, vy=(b.y-old[k].y)*HZ)
                          for k, b in trial.items()}
        else:
            # Keep previous valid packing, including a permitted soft birth overlap.
            self.balls, _ = self.project(old, self.height)
            self.balls = {k: replace(b, vx=(b.x-old[k].x)*HZ, vy=(b.y-old[k].y)*HZ)
                          for k, b in self.balls.items()}
        first = self.first_contact
        self.contacts()
        knot = any(round(t*HZ) == self.tick for t, _ in self.p.schedule)
        if changed_stall or knot or (first is None and self.first_contact is not None):
            self.emit("compression_advanced", {"stalled": self.stalled, "schedule_knot": knot,
                      "first_contact": self.first_contact}, before)

    def release(self):
        before = dict(self.balls)
        moved = {k: replace(b, x=b.x+b.vx/HZ, y=b.y+b.vy/HZ) for k, b in self.balls.items()}
        self.balls, ok = self.project(moved, self.height)
        if not ok:
            self.finish("invalid", "unresolved_release_overlap", "simulation_invalid")
            return
        for k in sorted(self.balls):
            b = self.balls[k]
            if b.status == "inside" and self.fits_opening(b) and (
                (self.opening[0][0] == "L" and b.x+b.radius <= 0)
                or (self.opening[0][0] == "R" and b.x-b.radius >= self.p.width)
            ):
                state = encoded(self.state())
                self.balls[k] = replace(b, status="escaped")
                self.contacts()
                self.emit("ball_escaped", {"ball": k, "previous_position": [before[k].x, before[k].y],
                          "opening": self.opening}, state)
        self.contacts()
        if self.tick-self.rupture_tick >= 72:
            self.finish("rupture", "release_interval_complete", "rupture_resolved",
                        {"release_ticks": 72, "escaped": [k for k, b in sorted(self.balls.items())
                                                           if b.status == "escaped"]})

    def checks(self):
        bs = self.inside()
        if not all(math.isfinite(v) for b in bs for v in (b.x, b.y, b.vx, b.vy, b.radius)):
            self.finish("invalid", "nonfinite_state", "simulation_invalid")
            return
        penetration = self.penetration(self.balls, self.height)
        if penetration > EPS:
            if self.overlap_start is None:
                self.overlap_start = self.tick
            self.overlap_age = self.tick-self.overlap_start
            ratio = penetration/min(b.radius for b in bs)
            if ratio > self.p.excessive_overlap_ratio:
                self.finish("invalid", "severe_unresolved_overlap", "simulation_invalid")
                return
            if self.overlap_age >= self.p.overlap_ticks:
                self.finish("draw", "finite_packing_stall", "simulation_draw")
                return
        else:
            self.overlap_age = 0
            self.overlap_start = None
        if self.mode != "compression":
            return
        signature = encoded([[b.id, round(b.x, 9), round(b.y, 9)] for b in bs])
        bands = tuple((k, self.bands[k]) for k in sorted(self.audit))
        stable = (signature, bands, tuple((k, v["W"]) for k, v in sorted(self.walls.items())))
        pending = bool(self.previous_conditions or self.previous_walls)
        at_final = abs(self.height-self.p.schedule[-1][1]) <= EPS
        slow = all(math.hypot(b.vx, b.vy) <= .005 for b in bs)
        self.stable_ticks = self.stable_ticks+1 if at_final and slow and not pending and stable == self.old_stable else 0
        self.old_stable = stable if at_final and slow and not pending else None
        if self.stable_ticks >= 72:
            self.finish("containment", "stable_final_chamber", "chamber_contained", {"hold_ticks": 72})
            return
        clock_advancing = any(self.clocks.values()) or any(self.wall_clocks.values()) or self.stable_ticks
        idle = (signature, bands, self.height, command(self.p, self.tick),
                encoded(self.audit), self.mode)
        eligible = self.tick/HZ >= self.p.schedule[-1][0] and not clock_advancing
        self.idle = self.idle+1 if eligible and idle == self.old_idle else 0
        self.old_idle = idle
        if self.idle >= self.p.nonprogress_ticks:
            self.finish("draw", "nonprogress", "simulation_draw")

    def run(self):
        reason = self.invalid_reason()
        if reason:
            self.finish("invalid", reason, "simulation_invalid", {"reason": reason,
                        "diagnostic": "Rejected input; nonfinite strings preserve the failure, not a repaired state."})
            initial = encoded(self.state())
        else:
            self.contacts()
            initial = encoded(self.state())
            self.last_valid = initial
            self.emit("press_engaged", {"first_contact": self.first_contact, "rules": RULES})
            for tick in range(1, self.p.max_ticks+1):
                self.tick = tick
                # Event budget is a transaction boundary: rollback the entire attempted tick.
                saved = self.__dict__.copy()
                for name in ("balls", "retired", "clocks", "wall_clocks", "bands", "wall_bands"):
                    saved[name] = dict(getattr(self, name))
                for name in ("extinct", "previous_conditions", "previous_walls"):
                    saved[name] = set(getattr(self, name))
                event_count = len(self.events)
                try:
                    if self.mode == "release":
                        self.release()
                    else:
                        self.movement()
                        normals = self.contacts()
                        latched = self.qualifications()
                        self.bands_changed()
                        self.transitions(latched, normals)
                        if not self.outcome and self.mode == "compression":
                            self.bands_changed()
                    if not self.outcome:
                        self.checks()
                except _Budget:
                    self.__dict__.update(saved)
                    del self.events[event_count:]
                    self.finish("draw", "event_limit", "simulation_draw")
                self.samples.append(encoded(self.state()))
                if self.outcome != "invalid":
                    self.last_valid = self.samples[-1]
                if self.outcome:
                    break
            if not self.outcome:
                self.finish("draw", "duration_limit", "simulation_draw",
                            {"reason": "duration_limit", "locked_outcome": self.locked_outcome,
                             "release_incomplete": self.mode == "release"})
                self.samples[-1] = encoded(self.state())
        return Result(self.run_id, self.seed, self.p, initial, tuple(self.events),
                      tuple(self.samples), encoded(self.state()))


def simulate(balls: tuple[Ball, ...], parameters: Parameters = Parameters(), *,
             seed: int = 0, run_id: str = "pressure-bloom") -> Result:
    """Simulate explicit versioned packing; seed identifies the reproducible input.

    No randomized contacts or hidden fixture interventions are performed. A future
    seeded initializer may produce these explicit layouts; it is outside this slice.
    """
    return _Engine(balls, parameters, seed, run_id).run()
