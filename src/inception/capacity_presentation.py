"""Frozen PB-2.0 presentation only. No simulation, layout solver or sound imports."""
from dataclasses import dataclass
import hashlib
import json
import math
from PIL import Image,ImageDraw


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


@dataclass(frozen=True)
class Tape:
    frames: tuple[str,...]
    states: tuple[str,...]
    events: tuple[str,...]
    duration: float
    frame_count: int
    width: float
    height: float
    final_time: float

    @classmethod
    def from_record(cls,r):
        if r['schema']!='ms06.3d.frozen-timeline.v1' or r['rules']!='PB-2.0':raise ValueError('Unsupported frozen record')
        sim=r['simulation'];lt=r['layout'];p=r['presentation']
        for value,key in ((sim,'simulation_sha256'),(sim['events'],'event_sha256'),(lt,'layout_sha256'),(r['configuration'],'configuration_sha256'),(r['constants'],'rules_sha256')):
            if digest(value)!=r[key]:raise ValueError('Frozen hash mismatch: '+key)
        if sim['rules']!=r['constants'] or sim['configuration']!=r['configuration']:raise ValueError('Rules/configuration mismatch')
        if sim['final']['outcome']!='rupture' or lt['status']!='passed':raise ValueError('No qualified rupture/layout')
        if (p['width'],p['height'],p['fps'])!=(720,1280,30) or not 11<=p['duration']<=14:raise ValueError('Bad presentation')
        if p['frame_count']!=len(lt['frames']) or p['frame_count']!=round(p['duration']*30):raise ValueError('Missing layout frames')
        if [s['tick'] for s in sim['states']]!=list(range(1,sim['final']['tick']+1)):raise ValueError('Missing logical ticks')
        if [e['sequence'] for e in sim['events']]!=list(range(len(sim['events']))):raise ValueError('Incomplete events')
        if any(e['time']!=e['tick']/120 for e in sim['events']):raise ValueError('Bad absolute event clock')
        if sim['states'][-1]!=sim['final']:raise ValueError('Missing final state')
        states=[sim['initial'],*sim['states']]
        for i,f in enumerate(lt['frames']):
            if f['time']!=i/30:raise ValueError('Bad layout clock')
            logical=states[min(int(i/30*120+1e-8),len(states)-1)]
            expected={b['id']:b for b in logical['balls']}
            if {b['id'] for b in f['balls']}!=set(expected):raise ValueError('Layout membership changed')
            for b in f['balls']:
                if any(b[k]!=expected[b['id']][k] for k in ('radius','generation','lineage','parent','status')):
                    raise ValueError('Layout changed identity properties')
                if not math.isfinite(b['x']+b['y']):raise ValueError('Nonfinite layout')
        return cls(tuple(canonical(f) for f in lt['frames']),tuple(canonical(s) for s in states),
                   tuple(canonical(e) for e in sim['events']),p['duration'],p['frame_count'],
                   r['configuration']['width'],r['configuration']['schedule'][0][1],sim['final']['time'])

    def at(self,t):
        t=min(t,self.final_time)
        return (json.loads(self.frames[min(max(0,int(t*30+1e-8)),len(self.frames)-1)]),
                json.loads(self.states[min(max(0,int(t*120+1e-8)),len(self.states)-1)]))


COLORS={'cyan':(11,232,250),'orange':(255,119,30)}


