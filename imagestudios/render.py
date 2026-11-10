"""Turn raw planes (any dtype, any channel count) into 8-bit RGB(A) images."""
from __future__ import annotations

import itertools
from dataclasses import dataclass

import numpy as np

CONTRAST_MODES = {
    "auto": "Auto (consistent across stack)",
    "frame": "Auto (per frame)",
    "full": "Full bit-depth range",
    "none": "Raw values (no stretch)",
}


@dataclass
class Display:
    contrast: str = "auto"
    low_pct: float = 0.1
    high_pct: float = 99.9
    gray_single: bool = True   # a single channel on its own renders in grayscale


def plane_projected(src, idx: dict, proj: dict | None) -> np.ndarray:
    """Plane at idx; axes listed in proj (axis -> list of indices) are max-projected."""
    if not proj:
        return src.plane(idx)
    axes = list(proj)
    out = None
    for combo in itertools.product(*(proj[a] for a in axes)):
        i = dict(idx)
        i.update(zip(axes, combo))
        p = src.plane(i)
        out = p.copy() if out is None else np.maximum(out, p, out=out)
    return out


def _sample_pixels(a: np.ndarray, target=250_000) -> np.ndarray:
    flat = a.reshape(-1)
    step = max(1, flat.size // target)
    return flat[::step]


def _range_for_dtype(dt: np.dtype, sample: np.ndarray | None = None):
    if np.issubdtype(dt, np.integer):
        info = np.iinfo(dt)
        return float(max(info.min, 0)), float(info.max)
    if sample is not None and sample.size:
        return float(np.nanmin(sample)), float(np.nanmax(sample))
    return 0.0, 1.0


def stack_limits(src, c: int | None, disp: Display, proj=None) -> tuple:
    key = (c, disp.low_pct, disp.high_pct, tuple(sorted((proj or {}).keys())))
    if key in src.limits_cache:
        return src.limits_cache[key]
    axes = [a for a in src.axes if a != "C" and a not in (proj or {})]
    combos = list(itertools.product(*(range(src.axes[a]) for a in axes))) or [()]
    n = len(combos)
    pick = sorted(set(int(round(i)) for i in np.linspace(0, n - 1, min(n, 12))))
    samples = []
    for k in pick:
        idx = dict(zip(axes, combos[k]))
        if c is not None:
            idx["C"] = c
        samples.append(_sample_pixels(plane_projected(src, idx, proj)))
    s = np.concatenate(samples).astype(np.float64)
    lo, hi = np.nanpercentile(s, [disp.low_pct, disp.high_pct]) if s.size else (0, 1)
    if hi <= lo:
        hi = lo + 1
    src.limits_cache[key] = (float(lo), float(hi))
    return src.limits_cache[key]


def _limits(src, plane, c, disp: Display, proj):
    mode = disp.contrast
    if c is not None and 0 <= c < len(src.channels) and src.channels[c].limits:
        lo, hi = src.channels[c].limits
        return float(lo), float(hi if hi > lo else lo + 1)
    if mode == "frame":
        s = _sample_pixels(plane).astype(np.float64)
        lo, hi = np.nanpercentile(s, [disp.low_pct, disp.high_pct])
        return float(lo), float(hi if hi > lo else lo + 1)
    if mode == "full":
        bits = getattr(src, "bit_depth", None)
        if bits and np.issubdtype(plane.dtype, np.integer) and bits < plane.dtype.itemsize * 8:
            return 0.0, float(2 ** bits - 1)
        return _range_for_dtype(plane.dtype, _sample_pixels(plane))
    if mode == "none":
        if plane.dtype == np.uint8:
            return 0.0, 255.0
        return _range_for_dtype(plane.dtype, _sample_pixels(plane))
    return stack_limits(src, c, disp, proj)


def _norm(plane, lo, hi):
    a = plane.astype(np.float32)
    a -= lo
    a *= 1.0 / (hi - lo)
    np.clip(a, 0, 1, out=a)
    return a


def render(src, idx: dict, proj: dict | None = None, channel: int | None = None,
           disp: Display | None = None) -> np.ndarray:
    """Return uint8 array (Y, X, 3) or (Y, X, 4).

    channel=None -> composite of visible channels; int -> only that channel.
    """
    disp = disp or Display()
    if src.rgb:
        p = plane_projected(src, idx, proj)
        if p.ndim == 2:
            p = np.stack([p] * 3, -1)
        if p.dtype != np.uint8:
            lo, hi = _limits(src, p, None, disp, proj)
            p = (_norm(p, lo, hi) * 255).astype(np.uint8)
        return p

    nC = src.axes.get("C", 0)
    if nC == 0:
        chans = [(None, (255, 255, 255))]
    elif channel is not None:
        col = (255, 255, 255) if disp.gray_single else src.channels[channel].color
        chans = [(channel, col)]
    else:
        chans = [(i, ch.color) for i, ch in enumerate(src.channels) if ch.visible]
        if not chans:
            chans = [(0, src.channels[0].color)]

    acc = None
    for c, col in chans:
        i = dict(idx)
        if c is not None:
            i["C"] = c
        p = plane_projected(src, i, proj)
        if p.ndim == 3:  # unexpected sample axis: take luminance
            p = p.mean(axis=-1)
        if disp.contrast == "none" and p.dtype == np.uint8:
            n = p.astype(np.float32) / 255.0
        else:
            lo, hi = _limits(src, p, c, disp, proj)
            n = _norm(p, lo, hi)
        rgb = n[..., None] * (np.asarray(col, np.float32) / 255.0)
        acc = rgb if acc is None else acc + rgb
    np.clip(acc, 0, 1, out=acc)
    return (acc * 255 + 0.5).astype(np.uint8)
