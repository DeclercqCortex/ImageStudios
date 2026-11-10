"""Interactive HTML viewer output: one self-contained .html per file.

Raw intensities (8/16-bit, or float32) are zlib-compressed per position and
embedded as base64; the page decodes them in the browser, so LUTs, projections
and the pixel inspector work on the original values.
"""
from __future__ import annotations

import base64
import html
import io
import json
import os
import zlib

import numpy as np
from PIL import Image

from .html_template import HEAD, TAIL
from .plan import parse_selection
from .render import Display, render, stack_limits

STACK_T = ("T", "P", "I")     # first of these present becomes the viewer's time-like axis


def _sel(src, recipe, axis):
    if axis not in src.axes:
        return [0]
    return parse_selection(recipe.rule(axis).sel, src.axes[axis], src.current.get(axis, 0))


def layout_for(src, recipe, per_position_mb: float | None = None) -> dict:
    """Which original indices go into the viewer, the data type and the binning."""
    t_ax = next((a for a in STACK_T if a in src.axes), None)
    sel = {
        "M": _sel(src, recipe, "M"),
        "T": _sel(src, recipe, t_ax) if t_ax else [0],
        "Z": _sel(src, recipe, "Z"),
    }
    if src.rgb:
        chans = [0, 1, 2]
    elif "C" in src.axes:
        chans = _sel(src, recipe, "C")
    else:
        chans = [None]
    dt = np.dtype(src.dtype)
    if src.rgb or dt == np.uint8:
        kind, nbytes = "u8", 1
    elif dt == np.uint16:
        kind, nbytes = "u16", 2
    else:
        kind, nbytes = "f32", 4
    total = len(sel["M"]) * len(sel["T"]) * len(sel["Z"]) * len(chans) * src.width * src.height * nbytes
    budget = max(16, float(recipe.html_budget_mb)) * 1024 * 1024
    if per_position_mb:   # live preview: judge a single position against a small budget
        total = total / max(1, len(sel["M"]))
        budget = min(budget, per_position_mb * 1024 * 1024)
    b = 1
    while total / (b * b) > budget and min(src.width, src.height) // (b * 2) >= 16:
        b *= 2
    return {"t_axis": t_ax, "sel": sel, "chans": chans, "kind": kind, "nbytes": nbytes, "bin": b,
            "raw_bytes": total, "bytes": total / (b * b)}


