"""MS06.3 frozen-log presentation. No rules engine, transitions or sound imports."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw

COLORS = {"cyan": (19, 229, 246), "orange": (255, 143, 52), "magenta": (238, 74, 170)}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


@dataclass(frozen=True)
class FrozenTape:
    initial: str
    samples: tuple[str, ...]
    final: str
    events: tuple[str, ...]
    duration: float
    frame_count: int
    width_world: float
    height_world: float
    simulation_sha256: str
    event_sha256: str

    @classmethod
    def from_record(cls, record: dict):
        if record["schema"] != "ms06.3.frozen-timeline.v1" or record["rules"] != "PB-1.1":
            raise ValueError("Unsupported frozen PB timeline")
        sim = record["simulation"]
        if sha(sim) != record["simulation_sha256"] or sha(sim["events"]) != record["event_sha256"]:
            raise ValueError("Frozen simulation/event hash mismatch")
        if sim["final"]["outcome"] not in ("rupture", "containment"):
            raise ValueError("This prototype requires a genuinely resolved rupture or containment")
        if [e["sequence"] for e in sim["events"]] != list(range(len(sim["events"]))):
            raise ValueError("Incomplete semantic sequence")
        if sim["samples"][-1] != sim["final"] or sim["hz"] != 120:
            raise ValueError("Incomplete fixed-clock state history")
        if [s["tick"] for s in sim["samples"]] != list(range(1, sim["final"]["tick"]+1)):
            raise ValueError("Missing committed simulation tick")
        if any(e["time"] != e["tick"]/120 for e in sim["events"]):
            raise ValueError("Event time is inconsistent with simulation clock")
        p = record["presentation"]
        if (p["width"], p["height"], p["fps"]) != (720, 1280, 30):
            raise ValueError("MS06.3 review is fixed at 720x1280/30")
        if not 14 <= p["duration"] <= 18 or p["frame_count"] != round(p["duration"]*30):
            raise ValueError("Invalid review duration")
        return cls(canonical(sim["initial"]), tuple(canonical(s) for s in sim["samples"]),
                   canonical(sim["final"]), tuple(canonical(e) for e in sim["events"]),
                   p["duration"], p["frame_count"], sim["parameters"]["width"],
                   sim["parameters"]["height"], record["simulation_sha256"], record["event_sha256"])

    @classmethod
    def read(cls, path: Path):
        return cls.from_record(json.loads(path.read_text(encoding="utf-8")))

    def state_at(self, seconds: float) -> dict:
        """Interpolate only continuous pose of identities alive at both ticks.

        Membership and all discrete truth are the preceding committed state.
        A child never exists before its logged birth; a crushed ball never stays
        in the active population after its event. Later collapse art is an effect.
        """
        index = min(max(0, math.floor(seconds*120+1e-8)), len(self.samples))
        a = json.loads(self.initial if index == 0 else self.samples[index-1])
        if index >= len(self.samples):
            return a
        b = json.loads(self.samples[index])
        f = min(1., max(0., seconds*120-index))
        a["height"] += (b["height"]-a["height"])*f
        other = {x["id"]: x for x in b["balls"]}
        for ball in a["balls"]:
            nxt = other.get(ball["id"])
            if nxt and nxt["status"] == ball["status"]:
                for key in ("x", "y"):
                    ball[key] += (nxt[key]-ball[key])*f
        return a


class PressureRenderer:
    """Fixed camera; visual deformations decorate logged geometry only."""
    def __init__(self, tape: FrozenTape, supersample: int = 2):
        self.tape, self.ss = tape, supersample
        self.events = tuple(json.loads(e) for e in tape.events)
        self.split_by_child = {c["id"]: e for e in self.events if e["kind"] == "ball_split"
                               for c in e["payload"]["birth_children"]}
        self.scale = min(440/tape.width_world, 968/tape.height_world)
        self.left = 90.
        self.floor = 1050.

    def xy(self, x, y):
        return ((self.left+x*self.scale)*self.ss, (self.floor-y*self.scale)*self.ss)

    def render(self, seconds: float) -> Image.Image:
        s, ss = self.tape.state_at(seconds), self.ss
        # Clamp effects as well as state after terminal time: unchanged final hold.
        effect_time = min(seconds, json.loads(self.tape.final)["time"]+.35)
        image = Image.new("RGB", (720*ss, 1280*ss), (8, 13, 25))
        d = ImageDraw.Draw(image)
        x0, fy = self.xy(0, 0)
        x1, top = self.xy(self.tape.width_world, self.tape.height_world)
        piston_y = self.xy(0, s["height"])[1]
        d.rounded_rectangle((x0-27*ss, top-22*ss, x1+27*ss, fy+28*ss),
                            radius=24*ss, fill=(13, 23, 37), outline=(25, 41, 57), width=3*ss)
        d.rectangle((x0, top, x1, fy), fill=(10, 22, 32))
        d.rectangle((x0+9*ss, top, x0+16*ss, fy), fill=(14, 30, 41))
        terminal = s["outcome"] in ("containment", "rupture")
        edge = (126, 216, 203) if terminal else (74, 111, 129)
        opening = s["opening"]
        for side in ("L", "R"):
            x = x0 if side == "L" else x1
            for panel in range(4):
                key = f"{side}{panel}"
                yhi = self.xy(0, (panel+1)*self.tape.height_world/4)[1]
                ylo = self.xy(0, panel*self.tape.height_world/4)[1]
                if opening and opening[0] == key:
                    continue
                w = s["walls"].get(key, {}).get("W", 0.)
                strain = max(0., (w-.6)/.4)
                flex = strain*6*ss*(-1 if side == "L" else 1)
                color = tuple(round(c+(h-c)*strain) for c,h in zip(edge,(255,178,100)))
                d.line([(x,yhi),(x+flex,(yhi+ylo)/2),(x,ylo)], fill=color, width=7*ss)
                d.line([(x+(3 if side=='L' else -3)*ss,yhi),
                        (x+(3 if side=='L' else -3)*ss,ylo)],fill=(142,181,193),width=ss)
                if strain > 0:
                    mid = (yhi+ylo)/2
                    d.line([(x,mid-18*ss),(x+flex+8*ss,mid),(x-5*ss,mid+16*ss)],
                           fill=(255,204,140),width=2*ss)
        d.rounded_rectangle((x0-15*ss,fy-4*ss,x1+15*ss,fy+18*ss),radius=6*ss,
                            fill=(76,105,117),outline=(151,188,193),width=2*ss)
        # Visible custom compression head and guide: no machinery branding.
        cx = (x0+x1)/2
        d.rounded_rectangle((cx-30*ss,top-22*ss,cx+30*ss,piston_y-48*ss),
                            radius=8*ss,fill=(37,55,69),outline=(82,111,127),width=3*ss)
        d.polygon([(x0-9*ss,piston_y-78*ss),(x1+9*ss,piston_y-78*ss),
                   (x1+20*ss,piston_y-42*ss),(x1,piston_y),(x0,piston_y),
                   (x0-20*ss,piston_y-42*ss)],fill=(62,82,100),outline=(153,180,194),width=3*ss)
        d.line([(x0+18*ss,piston_y-17*ss),(x1-18*ss,piston_y-17*ss)],
               fill=(137,206,208) if terminal else (255,180,86),width=5*ss)
        for b in sorted(s["balls"], key=lambda b:b["id"]):
            a = s["loads"].get(b["id"], {})
            load = a.get("L", 0.)
            x, y = self.xy(b["x"], b["y"])
            r = b["radius"]*self.scale*ss
            color = COLORS[b["lineage"]]
            stretch_x, stretch_y = 1+.12*load, 1/(1+.12*load)
            born = self.split_by_child.get(b["id"])
            if born and 0 <= effect_time-born["time"] < .12:
                u = (effect_time-born["time"])/.12
                stretch_x *= .82+.18*u
                stretch_y *= 1.22-.22*u
            clock = max(s["clocks"].get(b["id"]+":split",0)/36,
                        s["clocks"].get(b["id"]+":crush",0)/18)
            if load >= .5:
                glow = min(1., .25+.75*clock)
                bright = tuple(round(c*.35+160*glow) for c in color)
                bright = tuple(min(255,c) for c in bright)
                d.ellipse((x-r*stretch_x-3*ss,y-r*stretch_y-3*ss,
                           x+r*stretch_x+3*ss,y+r*stretch_y+3*ss),outline=bright,width=2*ss)
            rx, ry = r*stretch_x*.94, r*stretch_y*.94
            d.ellipse((x-rx,y-ry,x+rx,y+ry),fill=color,outline=(5,12,23),width=3*ss)
            if r > 13*ss:
                d.arc((x-rx*.67,y-ry*.67,x+rx*.67,y+ry*.67),205,280,
                      fill=tuple(min(255,c+65) for c in color),width=2*ss)
        for e in self.events:
            age = effect_time-e["time"]
            if not 0 <= age < .13:
                continue
            p = e["payload"]
            if e["kind"] == "ball_split":
                parent = p["parent"]
                x,y = self.xy(parent["x"],parent["y"])
                r = parent["radius"]*self.scale*ss
                d.arc((x-r,y-r*.45,x+r,y+r*.45),0,360,
                      fill=COLORS[parent["lineage"]],width=max(ss,round(3*ss*(1-age/.13))))
            elif e["kind"] == "ball_crushed":
                b = p["ball"];x,y=self.xy(b["x"],b["y"])
                r = b["radius"]*self.scale*ss*(1-age/.13)
                d.ellipse((x-r,y-r*.6,x+r,y+r*.6),fill=COLORS[b["lineage"]],outline=(255,226,192),width=ss)
        return image.resize((720,1280),Image.Resampling.LANCZOS) if ss != 1 else image
