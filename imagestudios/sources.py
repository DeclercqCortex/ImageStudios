"""Readers: every supported file becomes a `Source` with named axes.

A Source exposes non-spatial axes (T, M, Z, C, P, I ...) with sizes and returns
2-D planes (Y, X) or colour planes (Y, X, 3|4) for a given index dict.
"""
from __future__ import annotations

import os
import re
import threading
from dataclasses import dataclass

import numpy as np

AXIS_LABELS = {
    "M": "Position",
    "T": "Time",
    "Z": "Z-slice",
    "C": "Channel",
    "P": "Page",
    "I": "Frame",
}
# Iteration / naming order for axes.
AXIS_ORDER = ["M", "T", "Z", "C", "P", "I"]

DEFAULT_COLORS = [
    (0, 255, 0), (255, 0, 255), (0, 200, 255), (255, 60, 60),
    (60, 90, 255), (255, 220, 0), (255, 255, 255),
]

SCI_EXT = {".nd2"}
TIFF_EXT = {".tif", ".tiff", ".ome.tif", ".ome.tiff", ".btf", ".tf8"}
SVG_EXT = {".svg", ".svgz"}
PDF_EXT = {".pdf"}
VIDEO_EXT = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v", ".wmv", ".mpg", ".mpeg"}
RASTER_EXT = {
    ".png", ".jpg", ".jpeg", ".jpe", ".jfif", ".gif", ".bmp", ".webp", ".ico",
    ".tga", ".ppm", ".pgm", ".pbm", ".pnm", ".dib", ".pcx", ".psd", ".jp2",
    ".j2k", ".avif", ".heic", ".heif", ".apng", ".qoi", ".dds", ".eps",
}
SUPPORTED_EXT = SCI_EXT | TIFF_EXT | SVG_EXT | PDF_EXT | VIDEO_EXT | RASTER_EXT

_PDFIUM_LOCK = threading.Lock()


def ordered_axes(keys) -> list[str]:
    keys = list(keys)
    known = [a for a in AXIS_ORDER if a in keys]
    return known + [k for k in keys if k not in known]


def axis_label(a: str) -> str:
    return AXIS_LABELS.get(a, a)


def file_ext(path: str) -> str:
    low = path.lower()
    for double in (".ome.tiff", ".ome.tif"):
        if low.endswith(double):
            return double
    return os.path.splitext(low)[1]


def file_stem(path: str) -> str:
    base = os.path.basename(path)
    ext = file_ext(path)
    return base[: len(base) - len(ext)] if ext else base


@dataclass
class Channel:
    name: str
    color: tuple
    visible: bool = True
    limits: tuple | None = None   # manual display range (min, max) in raw units


_UNIT_TO_UM = {"m": 1e6, "cm": 1e4, "mm": 1e3, "um": 1.0, "\u00b5m": 1.0, "\u03bcm": 1.0, "micron": 1.0,
               "microns": 1.0, "micrometer": 1.0, "nm": 1e-3, "pm": 1e-6, "\u00c5": 1e-4}
_UNIT_TO_S = {"s": 1.0, "sec": 1.0, "ms": 1e-3, "\u00b5s": 1e-6, "us": 1e-6, "ns": 1e-9, "min": 60.0, "h": 3600.0}


def to_um(value, unit) -> float | None:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    u = (unit or "um").strip()
    f = _UNIT_TO_UM.get(u, _UNIT_TO_UM.get(u.lower(), 1.0))
    return v * f if v > 0 else None


def to_s(value, unit) -> float | None:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v * _UNIT_TO_S.get((unit or "s").strip(), 1.0)


