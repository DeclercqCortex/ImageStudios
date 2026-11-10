"""Execute planned jobs: write images, GIF/MP4/WebP animations and PDFs."""
from __future__ import annotations

import os

import numpy as np
from PIL import Image

from . import annotate
from .annotate import ITEM_AXIS
from .plan import Frame, Job, Panel, Recipe, leaves
from .render import plane_projected, render


class Cancelled(Exception):
    pass


def _bg(recipe: Recipe):
    return (0, 0, 0) if recipe.background == "black" else (255, 255, 255)


AUTO_MIN_SIDE = 512      # Auto size: small images are enlarged to at least this (whole-number factor)
AUTO_MIN_TILE = 256      # ... and panel tiles to at least this
AUTO_MAX_OUTPUT = 4096   # Auto size: a panel is kept within this many pixels
AUTO_MAX_SINGLE = 16384  # ... a single image keeps its full resolution up to this


def tile_dims(unit) -> tuple:
    """(rows, cols) of the unit counted in single tiles, including nested panels."""
    if not isinstance(unit, Panel):
        return 1, 1
    rows = 0
    cols = 0
    for row in unit.cells:
        dims = [tile_dims(c) if c is not None else (1, 1) for c in row]
        rows += max((d[0] for d in dims), default=1)
        cols = max(cols, sum(d[1] for d in dims))
    return max(rows, 1), max(cols, 1)


