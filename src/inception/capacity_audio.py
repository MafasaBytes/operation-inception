"""Sparse PB-2.0 sound adapter from immutable timed facts; no engine or renderer."""
import json
import math
import hashlib
import numpy as np

from .pressure_audio import synthesize as tones,write_wav


def map_events(events):
    data=[json.loads(e) if isinstance(e,str) else e for e in events]
    rupture=next(e for e in data if e['kind']=='wall_ruptured');end=rupture['time']
    mapped=[];last_split=-10.;last_strain=-10.
    for e in data:
        kind=e['kind'];t=e['time']
        if kind=='press_engaged':
            mapped.append(e)
            schedule=e['payload']['schedule'];knots=[(t,h) for t,h in schedule if 0<t<end]+[(end,rupture['after']['height'])]
            for j,(time,height) in enumerate(knots):
                mapped.append({'id':e['id']+f':motion{j}','kind':'compression_advanced','time':time,
                               'payload':{},'after':{'height':height}})
        elif kind=='ball_split' and (last_split<0 or t-last_split>=.50):
            mapped.append(e);last_split=t
        elif kind=='ball_crushed':mapped.append(e)
        elif kind=='wall_strained' and e['payload']['strained'] and t-last_strain>=.65:
            mapped.append(e);last_strain=t
        elif kind=='wall_ruptured':mapped.append(e)
        elif kind=='rupture_resolved':
            mapped.append({**e,'kind':'chamber_contained'})
    return tuple(json.dumps(e,sort_keys=True,separators=(',',':')) for e in sorted(mapped,key=lambda e:(e['time'],e['id'])))


def synthesize(events,duration,seed=6364):
    mapped=map_events(events);pcm,report=tones(mapped,duration,seed)
    rupture=next(json.loads(e)['time'] for e in mapped if json.loads(e)['kind']=='wall_ruptured')
    facts=[json.loads(e) if isinstance(e,str) else e for e in events]
    strain=next(e for e in facts if e['kind']=='wall_strained' and e['payload']['strained'])
    # One sustained rising texture replaces chatter: its entire interval is
    # bounded by genuine strain and rupture facts on the same absolute clock.
    start=round(strain['time']*48000);stop=round((rupture-.12)*48000)
    mixed=pcm.astype(float)/32767/max(report['master_gain'],1e-12)
    n=max(0,stop-start)
    if n:
        seconds=np.arange(n)/48000;u=np.arange(n)/max(1,n-1)
        phase=2*np.pi*(250*seconds+110*seconds**2/max(n/48000,1e-9))
        envelope=np.minimum(1.,seconds/.025)*np.minimum(1.,(n/48000-seconds)/.02)*(.025+.10*u*u)
        layer=(np.sin(phase)+.22*np.sin(phase*1.91))*envelope
        mixed[start:stop]+=layer[:,None]/np.sqrt(2)
        report['cues'].append({'event_id':strain['id'],'kind':'pressure_rise','time':strain['time'],
                              'duration':n/48000,'frequency_start':250,'frequency_end':470,
                              'amplitude_start':.025,'amplitude_end':.125,'pan':0.})
    pre_peak=float(np.max(np.abs(mixed)));gain=min(1.,.86/max(pre_peak,1e-12))
    pcm=np.rint(mixed*gain*32767).astype('<i2')
    report.update(pre_mix_peak=pre_peak,master_gain=gain,cue_count=len(report['cues']))
    # Shared dynamic space before genuine wall failure, without moving any cue.
    a=round((rupture-.12)*48000);b=round(rupture*48000)
    pcm=pcm.copy();pcm[max(0,a):b]=np.rint(pcm[max(0,a):b].astype(float)*.22).astype('<i2')
    peak=float(np.max(np.abs(pcm.astype(float)))/32768)
    report.update(peak=peak,peak_dbfs=20*math.log10(max(peak,1e-12)),
                  pcm_sha256=hashlib.sha256(pcm.tobytes()).hexdigest(),
                  rms_by_channel=np.sqrt(np.mean((pcm.astype(float)/32768)**2,axis=0)).tolist(),
                  mono_rms=float(np.sqrt(np.mean(np.mean(pcm.astype(float)/32768,axis=1)**2))),
                  sparse_mapping='first split isolated; later low-priority splits grouped >=.50s; all crushes retained',
                  pre_rupture_space_seconds=.12,pre_rupture_shared_gain=.22,
                  source_event_ids=[json.loads(e)['id'] for e in events])
    return pcm,report