class Source:
    kind = "image"

    def __init__(self, path: str):
        self.path = path
        self.name = file_stem(path)
        self.axes: dict[str, int] = {}
        self.height = 0
        self.width = 0
        self.dtype = np.dtype(np.uint8)
        self.rgb = False          # planes already carry colour (Y, X, 3|4)
        self.channels: list[Channel] = []
        self.fps: float | None = None
        self.scientific = False   # use contrast stretching by default
        self.bit_depth: int | None = None  # significant bits (e.g. 12 for 12-bit cameras)
        self.lock = threading.RLock()
        self.current: dict[str, int] = {}
        self.limits_cache: dict = {}
        self.render_scale = 1.0   # vector sources
        self.pdf_dpi = 150.0      # pdf sources
        # ---- physical metadata (None = unknown) ----
        self.pixel_size: float | None = None      # um per pixel (effective, user-editable)
        self.pixel_size_meta: float | None = None
        self.z_step: float | None = None           # um between Z slices
        self.z_step_meta: float | None = None
        self.interval_s: float | None = None       # seconds between T frames (fallback / override)
        self.interval_meta: float | None = None
        self.use_interval = False                  # True: ignore per-frame timestamps, use interval
        self._times: dict = {}                     # (t, m, z) -> seconds since acquisition start
        self._zpos: dict = {}                      # (m, z) -> um (relative to first slice)
        self.position_names: dict = {}             # m -> name
        self.meta: dict = {}                       # free-form details for display

    # ---- to override -------------------------------------------------
    def _plane(self, idx: dict) -> np.ndarray:
        raise NotImplementedError

    # ---- public --------------------------------------------------------
    def plane(self, idx: dict) -> np.ndarray:
        full = {a: int(idx.get(a, self.current.get(a, 0))) for a in self.axes}
        for a, n in self.axes.items():
            full[a] = max(0, min(n - 1, full[a]))
        with self.lock:
            return np.asarray(self._plane(full))

    def init_current(self):
        self.current = {a: 0 for a in self.axes}

    def channel_name(self, c: int) -> str:
        if 0 <= c < len(self.channels):
            return self.channels[c].name
        return f"C{c + 1}"

    # ---- metadata helpers ------------------------------------------------
    def finish_meta(self):
        self.pixel_size_meta = self.pixel_size
        if self.interval_s is None and self.fps:
            self.interval_s = 1.0 / self.fps
        self.interval_meta = self.interval_s
        self.z_step_meta = self.z_step

    def has_times(self) -> bool:
        return bool(self._times) or bool(self.interval_s)

    def time_s(self, idx: dict, zero: str = "position") -> float | None:
        """Elapsed time of the frame at idx in seconds.

        zero="position": t=0 at the first time point of the same position.
        zero="experiment": t=0 at the very first frame acquired in the file.
        """
        t, m, z = idx.get("T", 0), idx.get("M", 0), idx.get("Z", 0)
        if self._times and not self.use_interval:
            v = self._times.get((t, m, z))
            if v is None:
                v = self._times.get((t, m, 0))
            if v is not None:
                if zero == "experiment":
                    return v - self._t_min()
                base = self._times.get((0, m, z), self._times.get((0, m, 0)))
                return v - (base if base is not None else self._t_min())
        if self.interval_s:
            return t * self.interval_s
        return None

    def _t_min(self):
        if getattr(self, "_tmin_cache", None) is None:
            self._tmin_cache = min(self._times.values()) if self._times else 0.0
        return self._tmin_cache

    def time_span(self) -> float:
        n = self.axes.get("T", 1)
        v = self.time_s({"T": n - 1, "M": self.current.get("M", 0)})
        return abs(v) if v else 0.0

    def z_um(self, idx: dict) -> float | None:
        z, m = idx.get("Z", 0), idx.get("M", 0)
        user_changed = self.z_step is not None and self.z_step != self.z_step_meta
        if self._zpos and not user_changed:
            v = self._zpos.get((m, z), self._zpos.get((0, z)))
            if v is not None:
                return v
        return z * self.z_step if self.z_step else None

    def position_name(self, m: int) -> str:
        return self.position_names.get(m) or f"Pos {m + 1}"

    def info_lines(self) -> list:
        out = [f"File: {self.path}", f"Type: {self.kind}", f"Dimensions: {self.describe()}"]
        if self.pixel_size:
            out.append(f"Pixel size: {self.pixel_size:.4g} \u00b5m/px  (field of view {self.pixel_size * self.width:.1f}"
                       f" \u00d7 {self.pixel_size * self.height:.1f} \u00b5m)")
        else:
            out.append("Pixel size: unknown (enter it to enable the scale bar)")
        if self.z_step:
            out.append(f"Z step: {self.z_step:.4g} \u00b5m")
        if self._times:
            out.append(f"Per-frame timestamps: {len(self._times)} frames")
        if self.interval_s:
            out.append(f"Frame interval: {self.interval_s:.4g} s")
        if self.channels:
            out.append("Channels: " + ", ".join(c.name for c in self.channels))
        if self.position_names:
            names = [self.position_names[k] for k in sorted(self.position_names)][:10]
            out.append("Positions: " + ", ".join(names) + (" \u2026" if len(self.position_names) > 10 else ""))
        for k, v in self.meta.items():
            out.append(f"{k}: {v}")
        return out

    def describe(self) -> str:
        parts = [f"{a}{n}" for a, n in ((a, self.axes[a]) for a in ordered_axes(self.axes))]
        dims = " ".join(parts) if parts else "single image"
        color = "RGB" if self.rgb else str(self.dtype)
        return f"{dims}  ·  {self.width}×{self.height}  {color}"

    def ensure_channels(self):
        n = self.axes.get("C", 0)
        while len(self.channels) < n:
            i = len(self.channels)
            self.channels.append(Channel(f"C{i + 1}", DEFAULT_COLORS[i % len(DEFAULT_COLORS)]))
        if n == 0:
            self.channels = []

    def close(self):
        pass