def scale_factor(src, recipe: Recipe, layout=(1, 1)) -> float:
    """Output pixels per source pixel for one tile."""
    if recipe.scale_mode == "manual":
        return max(0.01, (recipe.scale_pct or 100.0) / 100.0)
    rows, cols = layout
    w, h = max(1, src.width), max(1, src.height)
    side = max(w, h)
    f = 1.0
    if src.kind in ("microscopy", "image", "video"):
        n = max(rows, cols)
        target = AUTO_MIN_SIDE if n == 1 else max(AUTO_MIN_TILE, 1024 // n)
        if side < target:
            f = float(max(1, target // side))
    longest = max(cols * w, rows * h) * f
    cap = AUTO_MAX_SINGLE if rows * cols == 1 else AUTO_MAX_OUTPUT
    if longest > cap:
        f *= cap / longest
    return f


def frame_image(frame, recipe: Recipe, keep_alpha: bool, factor: float | None = None) -> Image.Image:
    arr = render(frame.source, frame.idx, frame.proj, frame.channel, recipe.display)
    im = Image.fromarray(arr)
    if im.mode == "RGBA" and not (keep_alpha and recipe.background == "transparent"):
        base = Image.new("RGB", im.size, _bg(recipe))
        base.paste(im, mask=im.getchannel("A"))
        im = base
    f = scale_factor(frame.source, recipe) if factor is None else factor
    if abs(f - 1.0) > 1e-6:
        w, h = max(1, round(im.width * f)), max(1, round(im.height * f))
        im = im.resize((w, h), Image.LANCZOS if f < 1 else Image.NEAREST if f >= 2 else Image.BICUBIC)
    return im


def overlay_plan(unit, annot) -> dict:
    """Decide which annotation goes on which tile (id(frame) -> set of items).

    Single images get everything. In a panel, an annotation whose axis is laid out
    across the panel (e.g. channel names when channels are tiled, time when T is
    tiled) appears on every tile; others appear once on the first tile, and the
    scale bar on the last tile.
    """
    items = annot.enabled_items()
    if not items:
        return {}
    if isinstance(unit, Frame):
        return {id(unit): set(items)}
    lv = leaves(unit)
    res = {id(f): set() for f in lv}
    panels = []

    def walk(u):
        if isinstance(u, Panel):
            panels.append(u)
            for row in u.cells:
                for c in row:
                    if c is not None:
                        walk(c)

    walk(unit)
    for it in items:
        ax = ITEM_AXIS[it]
        if it == "scalebar":
            targets = lv if annot.sb_every_tile else lv[-1:]
        else:
            targets = []
            for p in panels:
                if ax in p.tiled:
                    for row in p.cells:
                        for c in row:
                            if c is not None:
                                targets.append(leaves(c)[0])
            if not targets:
                # once per file (each file has its own clock, position, name ...)
                seen = {}
                for f in lv:
                    seen.setdefault(id(f.source), f)
                targets = list(seen.values())
        for f in targets:
            res[id(f)].add(it)
    return res


def _panel_bg(recipe):
    return (0, 0, 0) if recipe.panel_bg == "black" else (255, 255, 255)


def render_unit(unit, recipe: Recipe, keep_alpha=False, _plan=None, _root=True, _layout=None) -> Image.Image:
    plan = overlay_plan(unit, recipe.annot) if _plan is None else _plan
    layout = tile_dims(unit) if _layout is None else _layout
    if isinstance(unit, Frame):
        f = scale_factor(unit.source, recipe, layout)
        im = frame_image(unit, recipe, keep_alpha, f)
        items = plan.get(id(unit))
        if items:
            im = annotate.draw(im, unit, recipe.annot, items, px_scale=f)
        return im
    imgs = [[render_unit(c, recipe, False, plan, False, layout) if c is not None else None for c in row]
            for row in unit.cells]
    flat = [i for row in imgs for i in row if i is not None]
    if not flat:
        return Image.new("RGB", (8, 8), _panel_bg(recipe))
    cw = max(i.width for i in flat)
    ch = max(i.height for i in flat)
    gap = max(0, int(recipe.panel_gap))
    ncols = max(len(r) for r in imgs)
    nrows = len(imgs)
    margin = gap if _root else 0
    W = ncols * cw + (ncols - 1) * gap + 2 * margin
    H = nrows * ch + (nrows - 1) * gap + 2 * margin
    bg = _panel_bg(recipe)
    canvas = Image.new("RGB", (W, H), bg)
    for r, row in enumerate(imgs):
        for c, im in enumerate(row):
            if im is None:
                continue
            im = im.convert("RGB")
            if im.size != (cw, ch):
                im = _fit(im, (cw, ch), bg)
            canvas.paste(im, (margin + c * (cw + gap), margin + r * (ch + gap)))
    return canvas


def _fit(im: Image.Image, size, bg) -> Image.Image:
    if im.size == size:
        return im
    im = im.copy()
    im.thumbnail(size, Image.LANCZOS)
    canvas = Image.new(im.mode if im.mode in ("RGB", "RGBA") else "RGB", size, bg)
    canvas.paste(im, ((size[0] - im.width) // 2, (size[1] - im.height) // 2))
    return canvas


def run_job(job: Job, recipe: Recipe, tick=lambda: None, cancelled=lambda: False):
    os.makedirs(os.path.dirname(job.out_path) or ".", exist_ok=True)
    fmt = recipe.fmt
    if job.kind == "html":
        from .html_export import write_html

        write_html(job, recipe, tick, cancelled)
        return
    if job.kind == "image":
        f = job.frames[0]
        if fmt == "tif-raw" and isinstance(f, Frame):
            _write_raw_tiff(job.out_path, f)
        else:
            im = render_unit(f, recipe, keep_alpha=fmt in ("png", "webp", "tif"))
            src = getattr(f, "source", None)
            # a photo converted on its own keeps its EXIF (camera, date, GPS) and colour profile (e.g. Display P3)
            meta = dict(getattr(src, "photo_meta", None) or {}) if isinstance(f, Frame) else {}
            photo = bool(getattr(src, "lossy_photo", False))
            if fmt == "jpg":
                # camera photos are 4:2:0 already; 4:4:4 only helps sharp coloured overlays on scientific images
                sub = 2 if photo or recipe.quality < 90 else 0
                im.convert("RGB").save(job.out_path, "JPEG", quality=recipe.quality, subsampling=sub,
                                       optimize=True, **meta)
            elif fmt == "png":
                im.save(job.out_path, "PNG", optimize=False, compress_level=6, **meta)
            elif fmt in ("tif", "tif-raw"):
                im.save(job.out_path, "TIFF", compression="tiff_lzw", **meta)
            elif fmt == "webp":
                im.save(job.out_path, "WEBP", quality=recipe.quality, lossless=recipe.quality >= 100, **meta)
            elif fmt == "bmp":
                im.convert("RGB").save(job.out_path, "BMP")
        tick()
        return

    def frames_iter(keep_alpha=False):
        for f in job.frames:
            if cancelled():
                raise Cancelled()
            im = render_unit(f, recipe, keep_alpha)
            tick()
            yield im

    bg = _bg(recipe)
    if job.kind == "pdf":
        it = frames_iter()
        first = next(it).convert("RGB")
        rest = (im.convert("RGB") for im in it)
        first.save(job.out_path, "PDF", save_all=True, append_images=rest, resolution=150.0,
                   quality=recipe.quality)
        return

    # animation
    duration = max(1, int(round(1000.0 / max(recipe.fps, 0.01))))
    if fmt == "mp4":
        _write_mp4(job.out_path, frames_iter(), recipe, bg)
        return
    it = frames_iter(keep_alpha=False)
    first = next(it).convert("RGB")
    size = first.size
    rest = (_fit(im.convert("RGB"), size, bg) for im in it)
    if fmt == "gif":
        first.save(job.out_path, "GIF", save_all=True, append_images=rest, duration=duration,
                   loop=0 if recipe.loop else 1, disposal=1, optimize=False)
    else:
        first.save(job.out_path, "WEBP", save_all=True, append_images=rest, duration=duration,
                   loop=0 if recipe.loop else 1, quality=recipe.quality, lossless=recipe.quality >= 100)


def _write_mp4(path, frames, recipe: Recipe, bg):
    import imageio_ffmpeg

    gen = None
    size = None
    try:
        for im in frames:
            im = im.convert("RGB")
            if size is None:
                w, h = im.size
                size = (w + (w % 2), h + (h % 2))
                q = max(0.0, min(10.0, recipe.quality / 10.0))
                gen = imageio_ffmpeg.write_frames(
                    path, size, fps=recipe.fps, quality=q, codec="libx264",
                    pix_fmt_out="yuv420p", macro_block_size=1, ffmpeg_log_level="error",
                    output_params=["-movflags", "+faststart"])
                gen.send(None)
            if im.size != size:
                im = _fit(im, size, bg) if (abs(im.width - size[0]) > 1 or abs(im.height - size[1]) > 1) else _pad(im, size, bg)
            gen.send(np.ascontiguousarray(np.asarray(im)).tobytes())
    finally:
        if gen is not None:
            gen.close()


def _pad(im, size, bg):
    c = Image.new("RGB", size, bg)
    c.paste(im, (0, 0))
    return c


def _write_raw_tiff(path, frame):
    import tifffile

    src = frame.source
    if src.rgb or frame.channel is not None or "C" not in src.axes:
        idx = dict(frame.idx)
        if frame.channel is not None:
            idx["C"] = frame.channel
        data = plane_projected(src, idx, frame.proj)
        tifffile.imwrite(path, data, photometric="rgb" if (data.ndim == 3 and data.shape[-1] in (3, 4)) else "minisblack",
                         compression="zlib")
        return
    planes = []
    for c in range(src.axes["C"]):
        idx = dict(frame.idx)
        idx["C"] = c
        planes.append(plane_projected(src, idx, frame.proj))
    data = np.stack(planes)
    ij = data.dtype in (np.uint8, np.uint16, np.float32)
    if ij:
        tifffile.imwrite(path, data, imagej=True, metadata={"axes": "CYX", "mode": "composite"})
    else:
        tifffile.imwrite(path, data, compression="zlib")
