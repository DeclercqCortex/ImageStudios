"""Batch planning: turn loaded sources + a Recipe into concrete output jobs.

A job renders a list of *units*. A unit is either a single `Frame` or a `Panel`
(a grid of frames / nested panels) - e.g. channels side by side plus a merge.
"""
from __future__ import annotations

import itertools
import os
import re
from dataclasses import dataclass, field

from .annotate import Annot
from .render import Display
from .sources import ordered_axes

OUTPUTS = {
    "images": "Image files (one per frame / panel)",
    "animation": "Animation / video",
    "pdf": "PDF document",
    "html": "Interactive HTML viewer",
}
FORMATS = {
    "images": {"png": "PNG", "jpg": "JPEG", "tif": "TIFF (8-bit rendered)",
               "tif-raw": "TIFF (raw data, original bit depth)", "webp": "WebP", "bmp": "BMP"},
    "animation": {"gif": "GIF", "mp4": "MP4 (H.264)", "webp": "Animated WebP"},
    "pdf": {"pdf": "PDF"},
    "html": {"html": "HTML"},
}
MODES = {
    "iterate": "Iterate",
    "fixed": "Fixed index",
    "max": "Max projection",
    "animate": "Animate",
    "composite": "Merge channels",
    "panel": "In panel",
    "viewer": "In viewer",
}
MODE_TIPS = {
    "iterate": "One output per index in the range",
    "fixed": "Use a single index (e.g. 'current' = slider position, or a number)",
    "max": "Maximum-intensity projection over the range",
    "animate": "Frames of the GIF / MP4 run along this axis",
    "composite": "Overlay visible channels with their colours",
    "panel": "This axis is laid out in the panel (see Panel settings); the range picks which images",
    "viewer": "The viewer gets a slider for this axis; the range picks which frames are included",
}
PANEL_FILL = {"row": "Images per row", "col": "Images per column"}


@dataclass
class AxisRule:
    mode: str = "iterate"
    sel: str = "all"     # 1-based: "all", "current", "1-10", "1-20:2, 25"


HTML_TOOLS = {   # key: (label, tooltip)
    "playback": ("Play / pause controls", "Play button, frame rate and loop for time, Z or positions"),
    "gallery": ("Position gallery", "Thumbnail strip of every multipoint position"),
    "lut": ("LUT editor", "Histogram per channel with draggable min/max, gamma, colour and colour maps"),
    "projections": ("Projections", "Mean / max / min projection over time or Z"),
    "ortho": ("Orthogonal views", "XZ / YZ side views for Z stacks"),
    "zoom": ("Zoom & pan", "Mouse-wheel zoom and drag-to-pan, synced across tiles, with a minimap"),
    "inspector": ("Pixel inspector", "Hover to read x/y and raw channel values"),
    "ruler": ("Ruler", "Measure distances in \u00b5m"),
    "snapshot": ("Snapshot button", "Save the current view as a PNG"),
    "metadata": ("Metadata button", "Window listing the acquisition metadata"),
    "overlay_toggles": ("Overlay switches", "Let viewers turn the scale bar, time stamp etc. on and off"),
}
HTML_PRESETS = {
    "explorer": ("Full explorer", {k: True for k in HTML_TOOLS}),
    "player": ("Movie player", {**{k: False for k in HTML_TOOLS}, "playback": True, "gallery": True, "zoom": True,
                                "snapshot": True, "metadata": True}),
    "figure": ("Interactive figure", {**{k: False for k in HTML_TOOLS}, "zoom": True, "inspector": True,
                                      "ruler": True, "snapshot": True}),
    "custom": ("Custom", None),
}


@dataclass
class HtmlOpts:
    preset: str = "explorer"
    tools: dict = field(default_factory=lambda: {k: True for k in HTML_TOOLS})
    autoplay: bool = False
    theme: str = "dark"              # dark | light
    title: str = ""                  # empty = file name
    caption: str = ""
    start: str = "first"             # first | current (slider position in ImageStudios)
    auto_frame: bool = False         # viewer re-stretches contrast on every frame
    lut_view: str = "selected"       # selected: histograms follow the clicked tile | beside: one per tile
    # tiles per page for each axis when it is shown as a panel in the page: [rows, cols], 0 = auto (one page)
    grids: dict = field(default_factory=lambda: {"M": [0, 0], "T": [0, 0], "Z": [0, 0]})
    overlays: dict = field(default_factory=lambda: {"scalebar": True, "time": True, "z": True, "names": True,
                                                    "position": True})


