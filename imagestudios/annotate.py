"""Burn-in annotations for microscopy presentation: scale bar, time stamp, Z depth,
channel names, position name, file name and free text."""
from __future__ import annotations

import math
from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFont

CORNERS = {"tl": "Top left", "tr": "Top right", "bl": "Bottom left", "br": "Bottom right"}
TIME_FORMATS = {
    "auto": "Auto (s / min / h)",
    "hms": "hh:mm:ss",
    "ms": "mm:ss",
    "s": "seconds",
    "min": "minutes",
    "h": "hours",
    "d": "days",
}

# Which axis each annotation belongs to (used to decide where it goes in panels).
ITEM_AXIS = {"timestamp": "T", "zpos": "Z", "channels": "C", "position": "M", "filename": "F",
             "text": None, "scalebar": "SB"}


@dataclass
class Annot:
    timestamp: bool = False
    ts_format: str = "auto"
    ts_zero: str = "position"      # position | experiment
    ts_offset_min: float = 0.0     # subtract this many minutes (e.g. treatment at t=0)
    ts_prefix: str = ""
    ts_pos: str = "tl"
    zpos: bool = False
    z_pos: str = "tl"
    channels: bool = False
    ch_pos: str = "tr"
    position: bool = False
    pos_pos: str = "bl"
    filename: bool = False
    name_pos: str = "bl"
    text: str = ""
    text_pos: str = "bl"
    scalebar: bool = False
    sb_um: float = 0.0             # 0 = automatic nice length
    sb_pos: str = "br"
    sb_label: bool = True
    sb_thick_pct: float = 1.2
    sb_every_tile: bool = False
    font_pct: float = 4.5          # text height as % of the shorter image side
    color: str = "white"           # white | black | yellow
    outline: bool = True

    def enabled_items(self) -> list:
        items = [k for k in ("timestamp", "zpos", "channels", "position", "filename", "scalebar") if getattr(self, k)]
        if self.text.strip():
            items.append("text")
        return items

    def any(self) -> bool:
        return bool(self.enabled_items())


_FONT_CACHE: dict = {}


def get_font(px: int):
    px = max(8, int(px))
    if px in _FONT_CACHE:
        return _FONT_CACHE[px]
    font = None
    for name in ("segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf", "Arial Bold.ttf", "Helvetica.ttc"):
        try:
            font = ImageFont.truetype(name, px)
            break
        except OSError:
            continue
    if font is None:
        try:
            font = ImageFont.load_default(size=px)
        except TypeError:
            font = ImageFont.load_default()
    _FONT_CACHE[px] = font
    return font


def format_time(sec: float, fmt: str, span: float) -> str:
    neg = sec < 0
    a = abs(sec)
    sign = "-" if neg else ""
    if fmt == "auto":
        fmt = "s" if span < 120 else ("min" if span < 3 * 3600 else ("h" if span < 4 * 86400 else "d"))
        if fmt == "h":
            fmt = "hm"
    if fmt == "hms":
        h, r = divmod(int(round(a)), 3600)
        m, s = divmod(r, 60)
        return f"{sign}{h:02d}:{m:02d}:{s:02d}"
    if fmt == "hm":
        h, r = divmod(int(round(a / 60.0)), 60)
        return f"{sign}{h:d} h {r:02d} min"
    if fmt == "ms":
        m, s = divmod(int(round(a)), 60)
        return f"{sign}{m:02d}:{s:02d}"
    if fmt == "s":
        return f"{sign}{a:.1f} s" if a < 100 else f"{sign}{a:.0f} s"
    if fmt == "min":
        v = a / 60.0
        return f"{sign}{v:.1f} min" if v < 100 else f"{sign}{v:.0f} min"
    if fmt == "h":
        return f"{sign}{a / 3600.0:.2f} h"
    if fmt == "d":
        return f"{sign}{a / 86400.0:.2f} d"
    return f"{sign}{a:.1f} s"


def nice_length(target_um: float) -> float:
    if target_um <= 0:
        return 1.0
    e = math.floor(math.log10(target_um))
    best = None
    for m in (1, 2, 5, 10):
        v = m * 10 ** e
        if v <= target_um * 1.25:
            best = v
    return best or 10 ** e


def fmt_um(v: float) -> str:
    if v >= 1000:
        return f"{v / 1000:g} mm"
    if v < 1:
        return f"{v * 1000:g} nm"
    return f"{v:g} µm"


def _palette(annot: Annot):
    fg = {"white": (255, 255, 255), "black": (0, 0, 0), "yellow": (255, 230, 60)}.get(annot.color, (255, 255, 255))
    stroke = (0, 0, 0) if sum(fg) > 380 else (255, 255, 255)
    return fg, stroke


