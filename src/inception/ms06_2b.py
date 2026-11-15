"""PB-1.2 logical conformance only. Never regenerates a historical output."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from .pressure_bloom import Ball, encoded
from .pressure_bloom_v12 import RULES, Parameters12, simulate

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT/'fixtures/ms06.2b/pb12-conformance-v1.json'


def sha(value):
    return hashlib.sha256(encoded(value).encode()).hexdigest()


def load_fixture(path=FIXTURE):
    record=json.loads(Path(path).read_text())
    if record['schema']!='ms06.2b.pb12-fixtures.v1' or record['rules']!=RULES:
        raise ValueError('Explicit PB-1.2 fixture required')
    return record


def run_case(case):
    if case['rules']!=RULES:
        raise ValueError('Mixed rule versions in PB-1.2 fixture')
    balls=[]
    for spec in case['balls']:
        spec=dict(spec)
        if spec['x']=='nan':
            spec['x']=float('nan')
        balls.append(Ball(**spec))
    return simulate(tuple(balls),Parameters12(**case['parameters']),seed=case['seed'],run_id=case['id'])


def check_expected(case,result):
    data=result.to_dict()
    events=data['events'];final=data['final']
    for key,expected in case['expected'].items():
        if key in ('outcome','reason'):
            actual=final[key]
        elif key=='final_tick':
            actual=final['tick']
        else:
            actual=sum(e['kind']==key for e in events)
        if actual!=expected:
            raise AssertionError(f"{case['id']} {key}: {actual!r} != {expected!r}")
    return data


def prove(records):
    by_id={r['configuration']['id'].split('.')[1]:r['simulation'] for r in records}
    def events(s,kind):return [e for e in s['events'] if e['kind']==kind]
    free=by_id['free-travel'];jam=by_id['jam-pressure'];crush=by_id['crush-release']
    settling=by_id['settling'];wall=by_id['wall-strain'];rupture=by_id['rupture-escape']
    failure=by_id['settling-failure'];sub=by_id['sub-strain'];contain=by_id['containment']
    jr=[s for s in jam['samples'] if s['first_contact']]
    ce=events(crush,'ball_crushed')[0]
    after=[s for s in crush['samples'] if s['tick']>ce['tick']]
    re=events(rupture,'wall_ruptured')[0]
    prep=settling['settlement']
    matrix={
      'free_travel':all(abs(s['height']-s['command_height'])<1e-12 and s['piston']['debt']==0
                        for s in free['samples']) and free['initial']['height']>free['final']['height'],
      'jam_pressure':max(s['height'] for s in jr)-min(s['height'] for s in jr)<1e-5
                    and jr[-1]['piston']['debt']>jr[0]['piston']['debt']+.05
                    and max(a['L'] for a in jr[-1]['loads'].values())>
                        max(a['L'] for a in jr[0]['loads'].values())+.2,
      'crush_release':ce['after']['occupied_area']<ce['before']['occupied_area']
                       and any(s['piston']['debt']<ce['after']['piston']['debt']-.02
                               and s['piston']['achieved_travel']>ce['after']['piston']['achieved_travel']+.02 for s in after)
                       and bool(events(crush,'compression_debt_cleared')),
      'pre_settling':prep['summary']['status']=='completed' and prep['summary']['elapsed']>0
                     and sha(prep['frozen_state'])==prep['summary']['settled_state_sha256']
                     and settling['initial']['time']==0,
      'settling_failure':failure['final']['outcome']=='invalid' and failure['final']['reason']=='settling_time_limit',
      'sub_strain_wall_contact':any(w['W']>0 for s in sub['samples'] for w in s['walls'].values())
                              and all(w['W']<.6 for s in sub['samples'] for w in s['walls'].values()),
      'wall_strain':bool(events(wall,'wall_strained')) and not events(wall,'wall_ruptured')
                    and any(w['W']>=.6 and len(w['contributions'])>1 for s in wall['samples'] for w in s['walls'].values()),
      'rupture_escape':rupture['final']['outcome']=='rupture' and re['payload']['duration_ticks']==48
                        and re['payload']['qualification']['W']>=.8
                        and len(events(rupture,'ball_escaped'))==8
                        and rupture['final']['tick']-re['tick']==72,
      'containment':contain['final']['outcome']=='containment' and not events(contain,'wall_ruptured'),
      'nonprogress':by_id['nonprogress']['final']['reason']=='nonprogress',
      'invalid_state':all(by_id[k]['final']['outcome']=='invalid' for k in ('invalid-nonfinite','invalid-overlap')),
      'split_generation_control':len(events(by_id['split-generation-control'],'ball_split'))==7
                                 and len(by_id['split-generation-control']['final']['balls'])==8
                                 and all(b['generation']==3 for b in by_id['split-generation-control']['final']['balls']),
      'rupture_not_universal':len({s['final']['outcome'] for s in by_id.values()})>=4,
    }
    if not all(matrix.values()):
        raise AssertionError(f'PB-1.2 reachability failed: {matrix}')
    return matrix


def compatibility():
    # Recompute in memory; NEVER invoke the old writer or touch its output.
    from .ms06_2 import conformance
    path=ROOT/'outputs/ms06.2/ms06.2-conformance-v1.json'
    expected=path.read_bytes()
    replay=(encoded(conformance(ROOT/'fixtures/ms06.2/conformance-v1.json'))+'\n').encode()
    if replay!=expected:
        raise AssertionError('PB-1.1 conformance bytes changed')
    return {'rules':RULES,'compared_version':'PB-1.1','scenario_count':16,
            'byte_identical':True,'preserved_output_sha256':hashlib.sha256(expected).hexdigest()}


def conformance(path=FIXTURE):
    fixture=load_fixture(path);records=[]
    for case in fixture['scenarios']:
        print(f"PB-1.2 conformance: {case['id']}",flush=True)
        result=run_case(case)
        data=check_expected(case,result)
        replay=run_case(case)
        if result!=replay:
            raise AssertionError(f"Nondeterministic replay: {case['id']}")
        meaningful=sorted({e['tick'] for e in data['events']}|{data['final']['tick']})
        states={s['tick']:s for s in [data['initial'],*data['samples']]}
        records.append({'rules':RULES,'configuration':case,'simulation':data,
                        'simulation_sha256':sha(data),'event_sha256':sha(data['events']),
                        'replay_byte_identical':encoded(data)==encoded(replay.to_dict()),
                        'diagnostics_at_semantic_ticks':[{'rules':RULES,'tick':t,'piston':states[t]['piston'],
                            'walls':states[t]['walls']} for t in meaningful]})
    matrix=prove(records)
    comp=compatibility();matrix['pb11_compatibility']=comp['byte_identical']
    sources={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (
        Path(__file__),Path(__file__).with_name('pressure_bloom_v12.py'),
        Path(__file__).with_name('pressure_bloom.py'),Path(path))}
    return {'schema':'ms06.2b.pb12-conformance.v1','rules':RULES,
            'manifest':{'rules':RULES,'source_sha256':sources,'fixture_sha256':hashlib.sha256(Path(path).read_bytes()).hexdigest(),
                        'reproducibility':'Same inputs/seed and numeric environment; no runtime timestamps'},
            'reachability_matrix':matrix,'pb11_compatibility':comp,'scenarios':records}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture',type=Path,default=FIXTURE)
    parser.add_argument('--output',type=Path,default=ROOT/'outputs/ms06.2b/ms06.2b-conformance-v1.json')
    args=parser.parse_args()
    if args.output.exists():
        raise FileExistsError('Preserve an existing conformance record; use a new output path')
    record=conformance(args.fixture)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(encoded(record)+'\n')
    print(f"PB-1.2: {len(record['scenarios'])} scenarios and all reachability proofs passed: {args.output}")


if __name__=='__main__':
    main()
