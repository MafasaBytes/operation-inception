"""PB-2.0 logical conformance only. No production scenario or media export."""
from collections import Counter
import json
import math
from pathlib import Path

from .capacity_bloom import RULES, canonical, digest, simulate
from .capacity_layout import layout

ROOT=Path(__file__).resolve().parents[2]
FIXTURE=ROOT/'fixtures/ms06.3d/pb2-conformance-v1.json'


def conformance(historical=True):
    fixture=json.loads(FIXTURE.read_text());assert fixture['rules']==RULES
    records=[]
    for cfg in fixture['scenarios']:
        r=simulate(cfg);replay=simulate(cfg)
        assert r==replay
        records.append({'configuration':cfg,'replay_identical':True,'simulation_sha256':digest(r.to_dict()),'simulation':r.to_dict()})
    by={x['configuration']['id'].split('.')[1]:x['simulation'] for x in records}
    splits=[e for e in by['split']['events'] if e['kind']=='ball_split']
    crush=[e for e in by['crush']['events'] if e['kind']=='ball_crushed']
    rupture=[e for e in by['rupture']['events'] if e['kind']=='wall_ruptured']
    allstates=[s for r in records for s in (r['simulation']['initial'],*r['simulation']['states']) if 'capacity' in s]
    arithmetic=all(math.isclose(s['capacity']['R'],s['capacity']['occupied_area']/s['capacity']['effective_capacity'],rel_tol=1e-12) for s in allstates)
    areas=all(math.isclose(sum(math.pi*b['radius']**2 for b in e['payload']['children']),math.pi*e['payload']['parent']['radius']**2*1.125,rel_tol=1e-12) for e in splits)
    cfg=next(c for c in fixture['scenarios'] if '.rupture.' in c['id']);r=simulate(cfg);before=digest(r.to_dict())
    l=layout(r.to_dict(),seed=3);failure=layout(r.to_dict(),force_failure=True)
    counts=lambda state:Counter(b['lineage'] for b in state['balls'])
    reversal=by['reversal']
    initial=counts(reversal['initial']);final=counts(reversal['final'])
    matrix={'deterministic_resistance_and_complete_logs':all(r['replay_identical'] for r in records),
            'capacity_arithmetic':arithmetic,'single_split_cadence':bool(splits) and all(b['tick']-a['tick']>=RULES['split_cadence_ticks'] for a,b in zip(splits,splits[1:])),
            'split_area_112_5_percent':areas,'crush_capacity_release':bool(crush) and all(e['payload']['R_after']<e['payload']['R_before'] for e in crush),
            'lineage_reversal':initial['cyan']>initial['orange'] and final['cyan']<final['orange'],
            'section_strain':any(e['kind']=='wall_strained' and e['payload']['strained'] for e in by['strain']['events']),
            'rupture_and_escapes':len(rupture)==1 and by['rupture']['final']['outcome']=='rupture' and sum(e['kind']=='ball_escaped' for e in by['rupture']['events'])>=2,
            'separate_containment':by['contain']['final']['outcome']=='containment',
            'extinction_draw_invalid':all(by[name]['final']['outcome']==out for name,out in [('extinction','extinction'),('draw','draw'),('invalid','invalid')]),
            'layout_independent':l['status']=='passed' and digest(r.to_dict())==before and simulate(cfg)==r,
            'forced_layout_failure_preserves_truth':failure['status']=='failed' and digest(r.to_dict())==before,
            'live_cap':max(len(s['balls']) for s in by['live-cap']['states'])<=96,
            'event_limit':by['event-limit']['final']['outcome']=='draw' and len(by['event-limit']['events'])<=2}
    compatibility=None
    if historical:
        from .ms06_2b import conformance as old_conformance
        old=old_conformance()
        matrix['pb11_pb12_reproducible']=all(old['reachability_matrix'].values())
        compatibility={'pb11':old['pb11_compatibility'],'pb12_reachability':old['reachability_matrix']}
    return {'schema':'pb2.conformance.v1','rules':RULES,'rules_sha256':digest(RULES),
            'passed':all(matrix.values()),'reachability_matrix':matrix,
            'compatibility':compatibility,'scenarios':records,
            'layout_proof':{'successful_status':l['status'],'forced_failure_status':failure['status'],'truth_sha256':before}}


if __name__=='__main__':
    path=ROOT/'outputs/ms06.3d/ms06.3d-conformance-v1.json'
    if path.exists():raise FileExistsError(path)
    record=conformance()
    record['source_sha256']={str(p.relative_to(ROOT)):__import__('hashlib').sha256(p.read_bytes()).hexdigest() for p in (Path(__file__),ROOT/'src/inception/capacity_bloom.py',ROOT/'src/inception/capacity_layout.py',FIXTURE,ROOT/'fixtures/ms06.3d/pb2-rules-v1.json')}
    path.write_text(canonical(record)+'\n')
    print(json.dumps({'passed':record['passed'],'matrix':record['reachability_matrix'],'rules_sha256':record['rules_sha256']},indent=2))
    if not record['passed']:raise SystemExit('Conformance gate failed: stop before scenario authoring.')
