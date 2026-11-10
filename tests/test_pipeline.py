"""End-to-end smoke test: builds sample files of every kind, plans and exports them.

Run:  .venv\\Scripts\\python.exe -m tests.test_pipeline   (from the ImageStudios folder)
"""
import os
import shutil
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import tifffile
from PIL import Image
from PySide6.QtGui import QGuiApplication

from imagestudios.annotate import Annot
from imagestudios.export import render_unit, run_job
from imagestudios.plan import AxisRule, Panel, Recipe, build_plan, leaves
from imagestudios.sources import open_source

app = QGuiApplication.instance() or QGuiApplication([])


def make_samples(d):
    yy, xx = np.mgrid[0:96, 0:128]
    # OME-TIFF T5 Z4 C2, 16-bit
    data = np.zeros((5, 4, 2, 96, 128), np.uint16)
    for t in range(5):
        for z in range(4):
            data[t, z, 0] = (np.sin((xx + t * 8) / 9.0) * 1000 + 1500 + z * 200)
            data[t, z, 1] = ((xx - 64) ** 2 + (yy - 48) ** 2 < (10 + t * 5 + z) ** 2) * 3000 + 100
    tifffile.imwrite(os.path.join(d, "cells.ome.tif"), data, ome=True,
                     metadata={"axes": "TZCYX", "Channel": {"Name": ["GFP", "mCherry"]},
                               "PhysicalSizeX": 0.5, "PhysicalSizeXUnit": "µm",
                               "PhysicalSizeY": 0.5, "PhysicalSizeZ": 2.0, "TimeIncrement": 30.0,
                               "TimeIncrementUnit": "s"})
    # ImageJ hyperstack Z3 C3
    hj = (np.random.default_rng(0).random((3, 3, 64, 64)) * 255).astype(np.uint8)
    tifffile.imwrite(os.path.join(d, "stack_ij.tif"), hj, imagej=True, resolution=(1 / 0.25, 1 / 0.25),
                     metadata={"axes": "ZCYX", "unit": "um", "spacing": 1.5})
    # plain RGB images
    for i, c in enumerate([(255, 0, 0), (0, 160, 255), (40, 200, 90)]):
        Image.new("RGB", (120 + i * 10, 80), c).save(os.path.join(d, f"photo_{i}.jpg"))
    Image.new("RGBA", (50, 50), (255, 0, 0, 128)).save(os.path.join(d, "alpha.png"))
    # animated gif
    frames = [Image.new("RGB", (40, 40), (i * 50, 0, 255 - i * 50)) for i in range(4)]
    frames[0].save(os.path.join(d, "anim.gif"), save_all=True, append_images=frames[1:], duration=100)
    # svg
    with open(os.path.join(d, "logo.svg"), "w") as fh:
        fh.write('<svg xmlns="http://www.w3.org/2000/svg" width="200" height="100" viewBox="0 0 200 100">'
                 '<rect x="5" y="5" width="190" height="90" rx="20" fill="#3a7"/>'
                 '<circle cx="100" cy="50" r="30" fill="white"/></svg>')
    return d


def check(cond, msg):
    print(("  ok   " if cond else "  FAIL ") + msg)
    if not cond:
        check.failed = True


check.failed = False