def _bin(a: np.ndarray, b: int) -> np.ndarray:
    if b <= 1:
        return a
    h, w = (a.shape[0] // b) * b, (a.shape[1] // b) * b
    a = a[:h, :w].astype(np.float32)
    return a.reshape(h // b, b, w // b, b).mean(axis=(1, 3))


def _thumb(src, idx, disp) -> str:
    try:
        arr = render(src, idx, None, None, disp)
        im = Image.fromarray(arr).convert("RGB")
        if max(im.size) < 160:
            k = max(1, 160 // max(im.size))
            im = im.resize((im.width * k, im.height * k), Image.NEAREST)
        im.thumbnail((160, 160), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, "PNG", optimize=True)
        return base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception:
        return ""


def _panel_axis(recipe, axes, n_chans):
    """The image-export Panel settings decide the page's fixed tile layout."""
    a = recipe.panel_axis
    if a == "C":
        return "C" if n_chans > 1 else ""
    if a == "P" or a == "I":
        a = "T"            # pages / frames sit on the viewer's time-like axis
    return a if a in axes else ""


def write_html(job, recipe, tick=lambda: None, cancelled=lambda: False, preview: dict | None = None):
    """Write the viewer page. preview = {"cache": dict} makes a quick page holding only the
    position at the current slider (data and thumbnails are cached between calls)."""
    from .export import Cancelled

    src = job.frames[0].source
    L = layout_for(src, recipe, per_position_mb=48 if preview is not None else None)
    sel, chans, kind, b = L["sel"], L["chans"], L["kind"], L["bin"]
    t_ax = L["t_axis"]
    disp = recipe.display if isinstance(recipe.display, Display) else Display()
    W, H = src.width // b, src.height // b

    # ---- channel descriptions + display ranges ----
    channels = []
    for k, c in enumerate(chans):
        if src.rgb:
            name, color, lo, hi = ("Red", "Green", "Blue")[k], ("#ff0000", "#00ff00", "#0000ff")[k], 0.0, 255.0
        else:
            chobj = src.channels[c] if (c is not None and c < len(src.channels)) else None
            name = chobj.name if chobj else src.name
            col = tuple(chobj.color) if chobj else (255, 255, 255)
            color = "#%02x%02x%02x" % col
            if chobj and chobj.limits:
                lo, hi = chobj.limits
            else:
                lo, hi = stack_limits(src, c, disp)
        channels.append({"name": name, "color": color, "lo": float(lo), "hi": float(hi),
                         "preset": "grey" if (len(chans) == 1 and not src.rgb) else "color",
                         "dmin": None, "dmax": None})

    base_fixed = {a: src.current.get(a, 0) for a in src.axes if a not in ("M", "Z", "C", t_ax)}

    block = {"m": None, "arr": None, "dims": None}

    def from_block(m, t, z, c):
        if not hasattr(src, "position_block") or base_fixed:
            return None
        if block["m"] != m:
            block["arr"], block["dims"] = src.position_block(m)
            block["m"] = m
        if block["arr"] is None:
            return None
        key = []
        for d in block["dims"]:
            if d == "T":
                key.append(t)
            elif d == "Z":
                key.append(z)
            elif d == "C":
                key.append(c if c is not None else 0)
            else:
                key.append(slice(None))
        p = block["arr"][tuple(key)]
        if src.rgb and p.ndim == 3:
            p = p[..., c]
        return p

    def plane(m, t, z, c):
        p = from_block(m, t, z, c)
        if p is not None:
            p = _bin(np.asarray(p), b)
            if kind == "u16" and p.dtype == np.uint16 or kind == "u8" and p.dtype == np.uint8:
                return np.ascontiguousarray(p)
            if kind == "u8":
                return np.ascontiguousarray(np.clip(p, 0, 255).astype(np.uint8))
            if kind == "u16":
                return np.ascontiguousarray(np.clip(np.rint(p), 0, 65535).astype(np.uint16))
            return np.ascontiguousarray(p.astype(np.float32))
        idx = dict(base_fixed)
        if "M" in src.axes:
            idx["M"] = m
        if t_ax:
            idx[t_ax] = t
        if "Z" in src.axes:
            idx["Z"] = z
        if src.rgb:
            p = src.plane(idx)
            p = p[..., c] if p.ndim == 3 else p
        else:
            if c is not None:
                idx["C"] = c
            p = src.plane(idx)
            if p.ndim == 3:
                p = p.mean(axis=-1)
        p = _bin(p, b)
        if kind == "u8":
            return np.ascontiguousarray(np.clip(p, 0, 255).astype(np.uint8)) if p.dtype != np.uint8 else np.ascontiguousarray(p)
        if kind == "u16":
            return np.ascontiguousarray(np.clip(np.rint(p), 0, 65535).astype(np.uint16)) if p.dtype != np.uint16 else np.ascontiguousarray(p)
        return np.ascontiguousarray(p.astype(np.float32))

    # ---- times / z / names ----
    zero = recipe.annot.ts_zero
    times = None
    if t_ax == "T" and src.has_times():
        times = []
        for m in sel["M"]:
            row = []
            for t in sel["T"]:
                v = src.time_s({"T": t, "M": m, "Z": sel["Z"][0]}, zero)
                row.append(None if v is None else round(v - recipe.annot.ts_offset_min * 60.0, 4))
            times.append(row)
    zpos = None
    if "Z" in src.axes:
        zpos = []
        for m in sel["M"]:
            vals = [src.z_um({"Z": z, "M": m}) for z in sel["Z"]]
            zpos.append(None if all(v is None for v in vals) else [None if v is None else round(v, 4) for v in vals])
    labels = {"T": {"T": "Time", "P": "Page", "I": "Frame"}.get(t_ax, "Time"), "Z": "Z-slice", "M": "Position"}
    axes = {}
    if len(sel["T"]) > 1:
        axes["T"] = {"n": len(sel["T"]), "label": labels["T"]}
    if len(sel["Z"]) > 1:
        axes["Z"] = {"n": len(sel["Z"]), "label": "Z-slice"}
    if len(sel["M"]) > 1:
        axes["M"] = {"n": len(sel["M"]), "label": "Position",
                     "names": [src.position_name(m) for m in sel["M"]]}
    ho = recipe.html
    overlays = dict(ho.overlays)
    ui = {"playback": True, "gallery": True, "lut": True, "projections": True, "ortho": True, "zoom": True,
          "inspector": True, "ruler": True, "snapshot": True, "metadata": True, "overlay_toggles": True,
          }
    ui.update({k: bool(v) for k, v in ho.tools.items() if k in ui})
    ui["overlayToggles"] = ui.pop("overlay_toggles")
    ui["autoplay"] = bool(ho.autoplay)
    ui["theme"] = ho.theme
    start = {}
    if ho.start == "current" or preview is not None:
        def pos_in(lst, v):
            return lst.index(v) if v in lst else 0
        start = {"m": pos_in(sel["M"], src.current.get("M", 0)),
                 "t": pos_in(sel["T"], src.current.get(t_ax, 0)) if t_ax else 0,
                 "z": pos_in(sel["Z"], src.current.get("Z", 0))}
    info = list(src.info_lines())
    if b > 1:
        info.append(f"Viewer data binned {b}×{b} to fit the {recipe.html_budget_mb:g} MB size budget.")
    sub = [src.describe()]
    if b > 1:
        sub.append(f"binned {b}×{b}")

    # ---- write the page, streaming one position at a time ----
    os.makedirs(os.path.dirname(job.out_path) or ".", exist_ok=True)
    tmp = job.out_path + ".part"
    thumbs = []
    dmin = [np.inf] * len(chans)
    dmax = [-np.inf] * len(chans)
    cache = preview["cache"] if preview is not None else {}
    embed = list(range(len(sel["M"])))
    if preview is not None:
        cur = src.current.get("M", 0)
        embed = [sel["M"].index(cur) if cur in sel["M"] else 0]
    sig = repr([(tuple(c.color), c.visible, c.limits) for c in src.channels]) + repr(
        (disp.contrast, disp.low_pct, disp.high_pct))

    def encode(m):
        key = ("chunk", id(src), m, tuple(sel["T"]), tuple(sel["Z"]), tuple(chans), b, kind)
        if key in cache:
            return cache[key]
        comp = zlib.compressobj(6 if preview is None else 1)
        parts, lo_, hi_ = [], [np.inf] * len(chans), [-np.inf] * len(chans)
        for t in sel["T"]:
            for z in sel["Z"]:
                for k, c in enumerate(chans):
                    p = plane(m, t, z, c)
                    if p.size:
                        lo_[k] = min(lo_[k], float(np.nanmin(p)))
                        hi_[k] = max(hi_[k], float(np.nanmax(p)))
                    parts.append(comp.compress(p.tobytes()))
        parts.append(comp.flush())
        val = (base64.b64encode(b"".join(parts)).decode("ascii"), lo_, hi_)
        if preview is not None:
            for k_old in [k for k in cache if k[0] == "chunk" and k[1] == id(src) and k[2] == m]:
                del cache[k_old]          # keep one variant per position
            cache[key] = val
        return val

    def thumb(m):
        key = ("thumb", id(src), m, sig, tuple(sel["T"]), tuple(sel["Z"]))
        if key not in cache:
            idx = {"M": m}
            if t_ax:
                idx[t_ax] = sel["T"][len(sel["T"]) // 2]
            if "Z" in src.axes:
                idx["Z"] = sel["Z"][len(sel["Z"]) // 2]
            cache[key] = _thumb(src, idx, disp)
        return cache[key]

    with open(tmp + ".chunks", "w", encoding="ascii") as fc:
        for mi, m in enumerate(sel["M"]):
            if cancelled():
                fc.close()
                os.remove(tmp + ".chunks")
                raise Cancelled()
            if mi in embed:
                b64, lo_, hi_ = encode(m)
                for k in range(len(chans)):
                    dmin[k] = min(dmin[k], lo_[k])
                    dmax[k] = max(dmax[k], hi_[k])
                fc.write(f'<script type="application/octet-stream" id="chunk-{mi}">')
                fc.write(b64)
                fc.write("</script>\n")
            if len(sel["M"]) > 1 and ho.tools.get("gallery", True) and not _panel_axis(recipe, axes, len(chans)):
                thumbs.append(thumb(m))
            tick()

    for k, chd in enumerate(channels):
        chd["dmin"] = float(dmin[k]) if np.isfinite(dmin[k]) else 0.0
        chd["dmax"] = float(dmax[k]) if np.isfinite(dmax[k]) else 1.0
        if chd["dmax"] <= chd["dmin"]:
            chd["dmax"] = chd["dmin"] + 1
        chd["lo"] = max(chd["dmin"], min(chd["lo"], chd["dmax"]))
        chd["hi"] = max(chd["lo"] + 1e-6, min(chd["hi"], chd["dmax"]))

    meta = {
        "name": src.name, "subtitle": "  ·  ".join(sub), "width": W, "height": H, "dtype": kind,
        "bin": b, "rgb": bool(src.rgb), "axes": axes, "channels": channels,
        "pixelSize": (src.pixel_size * b) if src.pixel_size else None,
        "zStep": src.z_step, "times": times, "zpos": zpos, "info": info,
        "thumbs": thumbs if (len(sel["M"]) > 1 and thumbs) else None, "fps": recipe.fps,
        "lowPct": disp.low_pct, "highPct": disp.high_pct, "autoFrame": bool(getattr(ho, "auto_frame", False)),
        "preview": preview is not None,
        "panel": {"axis": _panel_axis(recipe, axes, len(chans)), "fill": recipe.panel_fill,
                  "count": int(recipe.panel_count), "merge": bool(recipe.panel_merge),
                  "gap": int(recipe.panel_gap), "bg": recipe.panel_bg,
                  "grids": {a: [max(0, int(v[0])), max(0, int(v[1]))]
                            for a, v in (getattr(ho, "grids", None) or {}).items() if a in "MTZ"}},
        "lutView": getattr(ho, "lut_view", "selected"),
        "overlays": overlays, "ui": ui,
        "title": ho.title.replace("{name}", src.name) if ho.title else "",
        "caption": ho.caption.replace("{name}", src.name), "start": start,
    }
    meta_json = json.dumps(meta, allow_nan=False, separators=(",", ":")).replace("</", "<\\/")
    with open(tmp, "w", encoding="utf-8") as fo:
        fo.write(HEAD.replace("__TITLE__", html.escape(src.name)).replace("__META__", meta_json))
        with open(tmp + ".chunks", "r", encoding="ascii") as fc:
            while True:
                block = fc.read(8 * 1024 * 1024)
                if not block:
                    break
                fo.write(block)
        fo.write(TAIL)
    os.remove(tmp + ".chunks")
    os.replace(tmp, job.out_path)
