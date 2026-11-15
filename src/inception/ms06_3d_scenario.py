"""Single authored PB-2.0 prototype and eight bounded acceptance probes."""
import copy
import json
import math
from collections import Counter
from pathlib import Path

from .capacity_bloom import RULES,canonical,digest,simulate
from .capacity_layout import layout


def summary(sim):
    events=sim['events'];times={kind:[e['time'] for e in events if e['kind']==kind] for kind in sorted({e['kind'] for e in events})}
    states=[sim['initial'],*sim['states']];finite=all(math.isfinite(s['height']+s['capacity']['R']+s['capacity']['occupied_area']) for s in states)
    return {'outcome':sim['final']['outcome'],'reason':sim['final']['reason'],'terminal_time':sim['final']['time'],
            'event_counts':dict(Counter(e['kind'] for e in events)),'event_times':times,
            'peak_live':max(len(s['balls']) for s in states),'finite':finite,
            'capacity_history':[{'time':s['time'],'height':s['height'],'R':s['capacity']['R'],'occupied_area':s['capacity']['occupied_area'],'effective_capacity':s['capacity']['effective_capacity']} for s in states],
            'split_then_crush':bool(times.get('ball_split') and times.get('ball_crushed') and times['ball_split'][0]<times['ball_crushed'][-1]),
            'simulation_sha256':digest(sim),'events_sha256':digest(events)}


def base_gate(s):
    times=s['event_times'];splits=times.get('ball_split',[]);crush=times.get('ball_crushed',[]);rupture=times.get('wall_ruptured',[])
    early=sorted(t for kind in ('ball_split','ball_crushed','wall_ruptured') for t in times.get(kind,[]) if t<=3)
    teaching=max((sum(t<=v<t+.1-1e-12 for v in early) for t in early),default=0)
    return {'rupture':s['outcome']=='rupture','finite':s['finite'],
            'first_isolated_split':bool(splits and .8<=splits[0]<=1.4 and (len(splits)<2 or splits[1]-splits[0]>=.2)),
            'split_count':12<=len(splits)<=24,'crush_count':4<=len(crush)<=10,
            'crush_timing':bool(crush and 5<=crush[0]<=8),
            'rupture_timing':bool(rupture and 9<=rupture[0]<=12),
            'preceding_strain':bool(rupture and times.get('wall_strained') and times['wall_strained'][0]<=rupture[0]-.4),
            'escapes':len(times.get('ball_escaped',[]))>=2,'teaching_density':teaching<=2,
            'actual_duration':11<=s['terminal_time']<=14-.4,'phone_population':s['peak_live']<=64}


def nearby(cfg):
    probes=[]
    c=copy.deepcopy(cfg);c['seed']+=1;probes.append(('resistance-seed-plus-one',c))
    c=copy.deepcopy(cfg);c['layout_offset']=.0015;probes.append(('initial-layout-offset',c))
    for speed in (.97,1.03):
        c=copy.deepcopy(cfg);c['schedule']=[[t/speed,h] for t,h in c['schedule']];probes.append((f'piston-speed-{speed}',c))
    for delta in (-.005,.005):
        c=copy.deepcopy(cfg);c['packing_efficiency']+=delta;probes.append((f'packing-efficiency-{delta:+}',c))
    c=copy.deepcopy(cfg);c['schedule']=[[t+(1/120 if t else 0),h] for t,h in c['schedule']];probes.append(('engagement-plus-one-tick',c))
    c=copy.deepcopy(cfg);c['weakness']['L0']*=1.02;probes.append(('fixed-L0-weakness-plus-2-percent',c))
    return probes


def make_layout(sim,cfg):
    tape=layout(sim,cfg['layout_seed'])
    # This small opening-only pose perturbation is expressly absent from rules.
    if cfg.get('layout_offset') and tape['status']=='passed':
        for frame in tape['frames']:
            for i,b in enumerate(frame['balls']):
                b['x']+=cfg['layout_offset']*(-1 if i%2 else 1)*max(0.,1-frame['time'])
    return tape


def audit(cfg):
    proof=json.loads(Path('outputs/ms06.3d/ms06.3d-conformance-v1.json').read_text())
    if not proof['passed'] or proof['rules_sha256']!=digest(RULES):raise ValueError('Conformance/constants not frozen')
    r=simulate(cfg);sim=r.to_dict();s=summary(sim);gate=base_gate(s)
    report={'schema':'ms06.3d.robustness.v1','rules':'PB-2.0','rules_sha256':digest(RULES),
            'scenario_sha256':digest(cfg),'base':s,'base_gate':gate,'probes':[],
            'base_replay_identical':r==simulate(cfg),'passed':False}
    if not all(gate.values()):
        report['status']='base_gate_failed';return report,sim,None
    lt=make_layout(sim,cfg);report['base_layout']={k:v for k,v in lt.items() if k!='frames'}
    report['layout_sha256']=digest(lt)
    if lt['status']!='passed':
        report['status']='base_layout_failed';return report,sim,lt
    for name,c in nearby(cfg):
        r=simulate(c);data=r.to_dict();p=summary(data);l=make_layout(data,c)
        report['probes'].append({'probe':name,'configuration':c,**p,'deterministic':r==simulate(c),
                                 'layout_status':l['status'],'layout_reason':l['reason'],'layout_sha256':digest(l)})
        print(f"PB-2.0 probe {name}: {p['outcome']} at {p['terminal_time']:.3f}s; layout {l['status']}",flush=True)
    probes=report['probes'];valid={'rupture','containment','extinction'}
    checks={'base':all(gate.values()),'base_replay':report['base_replay_identical'],
            'all_replay':all(p['deterministic'] for p in probes),'all_finite':all(p['finite'] for p in probes),
            'six_valid':sum(p['outcome'] in valid for p in probes)>=6,
            'four_ruptures':sum(p['outcome']=='rupture' for p in probes)>=4,
            'five_split_then_crush':sum(p['split_then_crush'] for p in probes)>=5,
            'at_most_two_unresolved':sum(p['outcome'] not in valid for p in probes)<=2,
            'layout_success':lt['status']=='passed' and sum(p['layout_status']=='passed' for p in probes)>=6}
    report.update(gate=checks,passed=all(checks.values()),status='passed' if all(checks.values()) else 'robustness_failed')
    return report,sim,lt


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,default=Path('configs/ms06.3d.json'))
    parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args();cfg=json.loads(args.config.read_text())
    args.output_dir.mkdir(parents=True,exist_ok=True)
    report_path=args.output_dir/'ms06.3d-robustness.json';timeline=args.output_dir/'ms06.3d-timeline.json'
    if report_path.exists() or timeline.exists():raise FileExistsError('Preserve existing logical outputs')
    report,sim,lt=audit(cfg);report_path.write_text(canonical(report)+'\n')
    if not report['passed']:raise SystemExit('Pre-render gate failed; no timeline or media')
    record={'schema':'ms06.3d.frozen-timeline.v1','rules':'PB-2.0','constants':RULES,'rules_sha256':digest(RULES),
            'configuration':cfg,'configuration_sha256':digest(cfg),'simulation':sim,'simulation_sha256':digest(sim),
            'event_sha256':digest(sim['events']),'layout':lt,'layout_sha256':digest(lt),
            'presentation':{'width':720,'height':1280,'fps':30,'duration':lt['duration'],'frame_count':lt['frame_count'],
                            'clock':'one-to-one absolute seconds','unchanged_hold':lt['duration']-sim['final']['time']},
            'status':'owner-and-wife normal-speed phone review pending'}
    timeline.write_text(canonical(record)+'\n')