# ---------------------------------------------------------------------------
# ND2 (Nikon NIS-Elements)
# ---------------------------------------------------------------------------
def _nd2_color(ch):
    c = getattr(ch, "color", None)
    if c is not None and all(hasattr(c, k) for k in ("r", "g", "b")):
        return (int(c.r), int(c.g), int(c.b))
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        v = getattr(ch, "colorRGBA", None)
        if v is None:
            v = getattr(ch, "colorRGB", None)
    if v is None:
        return None
    v = int(v)
    return (v & 255, (v >> 8) & 255, (v >> 16) & 255)


class ND2Source(Source):
    kind = "microscopy"

    def __init__(self, path):
        super().__init__(path)
        import nd2

        self._f = nd2.ND2File(path)
        sizes = dict(self._f.sizes)
        self._dims = list(sizes.keys())
        self._arr = self._f.to_dask()
        self._map = {}  # nd2 dim -> our axis letter
        for d, n in sizes.items():
            if d in ("Y", "X"):
                continue
            if d == "S":
                self.rgb = True
                continue
            ours = {"P": "M"}.get(d, d)
            self._map[d] = ours
            if n > 1 or d == "C":
                self.axes[ours] = n
        if self.axes.get("C", 0) <= 1 and "C" in self.axes:
            del self.axes["C"]
        self.height, self.width = sizes.get("Y", 0), sizes.get("X", 0)
        self.dtype = np.dtype(self._f.dtype)
        self.scientific = not self.rgb
        try:
            self.bit_depth = int(self._f.attributes.bitsPerComponentSignificant)
        except Exception:
            pass
        try:
            for i, ch in enumerate(self._f.metadata.channels or []):
                name = ch.channel.name or f"C{i + 1}"
                col = _nd2_color(ch.channel)
                if col is None or col in ((0, 0, 0), (255, 255, 255)) or sum(col) < 100:
                    col = DEFAULT_COLORS[i % len(DEFAULT_COLORS)]
                self.channels.append(Channel(name, col))
        except Exception:
            self.channels = []
        if "C" in self.axes:
            self.channels = self.channels[: self.axes["C"]]
        self.ensure_channels()
        self._read_nd2_meta()
        self.finish_meta()
        self.init_current()

    def _read_nd2_meta(self):
        f = self._f
        try:
            vs = f.voxel_size()
            if vs.x and vs.x > 0 and not (vs.x == 1 and vs.y == 1):
                self.pixel_size = float(vs.x)
            if "Z" in self.axes and vs.z and vs.z > 0:
                self.z_step = float(vs.z)
        except Exception:
            pass
        try:
            for loop in f.experiment or []:
                typ = getattr(loop, "type", "")
                par = loop.parameters
                if typ == "TimeLoop" and getattr(par, "periodMs", 0):
                    self.interval_s = par.periodMs / 1000.0
                elif typ == "ZStackLoop" and getattr(par, "stepUm", 0):
                    self.z_step = float(par.stepUm)
                elif typ == "XYPosLoop":
                    for i, pt in enumerate(getattr(par, "points", []) or []):
                        if getattr(pt, "name", None):
                            self.position_names[i] = pt.name
        except Exception:
            pass
        try:
            for ev in f.events(orient="records"):
                t = int(ev.get("T Index", 0) or 0)
                m = int(ev.get("P Index", 0) or 0)
                z = int(ev.get("Z Index", 0) or 0)
                if ev.get("Time [s]") is not None:
                    self._times[(t, m, z)] = float(ev["Time [s]"])
                if ev.get("Z-Series") is not None:
                    self._zpos[(m, z)] = float(ev["Z-Series"])
                nm = ev.get("Position Name")
                if nm and m not in self.position_names:
                    self.position_names[m] = str(nm)
            if "Z" in self.axes and self._zpos:
                for m in {k[0] for k in self._zpos}:
                    base = self._zpos.get((m, 0))
                    if base is not None:
                        for z in range(self.axes["Z"]):
                            if (m, z) in self._zpos:
                                self._zpos[(m, z)] -= base
            else:
                self._zpos = {}
        except Exception:
            pass
        if "T" in self.axes and self._times and not self.interval_s:
            ts = sorted(v for (t, m, z), v in self._times.items() if m == 0 and z == 0)
            if len(ts) > 1:
                self.interval_s = (ts[-1] - ts[0]) / (len(ts) - 1)
        try:
            mic = f.metadata.channels[0].microscope
            if mic.objectiveName:
                self.meta["Objective"] = mic.objectiveName
            if mic.objectiveMagnification:
                self.meta["Magnification"] = f"{mic.objectiveMagnification:g}x"
            if mic.objectiveNumericalAperture:
                self.meta["NA"] = f"{mic.objectiveNumericalAperture:g}"
            if mic.zoomMagnification and mic.zoomMagnification != 1:
                self.meta["Zoom"] = f"{mic.zoomMagnification:g}x"
            if mic.modalityFlags:
                self.meta["Modality"] = ", ".join(mic.modalityFlags)
        except Exception:
            pass
        try:
            em = [f"{c.channel.name} {c.channel.emissionLambdaNm:g} nm" for c in f.metadata.channels
                  if getattr(c.channel, "emissionLambdaNm", None)]
            if em:
                self.meta["Emission"] = ", ".join(em)
        except Exception:
            pass
        try:
            d = f.text_info.get("date")
            if d:
                self.meta["Acquired"] = d.strip()
        except Exception:
            pass
        if self.bit_depth:
            self.meta["Bit depth"] = f"{self.bit_depth}-bit"

    def position_block(self, m: int):
        """All planes of one position at once: (array, our-axis letter per dim). Much faster
        than reading plane by plane."""
        per_pos = self._arr.nbytes / max(1, self._f.sizes.get("P", 1))
        if per_pos > 1.5e9:
            return None, None
        key, dims = [], []
        for d in self._dims:
            if d == "P":
                key.append(m)
            else:
                key.append(slice(None))
                dims.append("YX" if d in ("Y", "X") else ("S" if d == "S" else self._map[d]))
        with self.lock:
            return np.asarray(self._arr[tuple(key)].compute()), dims

    def _plane(self, idx):
        key = []
        for d in self._dims:
            if d in ("Y", "X", "S"):
                key.append(slice(None))
            else:
                key.append(idx.get(self._map[d], 0))
        return np.asarray(self._arr[tuple(key)].compute())

    def close(self):
        try:
            self._f.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# TIFF / OME-TIFF / ImageJ hyperstacks