class Renderer:
    def __init__(self,tape,ss=2):
        self.tape=tape;self.ss=ss;self.scale=560/tape.width;self.left=64;self.floor=1080
        self.events=[json.loads(e) for e in tape.events]
        self.splits=[e for e in self.events if e['kind']=='ball_split']
        self.crushes=[e for e in self.events if e['kind']=='ball_crushed']
        self.child_events={b['id']:e for e in self.splits for b in e['payload']['children']}

    def xy(self,x,y):return ((self.left+x*self.scale)*self.ss,(self.floor-y*self.scale)*self.ss)

    def render(self,t):
        f,s=self.tape.at(t);ss=self.ss;now=min(t,self.tape.final_time);scale=self.scale
        image=Image.new('RGB',(720*ss,1280*ss),(7,12,23));d=ImageDraw.Draw(image)
        x0,fy=self.xy(0,0);x1,top=self.xy(self.tape.width,self.tape.height)
        py=self.xy(0,f['height'])[1];cx=(x0+x1)/2
        # Original graphic mechanism: glass sleeve, broad floating compression
        # head and a central guide. No machine branding or UI.
        d.rounded_rectangle((x0-19*ss,top-25*ss,x1+19*ss,fy+24*ss),radius=19*ss,
                            fill=(14,28,40),outline=(43,71,85),width=3*ss)
        d.rectangle((x0,top,x1,fy),fill=(9,24,34))
        d.rounded_rectangle((cx-37*ss,125*ss,cx+37*ss,py-30*ss),radius=12*ss,
                            fill=(30,48,65),outline=(105,139,153),width=4*ss)
        for y in range(170,int(py/ss)-95,48):
            d.line((cx-25*ss,y*ss,cx+25*ss,y*ss),fill=(49,75,91),width=2*ss)
        for side in ('L','R'):
            x=x0 if side=='L' else x1
            for part in (0,1):
                key=f'{side}{part}';hi=self.xy(0,(part+1)*self.tape.height/2)[1];lo=self.xy(0,part*self.tape.height/2)[1]
                wall=s['capacity']['walls'][key];stress=wall['W'];strained=stress>=.6
                flex=max(0.,(stress-.6)/.4)*13*ss*(-1 if side=='L' else 1)
                if s['opening']==key:
                    event=next(e for e in self.events if e['kind']=='wall_ruptured')
                    u=min(1.,max(0.,(now-event['time'])/.2));away=(-1 if side=='L' else 1)*50*ss*u
                    d.line([(x+away,hi),(x+away*1.7,(hi+lo)/2),(x+away,lo)],fill=(94,126,139),width=7*ss)
                    continue
                color=(255,168,74) if strained else (108,172,192)
                d.line([(x,hi),(x+flex,(hi+lo)/2),(x,lo)],fill=color,width=8*ss)
                if strained:
                    amount=max(1,min(4,int((stress-.6)*15)+1));mid=(hi+lo)/2
                    for j in range(amount):
                        y=mid+(j-1.5)*30*ss
                        d.line([(x,y-16*ss),(x+flex+(-9 if side=='L' else 9)*ss,y),
                                (x-flex*.3,y+19*ss)],fill=(255,213,157),width=3*ss)
        d.rounded_rectangle((x0-15*ss,fy-3*ss,x1+15*ss,fy+20*ss),radius=7*ss,
                            fill=(66,105,121),outline=(148,199,211),width=3*ss)
        d.polygon([(x0-11*ss,py-83*ss),(x1+11*ss,py-83*ss),(x1+19*ss,py-36*ss),
                   (x1,py),(x0,py),(x0-19*ss,py-36*ss)],fill=(66,88,106),outline=(175,205,215),width=4*ss)
        d.line((x0+16*ss,py-16*ss,x1-16*ss,py-16*ss),fill=(255,198,84),width=7*ss)
        upcoming={e['payload']['parent']['id']:max(0.,1-(e['time']-now)/.16) for e in self.splits if 0<=e['time']-now<.16}
        poses={b['id']:b for b in f['balls']}
        for b in sorted(f['balls'],key=lambda b:b['id']):
            x,y=self.xy(b['x'],b['y']);r=b['radius']*scale*ss;color=COLORS[b['lineage']]
            load=max(0.,min(1.,(f['R']-.8)/.95));bulge=upcoming.get(b['id'],0.)
            ry=r*max(.48,min(.95,1/max(f['R'],.9)));rx=r*.94
            rx*=1+.10*bulge;ry*=1-.16*bulge
            born=self.child_events.get(b['id'])
            if born and 0<=now-born['time']<.12:
                age=(now-born['time'])/.12;rx*=.88+.12*age;ry*=1.1-.1*age
            if load>.2 and b['status']=='inside':
                glow=tuple(min(255,round(c*.65+90*load)) for c in color)
                d.ellipse((x-rx-3*ss,y-ry-3*ss,x+rx+3*ss,y+ry+3*ss),outline=glow,width=2*ss)
            d.ellipse((x-rx,y-ry,x+rx,y+ry),fill=color,outline=(2,10,19),width=3*ss)
            d.arc((x-rx*.7,y-ry*.7,x+rx*.7,y+ry*.7),205,275,fill=tuple(min(255,c+60) for c in color),width=2*ss)
        # A short connector joins only the genuine child pair after birth.
        for e in self.splits:
            age=now-e['time'];children=e['payload']['children']
            if 0<=age<.11 and all(c['id'] in poses for c in children):
                a,b=(poses[c['id']] for c in children);xa,ya=self.xy(a['x'],a['y']);xb,yb=self.xy(b['x'],b['y'])
                width=max(ss,round(children[0]['radius']*scale*ss*.75*(1-age/.11)))
                d.line([(xa,ya),(xb,yb)],fill=COLORS[a['lineage']],width=width)
        for e in self.crushes:
            age=now-e['time']
            if not 0<=age<.14:continue
            before_index=max(0,min(len(self.tape.frames)-1,math.ceil(e['time']*30)-1))
            before=json.loads(self.tape.frames[before_index]);k=e['payload']['ball']['id']
            p=next((b for b in before['balls'] if b['id']==k),None)
            if p:
                x,y=self.xy(p['x'],p['y']);u=age/.14;r=p['radius']*scale*ss
                d.ellipse((x-r*(1-u),y-r*.35*(1-u),x+r*(1-u),y+r*.35*(1-u)),fill=(255,236,185))
                d.arc((x-r*(1+.6*u),y-r*.6,x+r*(1+.6*u),y+r*.6),0,360,fill=(162,185,185),width=max(ss,round(3*ss*(1-u))))
        return image.resize((720,1280),Image.Resampling.LANCZOS) if ss!=1 else image