def main():
    d = tempfile.mkdtemp(prefix="imagestudios_")
    out = os.path.join(d, "out")
    try:
        make_samples(d)
        paths = sorted(os.path.join(d, f) for f in os.listdir(d) if os.path.isfile(os.path.join(d, f)))
        srcs = [open_source(p) for p in paths]
        for s in srcs:
            print(f"{os.path.basename(s.path):18s} {s.kind:10s} {s.describe()}  ch={[c.name for c in s.channels]}")
        ome = next(s for s in srcs if s.name == "cells")
        ome2 = open_source(ome.path)
        check(ome.axes == {"T": 5, "Z": 4, "C": 2}, "OME axes T5 Z4 C2")
        check([c.name for c in ome.channels] == ["GFP", "mCherry"], "OME channel names")
        ij = next(s for s in srcs if s.name == "stack_ij")
        check(ij.axes.get("Z") == 3 and ij.axes.get("C") == 3, "ImageJ hyperstack axes")
        check(next(s for s in srcs if s.name == "anim").axes == {"T": 4}, "GIF frames -> T")
        svg = next(s for s in srcs if s.name == "logo")
        check((svg.width, svg.height) == (200, 100), "SVG size")

        # 1) image sequence from the OME stack
        r = Recipe(output="images", fmt="png", out_dir=out)
        jobs, warn = build_plan([ome], r)
        check(len(jobs) == 5 * 4, f"T x Z iterate, C composite -> 20 PNGs ({len(jobs)})")
        print("    e.g.", os.path.basename(jobs[0].out_path), os.path.basename(jobs[-1].out_path))
        for j in jobs[:3]:
            run_job(j, r)
        check(os.path.exists(jobs[0].out_path), "PNG written")

        # split channels + max-projection over Z
        r2 = Recipe(output="images", fmt="tif-raw", out_dir=out,
                    rules={"C": AxisRule("iterate"), "Z": AxisRule("max")})
        jobs, _ = build_plan([ome], r2)
        check(len(jobs) == 10, f"T x C with Z max-projection -> 10 raw TIFFs ({len(jobs)})")
        print("    e.g.", os.path.basename(jobs[0].out_path))
        run_job(jobs[0], r2)
        a = tifffile.imread(jobs[0].out_path)
        check(a.dtype == np.uint16 and a.shape == (96, 128), "raw TIFF keeps uint16")
        check(int(a.max()) == int(ome.plane({"T": 0, "Z": 3, "C": 0}).max()), "max projection correct")

        # 2) GIF & MP4 scrubbing Z per T
        for fmt in ("gif", "mp4", "webp"):
            r3 = Recipe(output="animation", fmt=fmt, fps=5, out_dir=out,
                        rules={"Z": AxisRule("animate"), "T": AxisRule("fixed", "3")})
            jobs, _ = build_plan([ome], r3)
            check(len(jobs) == 1 and len(jobs[0].frames) == 4, f"{fmt}: 1 animation of 4 Z frames")
            run_job(jobs[0], r3)
            check(os.path.getsize(jobs[0].out_path) > 0, f"{fmt} written: {os.path.basename(jobs[0].out_path)}")
        # odd-size mp4 + default animate axis on GIF source
        r4 = Recipe(output="animation", fmt="mp4", out_dir=out)
        jobs, w = build_plan([s for s in srcs if s.name in ("anim", "cells")], r4)
        print("    animations:", [os.path.basename(j.out_path) for j in jobs])
        for j in jobs:
            run_job(j, r4)
        check(len(jobs) == 1 + 4, "anim.gif -> 1 mp4; cells -> T animated, one per Z")

        # 3) chain photos into a PDF & into a GIF
        photos = [s for s in srcs if s.name.startswith("photo") or s.name in ("alpha", "logo")]
        r5 = Recipe(output="pdf", combine=True, out_dir=out, combined_name="album")
        jobs, _ = build_plan(photos, r5)
        check(len(jobs) == 1 and len(jobs[0].frames) == 5, "combined PDF of 5 pages")
        run_job(jobs[0], r5)
        import pypdfium2 as pdfium
        check(len(pdfium.PdfDocument(jobs[0].out_path)) == 5, "PDF has 5 pages")
        r6 = Recipe(output="animation", fmt="gif", combine=True, out_dir=out, combined_name="slideshow", fps=2)
        jobs, _ = build_plan(photos, r6)
        run_job(jobs[0], r6)
        check(Image.open(jobs[0].out_path).n_frames == 5, "combined GIF has 5 frames")

        # 4) SVG -> PNG at 3x
        svg.set_scale(3)
        r7 = Recipe(output="images", fmt="png", out_dir=out, background="transparent")
        jobs, _ = build_plan([svg], r7)
        run_job(jobs[0], r7)
        im = Image.open(jobs[0].out_path)
        check(im.size == (600, 300) and im.mode == "RGBA", f"SVG rendered 600x300 RGBA ({im.size} {im.mode})")

        # 5) PDF as input -> PNG per page
        pdfsrc = open_source(os.path.join(out, "album.pdf"))
        check(pdfsrc.axes == {"P": 5}, "PDF input pages -> P axis")
        jobs, _ = build_plan([pdfsrc], Recipe(output="images", fmt="jpg", out_dir=out))
        run_job(jobs[0], Recipe(output="images", fmt="jpg"))
        check(len(jobs) == 5 and os.path.exists(jobs[0].out_path), "PDF pages -> JPEGs")

        # 6) MP4 as input
        vid = open_source(os.path.join(out, next(j for j in os.listdir(out) if j.startswith("cells") and j.endswith(".mp4"))))
        check(vid.axes.get("T", 0) >= 2, f"MP4 input frames -> T ({vid.axes})")
        # 7) metadata from OME / ImageJ
        check(abs((ome.pixel_size or 0) - 0.5) < 1e-9, f"OME pixel size 0.5 um ({ome.pixel_size})")
        check(abs((ome.z_step or 0) - 2.0) < 1e-9, f"OME z step 2 um ({ome.z_step})")
        check(ome.time_s({"T": 3}) == 90.0, f"OME time of T4 = 90 s ({ome.time_s({'T': 3})})")
        check(abs((ij.pixel_size or 0) - 0.25) < 1e-6 and abs((ij.z_step or 0) - 1.5) < 1e-9,
              f"ImageJ pixel size / spacing ({ij.pixel_size}, {ij.z_step})")

        # 8) panel of channels (+ merged tile), 3 per row, one panel per time point
        r8 = Recipe(output="images", fmt="png", out_dir=out, panel_gap=4, panel_axis="C", panel_count=3,
                    scale_mode="manual", scale_pct=100,
                    rules={"T": AxisRule("iterate", "1-5:2"), "Z": AxisRule("fixed", "1")},
                    annot=Annot(timestamp=True, scalebar=True, channels=True, zpos=True))
        jobs, w = build_plan([ome], r8)
        u = jobs[0].frames[0]
        check(len(jobs) == 3 and isinstance(u, Panel) and len(u.cells) == 1 and len(u.cells[0]) == 3,
              f"3 panels of (2 channels + merge) ({len(jobs)} jobs)")
        check(u.cells[0][2].channel is None and jobs[1].frames[0].cells[0][0].idx["T"] == 2,
              "merged tile + one panel per time point")
        run_job(jobs[0], r8)
        im = Image.open(jobs[0].out_path)
        check(im.size == (3 * 128 + 4 * 4, 96 + 2 * 4), f"manual 100% panel size {im.size}")
        r8.scale_mode = "auto"
        run_job(jobs[0], r8)
        im = Image.open(jobs[0].out_path)
        check(im.size == (3 * 256 + 4 * 4, 192 + 2 * 4), f"auto size enlarges small tiles 2x {im.size}")
        plain = render_unit(leaves(u)[-1], Recipe())
        annotated = render_unit(leaves(u)[-1], r8)
        diff = np.abs(np.asarray(annotated, np.int16) - np.asarray(plain, np.int16)).sum()
        check(diff > 0, "annotations change the pixels")
        # wrap a row of 4 Z slices into 2 columns
        r9 = Recipe(output="images", out_dir=out, panel_axis="Z", panel_count=0, rules={"T": AxisRule("fixed", "1")})
        u9 = build_plan([ome], r9)[0][0].frames[0]
        check(len(u9.cells) == 1 and len(u9.cells[0]) == 4, "Z panel auto: 4 slices in one row")
        r9b = Recipe(output="images", out_dir=out, panel_axis="Z", panel_fill="col", panel_count=3,
                     rules={"T": AxisRule("fixed", "1")})
        u9b = build_plan([ome], r9b)[0][0].frames[0]
        check(len(u9b.cells) == 3 and u9b.cells[1][0].idx["Z"] == 1 and u9b.cells[0][1].idx["Z"] == 3,
              "3 images per column, filled column-first")
        # two files side by side, as an animation
        r10 = Recipe(output="animation", fmt="gif", out_dir=out, panel_axis="F", panel_count=2, combined_name="side",
                     rules={"T": AxisRule("animate"), "Z": AxisRule("fixed", "1"), "C": AxisRule("composite")})
        jobs, w = build_plan([ome, ome2], r10)
        check(len(jobs) == 1 and len(jobs[0].frames) == 5 and len(jobs[0].frames[0].cells[0]) == 2,
              f"files side by side animation ({[len(j.frames) for j in jobs]}) {w}")
        run_job(jobs[0], r10)
        check(Image.open(jobs[0].out_path).n_frames == 5, "side-by-side GIF written")
        # time stamp text formatting
        from imagestudios.annotate import format_time
        check(format_time(5400, "auto", 7200) == "90.0 min" and format_time(3661, "hms", 0) == "01:01:01",
              "time formatting")

        # 9) interactive HTML viewer: raw 16-bit data round-trips exactly
        import base64, json, re, zlib
        r11 = Recipe(output="html", fmt="html", out_dir=out, rules={"T": AxisRule("iterate", "2-4")})
        jobs, w = build_plan([ome, next(s for s in srcs if s.name == "photo_0")], r11)
        check(len(jobs) == 2 and jobs[0].out_path.endswith(".html"), "one HTML per file")
        for j in jobs:
            run_job(j, r11)
        page = open(jobs[0].out_path, encoding="utf-8").read()
        meta = json.loads(re.search(r'<script id="meta" type="application/json">(.*?)</script>', page, re.S).group(1))
        chunk = re.search(r'id="chunk-0">(.*?)</script>', page, re.S).group(1)
        raw = np.frombuffer(zlib.decompress(base64.b64decode(chunk)), np.uint16)
        check(meta["dtype"] == "u16" and meta["axes"]["T"]["n"] == 3 and meta["axes"]["Z"]["n"] == 4 and
              len(meta["channels"]) == 2, f"HTML metadata (T3 Z4 C2 u16) {meta['axes']}")
        expect = ome.plane({"T": 2, "Z": 1, "C": 1})
        got = raw[((1 * 4 + 1) * 2 + 1) * 96 * 128:][: 96 * 128].reshape(96, 128)
        check(np.array_equal(got, expect), "HTML embeds exact raw 16-bit values")
        check(meta["pixelSize"] == 0.5 and meta["times"][0][0] == 30.0, "HTML pixel size + per-frame times")
        from imagestudios.plan import HTML_PRESETS, HtmlOpts
        r12 = Recipe(output="html", fmt="html", out_dir=out, combined_name="x",
                     html=HtmlOpts(preset="player", tools=dict(HTML_PRESETS["player"][1]), theme="light",
                                   title="My {name}", autoplay=True))
        j12 = build_plan([ome], r12)[0][0]
        run_job(j12, r12)
        m12 = json.loads(re.search(r'<script id="meta" type="application/json">(.*?)</script>',
                                   open(j12.out_path, encoding="utf-8").read(), re.S).group(1))
        check(m12["ui"]["lut"] is False and m12["ui"]["playback"] is True and m12["ui"]["theme"] == "light" and m12["title"] == "My cells" and m12["ui"]["autoplay"] is True,
              "HTML format options reach the page (player preset, light, title)")
        r13 = Recipe(output="html", fmt="html", out_dir=out, template="{name}_tpanel",
                     panel_axis="T", panel_fill="col", panel_count=2, panel_gap=9, panel_bg="black",
                     rules={"T": AxisRule("iterate", "1-5:2")}, html=HtmlOpts(lut_view="beside"))
        j13 = build_plan([ome], r13)[0][0]
        run_job(j13, r13)
        m13 = json.loads(re.search(r'<script id="meta" type="application/json">(.*?)</script>',
                                   open(j13.out_path, encoding="utf-8").read(), re.S).group(1))
        check({k: v for k, v in m13["panel"].items() if k != "grids"}
              == {"axis": "T", "fill": "col", "count": 2, "merge": True, "gap": 9, "bg": "black"}
              and m13["panel"]["grids"]["T"] == [0, 0]
              and m13["axes"]["T"]["n"] == 3 and m13["lutView"] == "beside" and "panelCard" not in
              open(j13.out_path, encoding="utf-8").read(), f"image Panel settings fix the HTML tiles {m13['panel']}")
        r14 = Recipe(output="html", fmt="html", out_dir=out, template="{name}_mpanel", panel_axis="M")
        j14 = build_plan([ome], r14)[0][0]
        run_job(j14, r14)
        m14 = json.loads(re.search(r'<script id="meta" type="application/json">(.*?)</script>',
                                   open(j14.out_path, encoding="utf-8").read(), re.S).group(1))
        check(m14["panel"]["axis"] == "", "panel of a missing axis (no positions) falls back to channels")
        r15 = Recipe(output="html", fmt="html", out_dir=out, template="{name}_zpages", panel_axis="Z",
                     html=HtmlOpts(grids={"Z": [1, 2], "T": [2, 2], "M": [3, 3]}))
        j15 = build_plan([ome], r15)[0][0]
        run_job(j15, r15)
        p15 = open(j15.out_path, encoding="utf-8").read()
        m15 = json.loads(re.search(r'<script id="meta" type="application/json">(.*?)</script>', p15, re.S).group(1))
        check(m15["panel"]["axis"] == "Z" and m15["panel"]["grids"] == {"Z": [1, 2], "T": [2, 2], "M": [3, 3]}
              and "function openSingle" in p15 and 'id="pager"' in p15,
              "HTML page grids per axis + pages / popup code in the page")
        page2 = open(jobs[1].out_path, encoding="utf-8").read()
        check('"rgb":true' in page2 and '"dtype":"u8"' in page2, "photo -> RGB 8-bit viewer")

        for s in srcs + [pdfsrc, vid]:
            s.close()
    finally:
        shutil.rmtree(d, ignore_errors=True)
    print("\nFAILED" if check.failed else "\nALL PASSED")
    sys.exit(1 if check.failed else 0)


if __name__ == "__main__":
    main()