@dataclass
class Recipe:
    output: str = "images"
    fmt: str = "png"
    rules: dict = field(default_factory=dict)
    template: str = ""          # empty -> automatic
    one_based: bool = True
    fps: float = 10.0
    loop: bool = True
    quality: int = 90
    scale_pct: float = 100.0
    background: str = "white"   # white | black | transparent
    combine: bool = False
    combined_name: str = "ImageStudios_combined"
    out_dir: str = ""
    beside_source: bool = False
    subfolders: bool = False
    display: Display = field(default_factory=Display)
    annot: Annot = field(default_factory=Annot)
    scale_mode: str = "auto"     # auto | manual (manual uses scale_pct)
    # panel layout
    panel_axis: str = ""         # "" = no panel, an axis letter, or "F" = files side by side
    panel_fill: str = "row"      # row: panel_count images per row | col: per column
    panel_count: int = 0         # 0 = automatic (near-square grid)
    panel_gap: int = 6           # pixels between tiles (and around the panel)
    panel_bg: str = "white"      # white | black
    panel_merge: bool = True     # add a merged tile when channels are laid out in the panel
    html_budget_mb: float = 400  # HTML viewer: raw data above this is binned 2x2, 4x4 ...
    html: HtmlOpts = field(default_factory=HtmlOpts)

    def rule(self, axis: str) -> AxisRule:
        if axis not in self.rules:
            self.rules[axis] = default_rule(axis, self.output)
        return self.rules[axis]


def default_rule(axis: str, output: str) -> AxisRule:
    if axis == "C":
        return AxisRule("composite")
    return AxisRule("iterate")


def parse_selection(sel: str, n: int, current: int = 0) -> list:
    s = (sel or "all").strip().lower()
    cur = [min(max(current, 0), n - 1)]
    if s in ("", "all", "*"):
        return list(range(n))
    if s in ("current", "cur", "."):
        return cur
    out = []
    for part in re.split(r"[,;\s]+", s):
        if not part:
            continue
        try:
            step = 1
            if ":" in part:
                part, st = part.split(":", 1)
                step = max(1, int(st or 1))
            if part == "last":
                out.append(n)
            elif part in ("current", "cur"):
                out.append(cur[0] + 1)
            elif "-" in part:
                a, b = part.split("-", 1)
                a = n if a == "last" else (int(a) if a else 1)
                b = n if b in ("", "last") else int(b)
                out.extend(range(a, b - 1, -step) if b < a else range(a, b + 1, step))
            else:
                out.append(int(part))
        except ValueError:
            continue
    res = [i - 1 for i in out if 1 <= i <= n]
    return res or cur


@dataclass(eq=False)
class Frame:
    source: object
    idx: dict
    proj: dict
    channel: int | None


@dataclass(eq=False)
class Panel:
    cells: list                   # rows of Frame | Panel | None
    tiled: set = field(default_factory=set)   # axes laid out across the panel ("F" = files)


@dataclass
class Job:
    out_path: str
    kind: str          # image | animation | pdf
    frames: list       # units (Frame | Panel)
    label: str = ""


def leaves(unit) -> list:
    if isinstance(unit, Frame):
        return [unit]
    out = []
    for row in unit.cells:
        for c in row:
            if c is not None:
                out.extend(leaves(c))
    return out


def tiled_axes(unit) -> set:
    if isinstance(unit, Frame):
        return set()
    s = set(unit.tiled)
    for row in unit.cells:
        for c in row:
            if c is not None:
                s |= tiled_axes(c)
    return s


def grid_shape(unit) -> tuple:
    if isinstance(unit, Frame):
        return 1, 1
    return len(unit.cells), max((len(r) for r in unit.cells), default=0)


class _Fmt(dict):
    def __missing__(self, key):
        return ""


