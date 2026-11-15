"""PB-2.0: capacity rules only. No layout, media, numerical packing or audio."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


RULES = {
    'version': 'PB-2.0', 'hz': 120, 'packing_efficiency': .78,
    'split_base': .84, 'split_resistance_span': .18, 'split_ticks': 30,
    'split_cadence_ticks': 34, 'crush_base': 1.34, 'crush_resistance_span': .18,
    'crush_ticks': 18, 'crush_cadence_ticks': 66,
    'wall_pressure_span': .95, 'wall_strain': .60, 'wall_rupture': .80,
    'wall_ticks': 48, 'contain_ticks': 72, 'release_ticks': 84,
    'discharge_delay_ticks': 12, 'discharge_cadence_ticks': 7,
    'max_generation': 3, 'max_live': 96, 'max_events': 20000,
    'max_ticks': 2160, 'nonprogress_ticks': 240,
}
SECTIONS = ('L0', 'L1', 'R0', 'R1')


def unit(seed, identity, generation, domain):
    raw = hashlib.sha256(f'PB-2.0:{seed}:{identity}:{generation}:{domain}'.encode()).digest()
    return int.from_bytes(raw[:8], 'big') / 2**64


def ball_record(raw, seed):
    b = {k: raw[k] for k in ('id', 'lineage', 'generation', 'radius')}
    b['parent'] = raw.get('parent')
    b['status'] = 'inside'
    b['resistance'] = unit(seed, b['id'], b['generation'], 'resistance')
    weights = [.2 + .1*unit(seed,b['id'],b['generation'],s) for s in SECTIONS]
    b['affinity'] = dict(zip(SECTIONS, (w/sum(weights) for w in weights)))
    return b


def height_at(schedule, t):
    for (a,x),(b,y) in zip(schedule, schedule[1:]):
        if t <= b:
            return x+(y-x)*max(0.,t-a)/(b-a)
    return schedule[-1][1]


def capacity(balls, width, height, efficiency, weakness):
    members = sorted((b for b in balls if b['status']=='inside'),key=lambda b:b['id'])
    occupied = math.fsum(math.pi*b['radius']**2 for b in members)
    effective = width*height*efficiency
    ratio = occupied/effective
    walls={}
    for s in SECTIONS:
        contributions=[{'ball':b['id'],'area':math.pi*b['radius']**2,
                        'affinity':b['affinity'][s],
                        'assigned_area':math.pi*b['radius']**2*b['affinity'][s]} for b in members]
        assigned=math.fsum(c['assigned_area'] for c in contributions)
        share=4*assigned/occupied if occupied else 0.
        stress=min(1.,max(0.,ratio-1)/RULES['wall_pressure_span']*share*weakness[s])
        walls[s]={'assigned_area':assigned,'normalized_share':share,'weakness':weakness[s],
                  'W':stress,'contributions':contributions}
    return {'chamber_area':width*height,'effective_capacity':effective,
            'occupied_area':occupied,'R':ratio,'walls':walls}


@dataclass(frozen=True)
class Result:
    initial: str
    states: tuple[str, ...]
    events: tuple[str, ...]
    final: str
    configuration: str
    rules: str

    def to_dict(self):
        return {'schema':'pb2.simulation.v1','rules':json.loads(self.rules),
                'configuration':json.loads(self.configuration),'initial':json.loads(self.initial),
                'states':[json.loads(s) for s in self.states],
                'events':[json.loads(e) for e in self.events],'final':json.loads(self.final)}


def simulate(config):
    """Finite, fixed-clock deterministic capacity state machine."""
    cfg=json.loads(json.dumps(config))
    seed=cfg.get('seed',0);run_id=cfg.get('id','pb2')
    balls=[];events=[];states=[];tick=0;height=1.;mode='active';outcome=None;reason=None
    opening=None;rupture_tick=None;queue=[];split_clock={};crush_clock={};wall_clock={s:0 for s in SECTIONS}
    ready_s={};ready_c={};last_split=-10000;last_crush=-10000;hold=0;idle=0;prior=None
    strained=set();ended_lineages=set();last_signature=None
    max_ticks=cfg.get('max_ticks',RULES['max_ticks']);max_events=cfg.get('max_events',RULES['max_events'])

    def metrics():
        return capacity(balls,cfg['width'],height,cfg.get('packing_efficiency',RULES['packing_efficiency']),cfg['weakness'])

    def snapshot():
        return {'rules':'PB-2.0','tick':tick,'time':tick/120,'height':height,'mode':mode,
                'outcome':outcome,'reason':reason,'opening':opening,
                'balls':sorted(balls,key=lambda b:b['id']), 'capacity':metrics(),
                'clocks':{'split':dict(split_clock),'crush':dict(crush_clock),'wall':dict(wall_clock)},
                'nonprogress_ticks':idle}

    def emit(kind,payload,before=None):
        events.append(canonical({'rules':'PB-2.0','id':f'{run_id}:{len(events):05}',
                       'sequence':len(events),'tick':tick,'time':tick/120,'kind':kind,
                       'payload':payload,'before':before,'after':snapshot()}))

    try:
        if cfg.get('rules')!='PB-2.0':raise ValueError('wrong_rule_version')
        if not isinstance(seed,int):raise ValueError('seed_not_integer')
        for k in ('width','packing_efficiency'):
            v=cfg.get(k,RULES['packing_efficiency'])
            if not math.isfinite(v) or v<=0 or v>100:raise ValueError('invalid_'+k)
        if cfg.get('packing_efficiency',.78)>1:raise ValueError('invalid_efficiency')
        if set(cfg['weakness'])!=set(SECTIONS) or any(not math.isfinite(x) or x<=0 for x in cfg['weakness'].values()):
            raise ValueError('invalid_weakness')
        schedule=cfg['schedule']
        if not schedule or schedule[0][0]!=0:raise ValueError('invalid_schedule')
        for i,(t,h) in enumerate(schedule):
            if not math.isfinite(t+h) or t<0 or h<=0 or h>100:raise ValueError('invalid_schedule')
            if i and (t<=schedule[i-1][0] or h>schedule[i-1][1]):raise ValueError('invalid_schedule')
        if not 1<=max_ticks<=2160 or not 2<=max_events<=20000:raise ValueError('invalid_budget')
        height=schedule[0][1]
        if not 1<=len(cfg['balls'])<=96:raise ValueError('invalid_population')
        for raw in sorted(cfg['balls'],key=lambda b:b['id']):
            if not isinstance(raw['id'],str) or not raw['id']:raise ValueError('invalid_identity')
            if raw['generation'] not in range(4) or not math.isfinite(raw['radius']) or not 0<raw['radius']<=100:raise ValueError('invalid_ball')
            if not raw['lineage']:raise ValueError('invalid_lineage')
            balls.append(ball_record(raw,seed))
        if len({b['id'] for b in balls})!=len(balls):raise ValueError('duplicate_identity')
    except (ValueError,KeyError,TypeError,OverflowError) as error:
        # Rejected input is diagnostic data; do not run capacity arithmetic on it.
        bad={'rules':'PB-2.0','tick':0,'time':0.,'mode':'terminal','outcome':'invalid','reason':str(error),'balls':[]}
        e={'rules':'PB-2.0','id':f'{run_id}:00000','sequence':0,'tick':0,'time':0.,'kind':'simulation_invalid','payload':{'reason':str(error)},'before':None,'after':bad}
        def diagnostic(v):
            if isinstance(v,float) and not math.isfinite(v):return str(v)
            if isinstance(v,dict):return {k:diagnostic(x) for k,x in v.items()}
            if isinstance(v,list):return [diagnostic(x) for x in v]
            return v
        return Result(canonical(bad),(),(canonical(e),),canonical(bad),canonical(diagnostic(cfg)),canonical(RULES))

    initial=canonical(snapshot());lineages={b['lineage'] for b in balls}
    emit('press_engaged',{'schedule':schedule,'capacity':metrics()})

    for tick in range(1,max_ticks+1):
        if max_events-len(events)<len(lineages)+9:
            mode='terminal';outcome='draw';reason='event_ceiling';emit('simulation_draw',{})
            states.append(canonical(snapshot()));break
        if mode=='release':
            elapsed=tick-rupture_tick
            if queue and elapsed>=RULES['discharge_delay_ticks'] and (elapsed-RULES['discharge_delay_ticks'])%RULES['discharge_cadence_ticks']==0:
                identity=queue.pop(0);b=next(b for b in balls if b['id']==identity);before=snapshot()
                b['status']='escaped';emit('ball_escaped',{'ball':dict(b),'section':opening,'release_elapsed':elapsed/120},before)
            if elapsed>=RULES['release_ticks']:
                mode='terminal';outcome='rupture';reason='release_completed';emit('rupture_resolved',{'section':opening})
            if tick==max_ticks and outcome is None:
                mode='terminal';outcome='draw';reason='duration_ceiling_release_incomplete';emit('simulation_draw',{'locked_outcome':'rupture'})
            states.append(canonical(snapshot()))
            if outcome:break
            continue

        height=height_at(schedule,tick/120);m=metrics();R=m['R']
        inside=[b for b in balls if b['status']=='inside']
        live=len(balls)
        for b in inside:
            k=b['id'];u=b['resistance'];crush=R>=RULES['crush_base']+RULES['crush_resistance_span']*u
            split=(b['generation']<3 and live<96 and R>=RULES['split_base']+RULES['split_resistance_span']*u and not crush)
            for ok,clocks,ready,duration in ((split,split_clock,ready_s,RULES['split_ticks']),(crush,crush_clock,ready_c,RULES['crush_ticks'])):
                clocks[k]=clocks.get(k,0)+1 if ok else 0
                if not ok:ready.pop(k,None)
                elif clocks[k]>=duration:ready.setdefault(k,tick)
        due_w=[]
        for s in SECTIONS:
            W=m['walls'][s]['W'];wall_clock[s]=wall_clock[s]+1 if W>=RULES['wall_rupture'] else 0
            active=W>=RULES['wall_strain']
            if active!=(s in strained):
                if active:strained.add(s)
                else:strained.discard(s)
                emit('wall_strained',{'section':s,'strained':active,'wall':m['walls'][s]})
            if wall_clock[s]>=RULES['wall_ticks']:due_w.append(s)
        crushes=sorted((b for b in inside if b['id'] in ready_c),key=lambda b:(ready_c[b['id']],b['resistance'],b['id']))
        splits=sorted((b for b in inside if b['id'] in ready_s),key=lambda b:(ready_s[b['id']],b['resistance'],b['id']))
        if crushes and tick-last_crush>=RULES['crush_cadence_ticks']:
            b=crushes[0];qualified=ready_c[b['id']];before=snapshot();balls.remove(b);last_crush=tick
            for store in (split_clock,crush_clock,ready_s,ready_c):store.pop(b['id'],None)
            after=metrics()
            emit('ball_crushed',{'ball':b,'qualification_tick':qualified,
                 'occupied_before':before['capacity']['occupied_area'],'occupied_after':after['occupied_area'],
                 'R_before':before['capacity']['R'],'R_after':after['R']},before)
        if due_w:
            opening=sorted(due_w)[0];before=snapshot();rupture_tick=tick;mode='release'
            queue=[b['id'] for b in sorted(balls,key=lambda b:(-b['affinity'][opening],b['id']))
                   if max(SECTIONS,key=lambda s:(b['affinity'][s],s))==opening and b['status']=='inside']
            split_clock.clear();crush_clock.clear();ready_s.clear();ready_c.clear();wall_clock={s:0 for s in SECTIONS}
            emit('wall_ruptured',{'section':opening,'qualified_capacity':m,'duration':.4,'discharge_queue':queue.copy()},before)
        elif splits and tick-last_split>=RULES['split_cadence_ticks'] and len(balls)<96:
            b=splits[0]
            if b in balls:
                qualified=ready_s[b['id']];before=snapshot();balls.remove(b);last_split=tick
                children=[ball_record({'id':b['id']+f'.{i}','parent':b['id'],'lineage':b['lineage'],
                                       'generation':b['generation']+1,'radius':b['radius']*.75},seed) for i in range(2)]
                balls.extend(children)
                for store in (split_clock,crush_clock,ready_s,ready_c):store.pop(b['id'],None)
                emit('ball_split',{'parent':b,'children':children,'area_ratio':1.125,
                                  'qualified_tick':qualified},before)
        for lineage in sorted(lineages-ended_lineages):
            if not any(b['lineage']==lineage for b in balls):
                ended_lineages.add(lineage);emit('lineage_extinct',{'lineage':lineage})
        if not balls and mode!='release':
            mode='terminal';outcome='extinction';reason='all_balls_crushed';emit('population_extinct',{})
        if mode=='active':
            pending=bool(ready_s or ready_c or any(split_clock.values()) or any(crush_clock.values()) or any(wall_clock.values()))
            final=tick/120>=schedule[-1][0]
            hold=hold+1 if final and not pending else 0
            if hold>=RULES['contain_ticks']:
                mode='terminal';outcome='containment';reason='stable_capacity';emit('chamber_contained',{'hold':.6})
            signature=(height,tuple(b['id'] for b in balls),R)
            idle=idle+1 if final and pending and signature==last_signature else 0;last_signature=signature
            if idle>=RULES['nonprogress_ticks']:
                mode='terminal';outcome='draw';reason='nonprogress';emit('simulation_draw',{})
        if not outcome and tick>=max_ticks:
            mode='terminal';outcome='draw';reason='duration_ceiling';emit('simulation_draw',{})
        # A conservative event budget reserves enough for one entire worst tick.
        if not outcome and len(events)>=max_events-8:
            mode='terminal';outcome='draw';reason='event_ceiling';emit('simulation_draw',{})
        states.append(canonical(snapshot()))
        if outcome:break
    return Result(initial,tuple(states),tuple(events),canonical(snapshot()),canonical(cfg),canonical(RULES))