# ---------------------------------------------------------------------------
_TIFF_AXIS_MAP = {"T": "T", "Z": "Z", "C": "C", "I": "I", "Q": "I", "O": "I", "M": "M", "R": "M"}


def _int_to_rgb(v: int) -> tuple:
    v &= 0xFFFFFFFF  # OME colours are signed RGBA ints
    return ((v >> 24) & 255, (v >> 16) & 255, (v >> 8) & 255)


class TiffSource(Source):
    kind = "microscopy"

    def __init__(self, path):
        super().__init__(path)
        import tifffile

        self._tf = tifffile.TiffFile(path)
        series = self._tf.series
        s0 = series[0]
        self._series = [s for s in series if s.shape == s0.shape and s.axes == s0.axes and s.dtype == s0.dtype]
        axes_str = s0.axes
        shape = s0.shape
        self.dtype = np.dtype(s0.dtype)

        # Identify spatial layout.
        self._lead = []      # list of (tiff_letter, our_letter, size)
        self._sample_axis = None
        used = set()
        for letter, n in zip(axes_str, shape):
            if letter in ("Y", "X"):
                continue
            if letter == "S" and n in (3, 4) and self.dtype == np.uint8:
                self._sample_axis = "S"
                self.rgb = True
                continue
            ours = _TIFF_AXIS_MAP.get(letter, letter)
            if letter == "S":
                ours = "C"
            if ours in used:
                ours = letter if letter not in used else letter + str(len(used))
            used.add(ours)
            self._lead.append((letter, ours, n))
        if len(self._series) > 1 and "M" not in used:
            self.axes["M"] = len(self._series)
        for letter, ours, n in self._lead:
            if n > 1:
                self.axes[ours] = n
        self.height = shape[axes_str.index("Y")]
        self.width = shape[axes_str.index("X")]
        if self.rgb and self.dtype != np.uint8:
            self.rgb = False
        self.scientific = not self.rgb

        # Page-based lazy access when every page is one YX(S) plane.
        self._page_mode = False
        self._full = {}
        try:
            p0 = s0.pages[0]
            page_axes = p0.axes
            lead_n = int(np.prod([n for _, _, n in self._lead])) if self._lead else 1
            if axes_str.endswith(page_axes) and page_axes in ("YX", "YXS") and len(s0.pages) == lead_n:
                self._page_mode = True
            if page_axes == "SYX" and self.rgb and len(s0.pages) == lead_n:
                self._page_mode = True
        except Exception:
            self._page_mode = False
        self._axes_str = axes_str

        self._read_channel_meta()
        self.ensure_channels()
        try:
            self._read_tiff_meta()
        except Exception:
            pass
        self.finish_meta()
        self.init_current()

    def _read_tiff_meta(self):
        tf = self._tf
        ome = tf.ome_metadata
        if ome:
            import xml.etree.ElementTree as ET

            root = ET.fromstring(ome)
            images = root.findall("{*}Image")
            many = len(self._series) > 1 and "M" in self.axes
            for si, img in enumerate(images[: len(self._series)] if many else images[:1]):
                if img.get("Name") and many:
                    self.position_names[si] = img.get("Name")
                pix = img.find("{*}Pixels")
                if pix is None:
                    continue
                if si == 0:
                    self.pixel_size = to_um(pix.get("PhysicalSizeX"), pix.get("PhysicalSizeXUnit"))
                    if "Z" in self.axes:
                        self.z_step = to_um(pix.get("PhysicalSizeZ"), pix.get("PhysicalSizeZUnit"))
                    ti = pix.get("TimeIncrement")
                    if ti:
                        self.interval_s = to_s(ti, pix.get("TimeIncrementUnit"))
                    ad = img.find("{*}AcquisitionDate")
                    if ad is not None and ad.text:
                        self.meta["Acquired"] = ad.text
                for pl in pix.findall("{*}Plane"):
                    t, z = int(pl.get("TheT", 0)), int(pl.get("TheZ", 0))
                    if pl.get("DeltaT") is not None and int(pl.get("TheC", 0)) == 0:
                        self._times[(t, si, z)] = to_s(pl.get("DeltaT"), pl.get("DeltaTUnit"))
            obj = root.find(".//{*}Objective")
            if obj is not None:
                if obj.get("Model"):
                    self.meta["Objective"] = obj.get("Model")
                if obj.get("NominalMagnification"):
                    self.meta["Magnification"] = f"{float(obj.get('NominalMagnification')):g}x"
                if obj.get("LensNA"):
                    self.meta["NA"] = obj.get("LensNA")
            if self._times and len({k[0] for k in self._times}) < 2:
                self._times = {}
            return
        ij = tf.imagej_metadata
        if ij:
            unit = str(ij.get("unit", "")).replace("\\u00B5", "\u00b5")
            page = tf.pages[0]
            xr = page.tags.get("XResolution")
            if xr is not None and unit and unit.lower() not in ("pixel", "pixels", "inch", ""):
                num, den = xr.value
                if num:
                    self.pixel_size = to_um(den / num, unit)
            if ij.get("spacing") and "Z" in self.axes:
                self.z_step = to_um(ij["spacing"], unit or "um")
            if ij.get("finterval"):
                self.interval_s = float(ij["finterval"])
            elif ij.get("fps"):
                self.interval_s = 1.0 / float(ij["fps"])

    def _read_channel_meta(self):
        n = self.axes.get("C", 0)
        if not n:
            return
        try:
            ome = self._tf.ome_metadata
            if ome:
                chans = re.findall(r"<(?:\w+:)?Channel\b([^>]*)>", ome)[:n]
                for i, attrs in enumerate(chans):
                    nm = re.search(r'\bName="([^"]*)"', attrs)
                    co = re.search(r'\bColor="(-?\d+)"', attrs)
                    col = _int_to_rgb(int(co.group(1))) if co else DEFAULT_COLORS[i % len(DEFAULT_COLORS)]
                    if col in ((255, 255, 255),) and n > 1:
                        col = DEFAULT_COLORS[i % len(DEFAULT_COLORS)]
                    self.channels.append(Channel(nm.group(1) if nm and nm.group(1) else f"C{i + 1}", col))
                return
            ij = self._tf.imagej_metadata
            if ij and "LUTs" in ij:
                for i, lut in enumerate(ij["LUTs"][:n]):
                    lut = np.asarray(lut)
                    col = tuple(int(x) for x in lut[:, -1][:3])
                    self.channels.append(Channel(f"C{i + 1}", col))
            if ij and ij.get("Labels"):
                pass
        except Exception:
            self.channels = []

    def _plane(self, idx):
        sidx = idx.get("M", 0) if (len(self._series) > 1 and "M" in self.axes and
                                   "M" not in [o for _, o, _ in self._lead]) else 0
        s = self._series[sidx]
        lead_idx = tuple(idx.get(o, 0) if n > 1 else 0 for _, o, n in self._lead)
        if self._page_mode:
            lead_shape = tuple(n for _, _, n in self._lead)
            k = int(np.ravel_multi_index(lead_idx, lead_shape)) if lead_shape else 0
            arr = s.pages[k].asarray()
            if arr.ndim == 3 and arr.shape[0] in (3, 4) and self.rgb and arr.shape[-1] not in (3, 4):
                arr = np.moveaxis(arr, 0, -1)
            return arr
        if sidx not in self._full:
            try:
                self._full[sidx] = s.asarray(out="memmap")
            except Exception:
                self._full[sidx] = s.asarray()
        data = self._full[sidx]
        key = []
        li = 0
        for letter in self._axes_str:
            if letter in ("Y", "X"):
                key.append(slice(None))
            elif letter == "S" and self._sample_axis:
                key.append(slice(None))
            else:
                key.append(lead_idx[li])
                li += 1
        arr = np.asarray(data[tuple(key)])
        if self.rgb and arr.ndim == 3 and arr.shape[0] in (3, 4) and arr.shape[-1] not in (3, 4):
            arr = np.moveaxis(arr, 0, -1)
        return arr

    def close(self):
        try:
            self._tf.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Raster images via Pillow (incl. animated GIF / WebP / APNG frames -> T)