_BAD = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')


def safe(s: str) -> str:
    return _BAD.sub("_", str(s)).strip(" .") or "untitled"


def _tokens(src, idx: dict, iter_axes: list, one_based: bool) -> dict:
    t = _Fmt(name=src.name)
    auto = []
    for a in ordered_axes(src.axes):
        n = src.axes[a]
        w = len(str(n))
        v = idx.get(a, 0) + (1 if one_based else 0)
        t[a.lower()] = f"{v:0{w}d}"
        t[a] = t[a.lower()]
        if a in iter_axes:
            piece = f"{a}{v:0{w}d}"
            if a == "C" and src.channels:
                piece += "-" + safe(src.channel_name(idx.get("C", 0))).replace(" ", "")
            auto.append(piece)
    if "C" in idx and src.channels:
        t["cname"] = safe(src.channel_name(idx["C"]))
    if "M" in src.axes:
        t["pos"] = safe(src.position_name(idx.get("M", 0)))
    t["auto"] = ("_" + "_".join(auto)) if auto else ""
    return t


def _render_name(template: str, tok: dict) -> str:
    tpl = template.strip() or "{name}{auto}"
    try:
        out = tpl.format_map(tok)
    except (ValueError, IndexError, KeyError, AttributeError):
        out = "{name}{auto}".format_map(tok)
    return safe(out)


def _out_dir(src, recipe: Recipe) -> str:
    base = os.path.dirname(src.path) if (recipe.beside_source or not recipe.out_dir) else recipe.out_dir
    if recipe.subfolders:
        base = os.path.join(base, safe(src.name))
    return base


def _ext(recipe: Recipe) -> str:
    return {"tif-raw": "tif"}.get(recipe.fmt, recipe.fmt)