def item_lines(item: str, frame, annot: Annot):
    """Return list of lines; each line is a list of (text, colour|None) segments."""
    src, idx = frame.source, frame.idx
    if item == "timestamp":
        if "T" not in src.axes:
            return []
        t = src.time_s(idx, annot.ts_zero)
        if t is None:
            return []
        t -= annot.ts_offset_min * 60.0
        span = max(src.time_span(), abs(t))
        return [[(annot.ts_prefix + format_time(t, annot.ts_format, span), None)]]
    if item == "zpos":
        if "Z" not in src.axes:
            return []
        z = src.z_um(idx)
        if z is None:
            return [[(f"Z {idx.get('Z', 0) + 1}/{src.axes['Z']}", None)]]
        return [[(f"z = {z:.1f} µm" if abs(z) < 100 else f"z = {z:.0f} µm", None)]]
    if item == "channels":
        if not src.channels:
            return []
        if frame.channel is not None:
            ch = src.channels[frame.channel]
            return [[(ch.name, tuple(ch.color))]]
        return [[(c.name, tuple(c.color))] for c in src.channels if c.visible]
    if item == "position":
        if "M" not in src.axes:
            return []
        return [[(src.position_name(idx.get("M", 0)), None)]]
    if item == "filename":
        return [[(src.name, None)]]
    if item == "text":
        tok = {"name": src.name, "pos": src.position_name(idx.get("M", 0)) if "M" in src.axes else "",
               "cname": src.channel_name(frame.channel) if frame.channel is not None else ""}
        t = src.time_s(idx, annot.ts_zero)
        tok["time"] = format_time(t - annot.ts_offset_min * 60, annot.ts_format, src.time_span()) if t is not None else ""
        try:
            txt = annot.text.format_map(type("D", (dict,), {"__missing__": lambda s, k: ""})(tok))
        except (ValueError, IndexError):
            txt = annot.text
        return [[(line, None)] for line in txt.split("\\n")]
    return []


def draw(im: Image.Image, frame, annot: Annot, items, px_scale: float = 1.0) -> Image.Image:
    """Draw annotation `items` on im. px_scale = output pixels per source pixel."""
    if not items:
        return im
    if im.mode not in ("RGB", "RGBA"):
        im = im.convert("RGB")
    w, h = im.size
    d = ImageDraw.Draw(im)
    fpx = max(9, round(annot.font_pct / 100.0 * min(w, h)))
    font = get_font(fpx)
    fg, stroke_col = _palette(annot)
    sw = max(1, fpx // 12) if annot.outline else 0
    margin = max(3, round(fpx * 0.55))
    gap = max(1, round(fpx * 0.18))

    stacks = {c: [] for c in CORNERS}
    pos_of = {"timestamp": annot.ts_pos, "zpos": annot.z_pos, "channels": annot.ch_pos,
              "position": annot.pos_pos, "filename": annot.name_pos, "text": annot.text_pos}
    order = ["timestamp", "zpos", "position", "filename", "text", "channels"]
    for it in order:
        if it in items:
            for line in item_lines(it, frame, annot):
                stacks[pos_of[it]].append(("text", line))

    if "scalebar" in items and frame.source.pixel_size:
        um_per_px = frame.source.pixel_size / max(px_scale, 1e-9)
        length = annot.sb_um if annot.sb_um > 0 else nice_length(0.2 * w * um_per_px)
        bar_px = max(2, round(length / um_per_px))
        thick = max(2, round(annot.sb_thick_pct / 100.0 * min(w, h)))
        stacks[annot.sb_pos].insert(0, ("bar", (bar_px, thick, fmt_um(length) if annot.sb_label else "")))

    def text_size(txt):
        if not txt:
            return 0, 0
        b = d.textbbox((0, 0), txt, font=font, stroke_width=sw)
        return b[2] - b[0], b[3] - b[1]

    line_h = text_size("Agµ")[1]

    for corner, entries in stacks.items():
        if not entries:
            continue
        right = corner[1] == "r"
        bottom = corner[0] == "b"
        seq = entries if not bottom else entries  # bars are first: closest to the edge
        y = h - margin if bottom else margin
        for kind, payload in (seq if not bottom else seq):
            if kind == "bar":
                bar_px, thick, label = payload
                lw, lh = text_size(label)
                block_w = max(bar_px, lw)
                x0 = (w - margin - block_w) if right else margin
                bx = x0 + (block_w - bar_px) // 2
                if bottom:
                    by = y - thick
                    if sw:
                        d.rectangle([bx - sw, by - sw, bx + bar_px + sw - 1, by + thick + sw - 1], fill=stroke_col)
                    d.rectangle([bx, by, bx + bar_px - 1, by + thick - 1], fill=fg)
                    y = by - gap
                    if label:
                        tx = x0 + (block_w - lw) // 2
                        d.text((tx, y - line_h), label, font=font, fill=fg, stroke_width=sw, stroke_fill=stroke_col,
                               anchor="la")
                        y -= line_h + gap
                else:
                    if label:
                        tx = x0 + (block_w - lw) // 2
                        d.text((tx, y), label, font=font, fill=fg, stroke_width=sw, stroke_fill=stroke_col)
                        y += line_h + gap
                    by = y
                    if sw:
                        d.rectangle([bx - sw, by - sw, bx + bar_px + sw - 1, by + thick + sw - 1], fill=stroke_col)
                    d.rectangle([bx, by, bx + bar_px - 1, by + thick - 1], fill=fg)
                    y = by + thick + gap
                continue
            segs = payload
            total_w = sum(text_size(t)[0] for t, _ in segs) + gap * (len(segs) - 1)
            x = (w - margin - total_w) if right else margin
            ty = (y - line_h) if bottom else y
            for t, col in segs:
                c = tuple(col) if col else fg
                sc = stroke_col if col is None else ((0, 0, 0) if sum(c) > 200 else (255, 255, 255))
                d.text((x, ty), t, font=font, fill=c, stroke_width=sw, stroke_fill=sc)
                x += text_size(t)[0] + gap
            y = (y - line_h - gap) if bottom else (y + line_h + gap)
    return im
