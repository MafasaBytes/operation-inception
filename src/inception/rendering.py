"""Pillow renderer consuming numerical snapshots; never advances a simulation."""

import numpy as np
from PIL import Image, ImageColor, ImageDraw

from .config import RenderConfig
from .simulation import ParticleFrame


class PillowRenderer:
    def __init__(self, config: RenderConfig, width: int, height: int):
        self.config = config
        self.width, self.height = width, height
        self.scale = width * config.supersample
        self.size = (width * config.supersample, height * config.supersample)
        base = np.array(ImageColor.getrgb(config.background))
        y, x = np.ogrid[-1:1:complex(self.size[1]), -1:1:complex(self.size[0])]
        light = np.clip(1 - (x * x + y * y) / 2, 0, 1)
        pixels = np.clip(base + light[..., None] * np.array([5, 10, 13]) * config.background_bloom, 0, 255).astype("uint8")
        self.background = Image.fromarray(pixels)
        self.warm = np.array(ImageColor.getrgb(config.particle_color))
        self.accent = np.array(ImageColor.getrgb(config.accent_color))

    def render(self, frame: ParticleFrame, trail: ParticleFrame | None = None) -> Image.Image:
        canvas = self.background.copy()
        draw = ImageDraw.Draw(canvas, "RGBA")
        if frame.activation is not None:
            self._draw_beads(draw, frame, trail)
            if self.config.supersample > 1:
                canvas = canvas.resize((self.width, self.height), Image.Resampling.LANCZOS)
            return canvas
        pulse = self.config.resolution_pulse * np.sin(np.pi * frame.resolution) ** 2
        for i, (position, radius, group) in enumerate(zip(frame.positions, frame.radii, frame.groups)):
            x, y = position * self.scale
            r = radius * self.scale
            # Alternate shells reveal geometry gradually; colors stay attached to particles.
            color = self.accent if group % 3 == 0 else self.warm
            color = tuple(np.clip(color + (255 - color) * pulse, 0, 255).astype(int))
            if trail is not None:
                tx, ty = trail.positions[i] * self.scale
                draw.line((tx, ty, x, y), fill=(*color, 55), width=max(1, round(r)))
            draw.ellipse((x - 2*r, y - 2*r, x + 2*r, y + 2*r), fill=(*color, 12))
            draw.ellipse((x - 1.35*r, y - 1.35*r, x + 1.35*r, y + 1.35*r), fill=(*color, 28))
            draw.ellipse((x - r, y - r, x + r, y + r), fill=(*color, 255))
        if self.config.supersample > 1:
            canvas = canvas.resize((self.width, self.height), Image.Resampling.LANCZOS)
        return canvas

    def _draw_beads(self, draw, frame, trail):
        if frame.links is not None:
            for start, end, signal in frame.links:
                a, b = start*self.scale, end*self.scale
                draw.line((*a, *b), fill=(*map(int, self.accent), 28), width=max(1, round(self.scale*.0012)))
                point = a + (b-a)*min(1, signal[0])
                r = self.scale*.003
                draw.ellipse((* (point-r), *(point+r)), fill=(*map(int, self.accent), 200))
        if frame.slot is not None:
            x, y = frame.slot[:2]*self.scale
            r = frame.radii[0]*self.scale*1.08
            draw.ellipse((x-r, y-r, x+r, y+r), outline=(*map(int, self.accent), int(150*frame.slot[2])),
                         width=max(1, round(self.scale*.0022)))
        for i, position in enumerate(frame.positions):
            x, y = position*self.scale
            radius = frame.radii[i]*self.scale*frame.scales[i]
            color = (1-frame.activation[i])*self.warm + frame.activation[i]*self.accent
            intensity = frame.brightness[i]
            rgb = lambda factor: tuple(np.clip(color*factor, 0, 255).astype(int))
            if intensity > 1.04:
                glow = min(1, intensity-1)
                draw.ellipse((x-2.2*radius, y-2.2*radius, x+2.2*radius, y+2.2*radius), fill=(*rgb(1), int(35*glow)))
                draw.ellipse((x-1.5*radius, y-1.5*radius, x+1.5*radius, y+1.5*radius), fill=(*rgb(1), int(65*glow)))
            if trail is not None and frame.activation[i] > .8:
                tx, ty = trail.positions[i]*self.scale
                draw.line((tx, ty, x, y), fill=(*rgb(1), 75), width=max(1, round(radius*.65)))
            draw.ellipse((x-radius, y-radius, x+radius, y+radius), fill=(*rgb(intensity*.48), 255))
            r = radius*.85
            draw.ellipse((x-r, y-r-.06*radius, x+r, y+r-.06*radius), fill=(*rgb(intensity*.94), 255))
            hx, hy, hr = x-.29*radius, y-.34*radius, radius*.25
            highlight = tuple(np.clip(color*intensity*.65 + 95*min(intensity, 1), 0, 255).astype(int))
            draw.ellipse((hx-hr, hy-hr, hx+hr, hy+hr), fill=(*highlight, 230))