# ---------------------------------------------------------------------------
def arrange(items: list, fill: str, count: int) -> list:
    """Lay a flat list of tiles out as rows (None pads the last row/column)."""
    import math

    n = len(items)
    if n == 0:
        return [[]]
    per = count if count and count > 0 else (n if n <= 4 else max(1, math.ceil(math.sqrt(n))))
    if fill == "col":
        rows_n = min(per, n)
        cols_n = math.ceil(n / rows_n)
        grid = [[None] * cols_n for _ in range(rows_n)]
        for k, it in enumerate(items):
            grid[k % rows_n][k // rows_n] = it
        return grid
    cols_n = min(per, n)
    rows = [items[i:i + cols_n] for i in range(0, n, cols_n)]
    rows[-1] = rows[-1] + [None] * (cols_n - len(rows[-1]))
    return rows


@dataclass
class _Analysis:
    fixed: dict
    proj: dict
    iter_axes: list          # [(axis, sel)]
    anim: tuple | None       # (axis, sel)
    tile: tuple | None       # (axis, sel) laid out in the panel
    c_explicit: bool         # channel index chosen explicitly (not a composite)


def analyse(src, recipe: Recipe, warnings: list | None = None) -> _Analysis:
    fixed, proj, iter_axes = {}, {}, []
    anim = tile = None
    c_explicit = False
    for a in ordered_axes(src.axes):
        r = recipe.rule(a)
        n = src.axes[a]
        sel = parse_selection(r.sel, n, src.current.get(a, 0))
        if a == recipe.panel_axis:
            tile = (a, sel)
            if a == "C":
                c_explicit = True
            continue
        mode = r.mode
        if a == "C" and mode == "max":
            mode = "composite"
        if mode in ("composite", "panel") and a != "C":
            mode = "iterate"
        if mode == "panel":
            mode = "composite"
        if mode == "animate" and recipe.output != "animation":
            mode = "iterate"
        if a == "C" and mode != "composite":
            c_explicit = True
        if mode == "fixed":
            fixed[a] = sel[0]
        elif mode == "max":
            proj[a] = sel
        elif mode == "animate":
            if anim is None:
                anim = (a, sel)
            else:
                iter_axes.append((a, sel))
        elif mode == "composite":
            pass
        else:
            iter_axes.append((a, sel))

    if recipe.output == "animation" and anim is None:
        for a in ("T", "Z", "P", "I", "M"):
            if a in src.axes and a not in fixed and a not in proj and a != recipe.panel_axis:
                iter_axes = [(x, s) for x, s in iter_axes if x != a]
                anim = (a, parse_selection(recipe.rule(a).sel, src.axes[a], 0))
                break
    return _Analysis(fixed, proj, iter_axes, anim, tile, c_explicit)


def make_unit(src, an: _Analysis, idx: dict, recipe: Recipe):
    def frame(i):
        i = dict(i)
        ch = i.get("C") if (an.c_explicit and "C" in i) else None
        if ch is None:
            i.pop("C", None)
        return Frame(src, i, an.proj, ch)

    if not an.tile:
        return frame(idx)
    ax, sel = an.tile
    tiles = []
    for v in sel:
        i = dict(idx)
        i[ax] = v
        tiles.append(frame(i))
    if ax == "C" and recipe.panel_merge and len(src.channels) > 1:
        i = dict(idx)
        i.pop("C", None)
        tiles.append(Frame(src, i, an.proj, None))
    return Panel(arrange(tiles, recipe.panel_fill, recipe.panel_count), {ax})


def preview_unit(src, recipe: Recipe):
    """The unit an export would produce at the file's current slider position."""
    an = analyse(src, recipe)
    idx = dict(an.fixed)
    for a, _sel in an.iter_axes:
        idx[a] = src.current.get(a, 0)
    if an.anim:
        idx[an.anim[0]] = src.current.get(an.anim[0], 0)
    if "C" in src.axes and an.c_explicit and "C" not in idx:
        idx["C"] = src.current.get("C", 0)
    return make_unit(src, an, idx, recipe)


@dataclass
class _Out:
    src: object
    tok: dict
    units: list
    label: str


def _source_outs(src, recipe: Recipe):
    an = analyse(src, recipe)
    iter_names = [a for a, _ in an.iter_axes]
    combos = list(itertools.product(*(s for _, s in an.iter_axes))) or [()]
    outs = []
    panel = bool(an.tile)
    for combo in combos:
        idx = dict(an.fixed)
        idx.update(zip(iter_names, combo))
        tok = _tokens(src, idx, iter_names, recipe.one_based)
        if panel:
            tok["auto"] += "_panel"
        if recipe.output == "animation":
            units = []
            if an.anim:
                a, sel = an.anim
                for v in sel:
                    i = dict(idx)
                    i[a] = v
                    units.append(make_unit(src, an, i, recipe))
                tok["auto"] += f"_{a}-anim"
            else:
                units.append(make_unit(src, an, idx, recipe))
            outs.append(_Out(src, tok, units, src.name))
        else:
            outs.append(_Out(src, tok, [make_unit(src, an, idx, recipe)], src.name))
    if recipe.output == "pdf":
        units = [u for o in outs for u in o.units]
        tok = _tokens(src, {}, [], recipe.one_based)
        outs = [_Out(src, tok, units, src.name)]
    return outs


def build_plan(sources, recipe: Recipe):
    """Return (jobs, warnings)."""
    jobs: list = []
    warnings: list = []
    used = set()

    def unique(path):
        base, ext = os.path.splitext(path)
        cand, k = path, 2
        while cand.lower() in used:
            cand = f"{base}_{k}{ext}"
            k += 1
        used.add(cand.lower())
        return cand

    if recipe.output == "html":
        return _html_plan(sources, recipe, unique)
    kind = {"images": "image", "animation": "animation", "pdf": "pdf"}[recipe.output]
    ext = "pdf" if recipe.output == "pdf" else _ext(recipe)
    per_src = [(s, _source_outs(s, recipe)) for s in sources]

    def combined_dir():
        first = sources[0]
        if recipe.beside_source or not recipe.out_dir:
            return os.path.dirname(first.path)
        return recipe.out_dir

    # --- files laid out side by side in a panel ---------------------------
    if recipe.panel_axis == "F" and len(sources) > 1:
        n_out = min(len(o) for _, o in per_src)
        if any(len(o) != n_out for _, o in per_src):
            warnings.append("Files produce different numbers of outputs; the file panel uses the first "
                            f"{n_out} of each.")
        for k in range(n_out):
            n_units = min(len(o[k].units) for _, o in per_src)
            units = []
            for j in range(n_units):
                cells = [o[k].units[j] for _, o in per_src]
                units.append(Panel(arrange(cells, recipe.panel_fill, recipe.panel_count), {"F"}))
            tok = _Fmt(per_src[0][1][k].tok)
            tok["name"] = safe(recipe.combined_name or "panel")
            path = unique(os.path.join(combined_dir(), _render_name(recipe.template, tok) + "." + ext))
            jobs.append(Job(path, kind, units, f"{len(sources)} files"))
        return _finish(jobs, warnings, recipe)

    # --- everything chained into one PDF / animation ----------------------
    if recipe.combine and recipe.output in ("animation", "pdf"):
        units = [u for _, outs in per_src for o in outs for u in o.units]
        if units:
            path = unique(os.path.join(combined_dir(), safe(recipe.combined_name or "combined") + "." + ext))
            jobs.append(Job(path, kind, units, f"{len(sources)} files"))
        return _finish(jobs, warnings, recipe)

    skipped = []
    for src, outs in per_src:
        for o in outs:
            if recipe.output == "animation" and len(o.units) < 2:
                skipped.append(src.name)
                continue
            path = unique(os.path.join(_out_dir(src, recipe), _render_name(recipe.template, o.tok) + "." + ext))
            jobs.append(Job(path, kind, o.units, o.label))
    if skipped:
        names = ", ".join(dict.fromkeys(skipped[:5])) + (f" and {len(skipped) - 5} more" if len(skipped) > 5 else "")
        warnings.append(f"{len(skipped)} single-frame output(s) skipped ({names}): nothing to animate. "
                        "Tick 'Combine all files' to chain separate images into one animation.")
    return _finish(jobs, warnings, recipe)


def _html_plan(sources, recipe, unique):
    from .html_export import layout_for

    jobs, warnings = [], []
    for src in sources:
        L = layout_for(src, recipe)
        tok = _tokens(src, {}, [], recipe.one_based)
        path = unique(os.path.join(_out_dir(src, recipe), _render_name(recipe.template, tok) + ".html"))
        frames = [Frame(src, {"M": m}, {}, None) for m in L["sel"]["M"]]
        mb = L["bytes"] / 1e6
        jobs.append(Job(path, "html", frames, f"{src.name}  (~{mb:.0f} MB raw)"))
        if L["bin"] > 1:
            warnings.append(f"{src.name}: {L['raw_bytes'] / 1e6:.0f} MB of raw data is over the "
                            f"{recipe.html_budget_mb:g} MB budget, so the viewer gets it binned "
                            f"{L['bin']}×{L['bin']}. Narrow the axis ranges or raise the budget to avoid this.")
        elif mb > 250:
            warnings.append(f"{src.name}: the viewer will hold ~{mb:.0f} MB of raw data; the page may be slow to open.")
    return jobs, warnings


def _finish(jobs, warnings, recipe):
    a = recipe.annot
    srcs = {id(f.source): f.source for j in jobs for u in j.frames[:1] for f in leaves(u)}
    if a.scalebar:
        missing = [s.name for s in srcs.values() if not s.pixel_size]
        if missing:
            warnings.append("Scale bar: no pixel size known for " + ", ".join(missing[:4]) +
                            (" …" if len(missing) > 4 else "") + " (enter it under the preview).")
    if a.timestamp:
        missing = [s.name for s in srcs.values() if not s.has_times()]
        if missing:
            warnings.append("Time stamp: no timing information for " + ", ".join(missing[:4]) +
                            (" …" if len(missing) > 4 else "") + " (enter a frame interval under the preview).")
    if recipe.fmt == "tif-raw" and any(isinstance(u, Panel) for j in jobs for u in j.frames[:1]):
        warnings.append("Raw TIFF can't hold panels; panels are written as rendered 8-bit TIFFs.")
    if recipe.fmt == "tif-raw" and a.any():
        warnings.append("Raw TIFF keeps original pixel values, so annotations are not burned in.")
    return jobs, warnings