# ---------------------------------------------------------------------------
LOSSY_PHOTO_EXT = {".heic", ".heif", ".jpg", ".jpeg", ".jpe", ".jfif", ".avif"}


class PilSource(Source):
    kind = "image"

    def __init__(self, path):
        super().__init__(path)
        from PIL import Image

        _register_pillow_plugins()
        self._im = Image.open(path)
        n = getattr(self._im, "n_frames", 1) or 1
        if n > 1:
            self.axes["T"] = n
            dur = self._im.info.get("duration")
            if dur:
                self.fps = round(1000.0 / max(dur, 10), 3)
        self.width, self.height = self._im.size
        # photos: keep the camera metadata + colour profile for conversions, and report the upright size
        self.photo_meta = {}
        self.lossy_photo = os.path.splitext(path)[1].lower() in LOSSY_PHOTO_EXT
        try:
            icc = self._im.info.get("icc_profile")
            if icc:
                self.photo_meta["icc_profile"] = icc
            ex = self._im.getexif()
            if ex:
                if ex.get(0x0112, 1) in (5, 6, 7, 8) and n == 1:
                    self.width, self.height = self.height, self.width
                ex[0x0112] = 1          # pixels are written upright, so the orientation tag is reset
                self.photo_meta["exif"] = ex.tobytes()
        except Exception:
            pass
        mode = self._im.mode
        if mode in ("I;16", "I;16B", "I;16L", "I", "F"):
            self.dtype = np.dtype(np.uint16 if mode.startswith("I;16") else (np.int32 if mode == "I" else np.float32))
            self.scientific = True
        elif mode == "L":
            self.dtype = np.dtype(np.uint8)
        else:
            self.rgb = True
        self.finish_meta()
        self.init_current()

    def _plane(self, idx):
        from PIL import ImageOps

        im = self._im
        if "T" in self.axes:
            im.seek(idx.get("T", 0))
        if idx.get("T", 0) == 0 and not self.axes:
            try:
                im = ImageOps.exif_transpose(im)
            except Exception:
                pass
        if not self.rgb:
            if im.mode.startswith("I;16"):
                return np.array(im).astype(np.uint16)
            return np.array(im)
        has_alpha = im.mode in ("RGBA", "LA", "PA") or "transparency" in im.info
        return np.array(im.convert("RGBA" if has_alpha else "RGB"))


