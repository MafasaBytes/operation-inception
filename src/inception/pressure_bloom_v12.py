"""PB-1.2 pressure reachability; reuses the unchanged PB-1.1 rule kernel.

Version-specific settling, motion, drive and wall arithmetic only. No media,
services, randomness, or generalized format framework.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import hashlib
import json
import math

from .pressure_bloom import Ball, EPS, HZ, Event, Parameters, Result, _Budget, _Engine, command, encoded

RULES = "PB-1.2"


@dataclass(frozen=True)
class Parameters12(Parameters):
    rules_version: str = RULES
    gravity: float = 1.2
    damping_per_second: float = 8.
    physics_substeps: int = 4
    settling_max_ticks: int = 2400
    settling_speed_tolerance: float = .002
    settling_penetration_tolerance: float = EPS
    catchup_speed: float = .4
    catchup_policy: str = 'bounded-contact-rollback-v1'
    wall_capacity: float = 2.5


@dataclass(frozen=True)
class Event12(Event):
    def to_dict(self):
        record = super().to_dict()
        record['rules'] = RULES
        record['phase'] = record['payload'].get('phase', record['after']['mode'])
        return record


@dataclass(frozen=True)
class Result12(Result):
    settlement: str = '{}'

    def to_dict(self):
        record = super().to_dict()
        record.update(schema='pressure-bloom-log-v2', rules=RULES,
                      settlement=json.loads(self.settlement))
        return record


class _Engine12(_Engine):
    def __init__(self, balls, p, seed, run_id):
        super().__init__(balls, p, seed, run_id)
        self.preparation = {'rules': RULES, 'status': 'not_started', 'tick': 0}
        self.settling_samples = []
        self.drive = self.drive_metrics()
        self.frozen_command = None
        self.contact_notified = False

    def commanded_height(self):
        return self.frozen_command if self.frozen_command is not None else command(self.p, self.tick)

    def drive_metrics(self):
        target = self.commanded_height() if hasattr(self, 'frozen_command') else command(self.p, self.tick)
        first = self.first_contact
        achieved = max(0., first['height']-self.height) if first else 0.
        commanded = max(0., first.get('command_height', target)-target) if first else 0.
        debt = min(self.p.drive_ramp_distance, max(0., commanded-achieved)) if first else 0.
        drive = min(1., max(0., (achieved+debt)/self.p.drive_ramp_distance)) if first else 0.
        return {'rules': RULES, 'commanded_position': target, 'achieved_position': self.height,
                'commanded_travel': commanded, 'achieved_travel': achieved, 'debt': debt, 'D': drive}

    def state(self):
        s = super().state()
        s.update(rules=RULES, piston=self.drive_metrics(), preparation=dict(self.preparation))
        s['command_height'] = self.commanded_height()
        return s

    def _version_event(self):
        self.events[-1] = Event12(**asdict(self.events[-1]))

    def notify_contact(self):
        if self.first_contact and not self.contact_notified:
            self.contact_notified = True
            self.emit('piston_first_contact', {'contact': self.first_contact, 'drive': self.drive_metrics()})

    def emit(self, kind, payload, before=None):
        super().emit(kind, {**payload, 'rules': RULES}, before)
        self._version_event()
        if kind == 'press_engaged':
            self.notify_contact()

    def finish(self, outcome, reason, kind, payload=None):
        super().finish(outcome, reason, kind, {**(payload or {'reason': reason}), 'rules': RULES})
        self._version_event()

    def invalid_reason(self):
        # Preparation uses the retracted ceiling, not the later active target.
        actual = self.height
        self.height = self.p.height
        reason = super().invalid_reason()
        self.height = actual
        if reason:
            return reason
        p = self.p
        integers = (p.physics_substeps, p.settling_max_ticks, p.max_ticks,
                    p.max_events, p.projection_passes, p.nonprogress_ticks, p.overlap_ticks)
        if not all(type(v) is int for v in integers):
            return 'invalid_pb12_integer_parameters'
        numbers = (p.gravity, p.damping_per_second, p.settling_speed_tolerance,
                   p.settling_penetration_tolerance, p.catchup_speed, p.wall_capacity)
        if not all(math.isfinite(v) and v > 0 for v in numbers):
            return 'invalid_pb12_numeric_parameters'
        if (p.rules_version != RULES or not 1 <= p.physics_substeps <= 8
            or not 1 <= p.settling_max_ticks <= 2400 or p.catchup_policy != 'bounded-contact-rollback-v1'
            or p.settling_penetration_tolerance > EPS or p.wall_capacity != 2.5):
            return 'invalid_pb12_policy'
        # A controller speed limit must not itself manufacture compression debt
        # during free motion. Reject commands faster than the bounded policy.
        free_speed = min(p.catchup_speed, p.reference_radius*.75**3*HZ*p.physics_substeps/4)
        if any((h0-h1)/(t1-t0) > free_speed+1e-12
               for (t0,h0),(t1,h1) in zip(p.schedule,p.schedule[1:])):
            return 'command_exceeds_bounded_free_speed'
        return None

    def contacts(self):
        old_first = self.first_contact
        normals = super().contacts()
        if old_first is None and self.first_contact is not None:
            self.first_contact = {**self.first_contact, 'rules': RULES,
                                  'command_height': self.commanded_height()}
        self.drive = self.drive_metrics()
        for a in self.audit.values():
            a['D'] = self.drive['D'] if self.mode == 'compression' else 0.
            a['L'] = a['C']*a['D']*min(1., a['weight']/4)
            a['commanded_travel'] = self.drive['commanded_travel']
            a['achieved_travel'] = self.drive['achieved_travel']
            a['debt'] = self.drive['debt']
        self.walls = {f'{side}{i}': {'W': 0., 'contacts': [], 'contributions': [],
                                   'capacity': self.p.wall_capacity}
                      for side in ('L', 'R') for i in range(4)}
        for b in self.inside():
            # A circle against a vertical planar segment contacts at (wall_x,y).
            index = max(0, min(3, math.floor(b.y/(self.p.height/4))))
            for side in ('L', 'R'):
                touch = b.x-b.radius <= EPS if side == 'L' else b.x+b.radius >= self.p.width-EPS
                if touch and self.solid(b, side):
                    value = self.audit[b.id]['L']*b.radius/self.p.reference_radius
                    w = self.walls[f'{side}{index}']
                    w['contacts'].append(b.id)
                    w['contributions'].append({'ball': b.id, 'contact_point': [0. if side=='L' else self.p.width,b.y],
                                               'normal': [1. if side=='L' else -1.,0.],
                                               'L': self.audit[b.id]['L'], 'radius': b.radius,
                                               'reference_radius': self.p.reference_radius,
                                               'contribution': value})
        for w in self.walls.values():
            w['sum'] = sum(c['contribution'] for c in w['contributions'])
            w['W'] = min(1., max(0., w['sum']/self.p.wall_capacity))
        return normals

    def piston_trial(self, balls, target):
        if target == self.height:
            # A fixed retracted/held piston has no motion to bisect. Residual
            # settling constraints retain their explicit finite validation.
            best, _ = self.project(balls, self.height)
            return best, self.height, False
        trial, ok = self.project(balls, target)
        if ok:
            return trial, target, False
        # A failed compression trial may still close the genuine free gap to
        # the highest surface. This avoids hovering just outside contact EPS.
        surface = max((b.y+b.radius for b in balls.values() if b.status=='inside'),default=target)
        contact_height = min(self.height, max(target, surface))
        contact, valid = self.project(balls, contact_height)
        if valid:
            return contact, contact_height, True
        # Roll back only this bounded substep, never the whole growing gap.
        best, _ = self.project(balls, self.height)
        return best, self.height, True

    def physics(self, target=None):
        dt = 1/(HZ*self.p.physics_substeps)
        blocked = False
        for _ in range(self.p.physics_substeps):
            old = self.balls
            radius = min((b.radius for b in self.inside()), default=self.p.reference_radius)
            step = min(self.p.catchup_speed*dt, radius/4)
            proposed = self.height if target is None else max(target, self.height-step)
            pushed, self.height, jam = self.piston_trial(old, proposed)
            blocked |= jam
            damping = math.exp(-self.p.damping_per_second*dt)
            predicted = {k: replace(b, x=b.x+old[k].vx*damping*dt,
                                    y=b.y+(old[k].vy-self.p.gravity*dt)*damping*dt)
                         for k,b in pushed.items()}
            moved, _ = self.project(predicted, self.height)
            self.balls = {k: replace(b, vx=(b.x-old[k].x)/dt, vy=(b.y-old[k].y)/dt)
                          for k,b in moved.items()}
        return blocked

    def geometry_failure(self):
        if not all(math.isfinite(v) for b in self.balls.values()
                   for v in (b.x,b.y,b.vx,b.vy,b.radius)):
            return 'nonfinite_state'
        depth = self.penetration(self.balls, self.height)
        radius = min((b.radius for b in self.inside()), default=1.)
        if depth/radius > self.p.excessive_overlap_ratio:
            return 'severe_unresolved_overlap'
        return None

    def movement(self):
        before = encoded(self.state())
        old_drive, old_stall = dict(self.drive), self.stalled
        self.stalled = self.physics(self.commanded_height())
        self.contacts()
        self.notify_contact()
        failure = self.geometry_failure()
        if failure:
            self.finish('invalid', failure, 'simulation_invalid')
            return
        current = self.drive_metrics()
        if self.stalled != old_stall:
            self.emit('piston_blocked' if self.stalled else 'piston_unblocked',
                      {'drive': current, 'reason': 'constraint_trial_unresolved'}, before)
        if old_drive['debt'] <= 1e-12 < current['debt']:
            self.emit('compression_debt_positive', {'previous_drive': old_drive, 'drive': current})
        elif current['debt'] <= 1e-12 < old_drive['debt']:
            self.emit('compression_debt_cleared', {'previous_drive': old_drive, 'drive': current})
        if any(round(t*HZ)==self.tick for t,_ in self.p.schedule):
            self.emit('compression_advanced', {'drive': current, 'schedule_knot': True}, before)

    def qualifications(self):
        if self.outcome:
            return {'crush': [], 'rupture': [], 'split': []}
        return super().qualifications()

    def transitions(self, latched, normals):
        if self.outcome:
            return
        for section in latched['rupture']:
            self.emit('wall_rupture_qualified', {'section': section, 'wall': self.walls[section],
                                               'duration_ticks': self.wall_clocks[section]})
        if latched['rupture']:
            self.frozen_command = self.commanded_height()
        super().transitions(latched, normals)

    def prepare(self):
        self.mode = 'settling'
        self.height = self.p.height
        self.preparation.update(status='running')
        self.contacts()
        self.emit('settling_started', {'phase': 'settling', 'retracted_height': self.height,
                                      'gravity': self.p.gravity, 'damping_per_second': self.p.damping_per_second})
        hold, previous, unresolved = 0, False, 0
        for tick in range(1, self.p.settling_max_ticks+1):
            self.physics()
            self.contacts()
            self.preparation['tick'] = tick
            failure = self.geometry_failure()
            depth = self.penetration(self.balls, self.height)
            speed = max(math.hypot(b.vx,b.vy) for b in self.balls.values())
            unresolved = unresolved+1 if depth > self.p.settling_penetration_tolerance else 0
            good = speed <= self.p.settling_speed_tolerance and depth <= self.p.settling_penetration_tolerance
            hold = hold+1 if good and previous else 0
            previous = good
            snapshot = {'rules': RULES, 'phase': 'settling', 'tick': tick, 'time': tick/HZ,
                        'max_speed': speed, 'max_penetration': depth, 'stable_intervals': hold,
                        'balls': [asdict(b) for _,b in sorted(self.balls.items())]}
            self.settling_samples.append(snapshot)
            if failure or unresolved >= self.p.overlap_ticks:
                return failure or 'settling_unresolved_overlap'
            if hold >= 30:
                frozen = {'rules': RULES, 'retracted_height': self.height,
                          'balls': snapshot['balls'], 'contacts': self.audit, 'walls': self.walls}
                self.preparation.update(status='completed', elapsed=tick/HZ,
                    settled_state_sha256=hashlib.sha256(encoded(frozen).encode()).hexdigest())
                self.emit('settling_completed', {'phase': 'settling', 'stable_intervals': hold,
                          'settled_state_sha256': self.preparation['settled_state_sha256']})
                return None
        return 'settling_time_limit'

    def run(self):
        reason = self.invalid_reason()
        frozen = None
        if not reason:
            try:
                reason = self.prepare()
            except _Budget:
                reason = 'settling_event_limit'
            if not reason:
                frozen = {'rules': RULES, 'retracted_height': self.height,
                          'balls': [asdict(b) for _,b in sorted(self.balls.items())],
                          'contacts': self.audit, 'walls': self.walls}
                self.height = command(self.p,0)
                if self.penetration(self.balls,self.height) > EPS:
                    reason = 'active_start_piston_intersects_settled_bed'
        if reason:
            self.preparation.update(status='failed', reason=reason)
            if len(self.events) < self.p.max_events-1:
                self.emit('settling_failed', {'phase': 'settling', 'reason': reason})
            self.finish('invalid', reason, 'simulation_invalid')
            result = Result(self.run_id,self.seed,self.p,encoded(self.state()),tuple(self.events),(),encoded(self.state()))
        else:
            self.mode = 'compression'
            self.drive = self.drive_metrics()
            result = super().run()
        preparation = {'rules': RULES, 'summary': self.preparation, 'frozen_state': frozen,
                       'samples': self.settling_samples}
        return Result12(result.run_id,result.seed,result.parameters,result.initial,result.events,
                        result.samples,result.final,encoded(preparation))


def simulate(balls: tuple[Ball,...], parameters: Parameters12 = Parameters12(), *,
             seed: int = 0, run_id: str = 'pressure-bloom-pb12') -> Result12:
    if not isinstance(parameters, Parameters12):
        raise TypeError('PB-1.2 requires explicit Parameters12; PB-1.1 entry point is unchanged')
    return _Engine12(balls,parameters,seed,run_id).run()
