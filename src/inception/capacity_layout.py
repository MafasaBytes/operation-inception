"""PB-2.0 presentation positions. Receives frozen dictionaries, never rules calls."""
from __future__ import annotations

import hashlib
import math
import numpy as np


def layout(simulation, seed=0, force_failure=False):
    """Return independent 30 Hz positions or an explicit presentation failure.

    Radii and membership are logical truth. Elliptical display constraints and
    soft overlap are presentation choices, not gameplay physics.
    """
    if force_failure:
        return {'schema':'pb2.layout.v1','rules':'PB-2.0','status':'failed','reason':'forced_test_failure','frames':[]}
    if simulation['final']['outcome'] not in ('rupture','containment','extinction'):
        return {'schema':'pb2.layout.v1','rules':'PB-2.0','status':'failed','reason':'unresolved_rules','frames':[]}
    cfg=simulation['configuration'];W=cfg['width'];H0=cfg['schedule'][0][1]
    rng=np.random.default_rng(seed)
    poses={};retired={};frames=[];max_overlap=0.
    initial=simulation['initial'];states=simulation['states'];events=simulation['events']
    escapes={e['payload']['ball']['id']:e for e in events if e['kind']=='ball_escaped'}
    duration=math.ceil((simulation['final']['time']+.4)*30)/30
    children={c['id']:e['payload']['parent']['id'] for e in events if e['kind']=='ball_split' for c in e['payload']['children']}
    split_t={c['id']:e['time'] for e in events if e['kind']=='ball_split' for c in e['payload']['children']}
    for frame in range(round(duration*30)):
        t=frame/30;index=min(int(t*120+1e-8),len(states))
        state=initial if index==0 else states[index-1];H=state['height'];R=state['capacity']['R']
        members=state['balls'];inside=sorted((b for b in members if b['status']=='inside'),key=lambda b:b['id'])
        current={b['id'] for b in inside}
        for k in list(poses):
            if k not in current:retired[k]=poses.pop(k)
        for b in inside:
            k=b['id'];r=b['radius']
            if k not in poses:
                parent=children.get(k)
                if parent in retired:
                    p=retired[parent];sgn=-1 if k.endswith('.0') else 1
                    poses[k]=np.array([p[0]+sgn*r*.48,p[1]])
                else:poses[k]=np.array([rng.uniform(r,W-r),rng.uniform(r,H-r)])
        if inside:
            positions=np.array([poses[b['id']] for b in inside]);r=np.array([b['radius'] for b in inside])
            # Compression visibly acts through the entire layout. Flatten the
            # display footprint at high R; identity/radius records stay untouched.
            squash=max(.48,min(.95,1/max(R,.9)))
            ry=r*squash;rx=r*.94
            if np.any(2*rx>W) or np.any(2*ry>H):
                return {'schema':'pb2.layout.v1','rules':'PB-2.0','status':'failed','reason':'display_ball_exceeds_chamber','frames':[]}
            iterations=350 if frame==0 else 14
            for step in range(iterations):
                positions[:,1]-=.0003
                positions[:,0]=np.clip(positions[:,0],rx,W-rx)
                positions[:,1]=np.clip(positions[:,1],ry,H-ry)
                delta=positions[:,None,:]-positions[None,:,:]
                delta[:,:,1]/=squash
                dist=np.sqrt(np.sum(delta*delta,axis=2))
                desired=(r[:,None]+r[None,:])*.93
                penetration=np.maximum(0.,desired-dist);np.fill_diagonal(penetration,0.)
                correction=delta/np.maximum(dist[:,:,None],1e-9)*penetration[:,:,None]*.24
                correction[:,:,1]*=squash
                positions+=np.sum(correction,axis=1)
            positions[:,0]=np.clip(positions[:,0],rx,W-rx)
            positions[:,1]=np.clip(positions[:,1],ry,H-ry)
            for i,b in enumerate(inside):poses[b['id']]=positions[i]
        rendered=[]
        for b in members:
            k=b['id'];r=b['radius'];p=poses.get(k,retired.get(k,np.array([W/2,H/2]))).copy()
            escape=escapes.get(k)
            if escape and t>=escape['time']-.35:
                section=escape['payload']['section'];left=section.startswith('L')
                lo=(0 if section.endswith('0') else H0/2)
                hi=min(H,lo+H0/2)
                if hi-lo<2*r*.55:
                    return {'schema':'pb2.layout.v1','rules':'PB-2.0','status':'failed','reason':'opening_inaccessible','frames':[]}
                target=np.array([-r if left else W+r,(lo+hi)/2])
                u=min(1.,max(0.,(t-(escape['time']-.35))/.35));p=p*(1-u)+target*u
                if t>=escape['time']:
                    p[0]+=(-1 if left else 1)*(t-escape['time'])*W*.95
            rendered.append({**b,'x':float(p[0]),'y':float(p[1])})
        if not all(math.isfinite(b['x']+b['y']) for b in rendered):
            return {'schema':'pb2.layout.v1','rules':'PB-2.0','status':'failed','reason':'nonfinite_position','frames':[]}
        frames.append({'time':t,'tick':state['tick'],'height':H,'R':R,'balls':rendered})
    minimum=min((b['radius']*560/W for f in frames for b in f['balls']),default=0.)
    return {'schema':'pb2.layout.v1','rules':'PB-2.0','status':'passed' if minimum>=8 else 'failed',
            'reason':None if minimum>=8 else 'display_radius_below_8px','seed':seed,
            'minimum_nominal_radius_pixels':minimum,'duration':duration,'frame_count':len(frames),'frames':frames}