_PLUGINS_DONE = False


def _register_pillow_plugins():
    global _PLUGINS_DONE
    if _PLUGINS_DONE:
        return
    _PLUGINS_DONE = True
    try:
        import pillow_heif

        pillow_heif.register_heif_opener()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# SVG (rendered by Qt's SVG engine)
# ---------------------------------------------------------------------------
class SvgSource(Source):
    kind = "vector"

    def __init__(self, path):
        super().__init__(path)
        from PySide6.QtCore import QByteArray
        from PySide6.QtSvg import QSvgRenderer

        with open(path, "rb") as fh:
            self._data = fh.read()
        r = QSvgRenderer(QByteArray(self._data))
        if not r.isValid():
            raise ValueError("Not a valid SVG file")
        sz = r.defaultSize()
        vb = r.viewBoxF()
        w, h = sz.width(), sz.height()
        if w <= 0 or h <= 0:
            w, h = int(vb.width()) or 512, int(vb.height()) or 512
        self._base = (max(1, w), max(1, h))
        self.rgb = True
        self._update_size()
        self.finish_meta()
        self.init_current()

    def _update_size(self):
        self.width = max(1, round(self._base[0] * self.render_scale))
        self.height = max(1, round(self._base[1] * self.render_scale))

    def set_scale(self, s):
        self.render_scale = float(s)
        self._update_size()

    def _plane(self, idx):
        from PySide6.QtCore import QByteArray, QRectF, Qt
        from PySide6.QtGui import QImage, QPainter
        from PySide6.QtSvg import QSvgRenderer

        self._update_size()
        img = QImage(self.width, self.height, QImage.Format_RGBA8888)
        img.fill(Qt.transparent)
        r = QSvgRenderer(QByteArray(self._data))
        r.setAspectRatioMode(Qt.KeepAspectRatio)
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        r.render(p, QRectF(0, 0, self.width, self.height))
        p.end()
        ptr = img.constBits()
        arr = np.frombuffer(ptr, np.uint8, count=img.sizeInBytes()).reshape(self.height, img.bytesPerLine())
        arr = arr[:, : self.width * 4].reshape(self.height, self.width, 4)
        return arr.copy()


# ---------------------------------------------------------------------------
# PDF pages (pdfium)
# ---------------------------------------------------------------------------
class PdfSource(Source):
    kind = "pdf"

    def __init__(self, path):
        super().__init__(path)
        import pypdfium2 as pdfium

        with _PDFIUM_LOCK:
            self._doc = pdfium.PdfDocument(path)
            n = len(self._doc)
            w, h = self._doc[0].get_size()
        if n > 1:
            self.axes["P"] = n
        self._pt = (w, h)
        self.rgb = True
        self._update_size()
        self.finish_meta()
        self.init_current()

    def _update_size(self):
        s = self.pdf_dpi / 72.0
        self.width, self.height = round(self._pt[0] * s), round(self._pt[1] * s)

    def set_dpi(self, dpi):
        self.pdf_dpi = float(dpi)
        self._update_size()

    def _plane(self, idx):
        with _PDFIUM_LOCK:
            page = self._doc[idx.get("P", 0)]
            bmp = page.render(scale=self.pdf_dpi / 72.0)
            return np.array(bmp.to_pil().convert("RGB"))

    def close(self):
        with _PDFIUM_LOCK:
            try:
                self._doc.close()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Video (ffmpeg)
# ---------------------------------------------------------------------------
class VideoSource(Source):
    kind = "video"

    def __init__(self, path):
        super().__init__(path)
        import imageio.v2 as iio

        self._r = iio.get_reader(path, "ffmpeg")
        meta = self._r.get_meta_data()
        self.fps = meta.get("fps") or None
        self.width, self.height = meta.get("size", (0, 0))
        try:
            n = self._r.count_frames()
        except Exception:
            n = int(round((meta.get("duration") or 0) * (self.fps or 0))) or 1
        if n > 1:
            self.axes["T"] = n
        self.rgb = True
        self.finish_meta()
        self.init_current()

    def _plane(self, idx):
        return np.asarray(self._r.get_data(idx.get("T", 0)))[..., :3]

    def close(self):
        try:
            self._r.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
def open_source(path: str) -> Source:
    ext = file_ext(path)
    if ext in SCI_EXT:
        return ND2Source(path)
    if ext in TIFF_EXT:
        try:
            return TiffSource(path)
        except Exception:
            return PilSource(path)
    if ext in SVG_EXT:
        return SvgSource(path)
    if ext in PDF_EXT:
        return PdfSource(path)
    if ext in VIDEO_EXT:
        return VideoSource(path)
    return PilSource(path)


def is_supported(path: str) -> bool:
    return file_ext(path) in SUPPORTED_EXT
