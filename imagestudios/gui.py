"""ImageStudios main window (PySide6)."""
from __future__ import annotations

import copy
import dataclasses
import json
import os
import sys
import time
import traceback

import numpy as np
from PySide6.QtCore import QEvent, QObject, QSettings, QSize, QStandardPaths, Qt, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import (QAction, QBrush, QColor, QDesktopServices, QIcon, QImage, QKeySequence,
                           QLinearGradient, QPainter, QPainterPath, QPalette, QPixmap)
from PySide6.QtWidgets import (QStackedWidget, QAbstractItemView, QAbstractScrollArea, QAbstractSpinBox, QApplication, QCheckBox, QColorDialog, QComboBox,
                               QDoubleSpinBox, QFileDialog, QFormLayout, QFrame, QGridLayout, QGroupBox,
                               QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem,
                               QMainWindow, QMessageBox, QProgressBar, QPushButton, QScrollArea, QSlider,
                               QSpinBox, QSplitter, QStyle, QToolBar, QToolButton, QDialog,
                               QDialogButtonBox, QPlainTextEdit,
                               QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget, QSizePolicy)

from . import __version__

try:  # the live HTML preview needs Qt WebEngine (optional)
    from PySide6.QtWebEngineCore import QWebEngineSettings
    from PySide6.QtWebEngineWidgets import QWebEngineView
except Exception:  # pragma: no cover
    QWebEngineView = None
from .annotate import CORNERS, TIME_FORMATS, Annot
from .export import Cancelled, render_unit, run_job
from .plan import (FORMATS, HTML_PRESETS, HTML_TOOLS, MODE_TIPS, MODES, OUTPUTS, PANEL_FILL, HtmlOpts, Recipe,
                   build_plan, preview_unit)
from .plan import parse_selection as parse_sel
from .render import CONTRAST_MODES, render
from .sources import (PdfSource, SUPPORTED_EXT, SvgSource, axis_label, is_supported, open_source,
                      ordered_axes)

ACCENT = "#6c8cff"


# ---------------------------------------------------------------------------
def to_qimage(arr: np.ndarray) -> QImage:
    arr = np.ascontiguousarray(arr)
    h, w = arr.shape[:2]
    if arr.ndim == 2:
        return QImage(arr.data, w, h, w, QImage.Format_Grayscale8).copy()
    if arr.shape[2] == 4:
        return QImage(arr.data, w, h, w * 4, QImage.Format_RGBA8888).copy()
    return QImage(arr.data, w, h, w * 3, QImage.Format_RGB888).copy()


def pil_to_qimage(im) -> QImage:
    if im.mode not in ("RGB", "RGBA"):
        im = im.convert("RGB")
    return to_qimage(np.asarray(im))


def default_export_dir() -> str:
    pics = QStandardPaths.writableLocation(QStandardPaths.PicturesLocation) or os.path.expanduser("~")
    return os.path.join(pics, "ImageStudios")


def _corner_combo(value, on_change):
    c = QComboBox()
    for k, v in CORNERS.items():
        c.addItem(v, k)
    c.setCurrentIndex(max(0, c.findData(value)))
    c.currentIndexChanged.connect(on_change)
    return c


class WheelGuard(QObject):
    """Mouse-wheel never changes dropdowns, number boxes or sliders: the wheel
    scrolls the surrounding panel instead."""

    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.Wheel and isinstance(obj, (QComboBox, QAbstractSpinBox, QSlider)):
            p = obj.parentWidget()
            while p is not None and not isinstance(p, QAbstractScrollArea):
                p = p.parentWidget()
            if p is not None:
                QApplication.sendEvent(p.viewport(), ev)
            return True
        return False


def app_icon() -> QIcon:
    pm = QPixmap(256, 256)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    g = QLinearGradient(0, 0, 256, 256)
    g.setColorAt(0, QColor("#7b5cff"))
    g.setColorAt(1, QColor("#21c3c9"))
    path = QPainterPath()
    path.addRoundedRect(8, 8, 240, 240, 56, 56)
    p.fillPath(path, QBrush(g))
    p.setPen(Qt.NoPen)
    for i, (x, y, c) in enumerate([(60, 60, "#ffffff"), (100, 100, "#ffffffcc"), (140, 140, "#ffffff88")]):
        p.setBrush(QColor(c))
        p.drawRoundedRect(x - 6, y - 6, 70, 70, 14, 14)
    p.end()
    return QIcon(pm)


class PreviewView(QWidget):
    def __init__(self):
        super().__init__()
        self._img: QImage | None = None
        self._msg = "Drop files here\n\nND2 · TIFF / OME-TIFF · SVG · PDF · PNG · JPEG · GIF · WebP · HEIC · MP4 …"
        self.setMinimumSize(320, 240)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._checker = self._make_checker()

    @staticmethod
    def _make_checker():
        pm = QPixmap(16, 16)
        pm.fill(QColor("#3a3d46"))
        p = QPainter(pm)
        p.fillRect(0, 0, 8, 8, QColor("#2e3038"))
        p.fillRect(8, 8, 8, 8, QColor("#2e3038"))
        p.end()
        return pm

    def set_image(self, img: QImage | None, msg: str = ""):
        self._img = img
        if msg:
            self._msg = msg
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#16171c"))
        if self._img is None or self._img.isNull():
            p.setPen(QColor("#7f8494"))
            p.drawText(self.rect(), Qt.AlignCenter, self._msg)
            return
        iw, ih = self._img.width(), self._img.height()
        r = self.rect().adjusted(10, 10, -10, -10)
        s = min(r.width() / iw, r.height() / ih)
        w, h = max(1, int(iw * s)), max(1, int(ih * s))
        x, y = r.x() + (r.width() - w) // 2, r.y() + (r.height() - h) // 2
        if self._img.hasAlphaChannel():
            p.fillRect(x, y, w, h, QBrush(self._checker))
        p.setRenderHint(QPainter.SmoothPixmapTransform, s < 1)
        p.drawImage(QRectF_(x, y, w, h), self._img)
        p.setPen(QColor("#7f8494"))
        p.drawText(self.rect().adjusted(12, 0, -12, -4), Qt.AlignBottom | Qt.AlignRight,
                   f"{iw}×{ih}  ·  {s * 100:.0f}%")


def QRectF_(x, y, w, h):
    from PySide6.QtCore import QRectF
    return QRectF(x, y, w, h)


# ---------------------------------------------------------------------------
class HtmlPreviewWorker(QObject):
    done = Signal(int, str, str)       # generation, path, error

    def __init__(self, gen, job, recipe, cache):
        super().__init__()
        self.gen, self.job, self.recipe, self.cache = gen, job, recipe, cache

    def run(self):
        from .html_export import write_html

        try:
            write_html(self.job, self.recipe, preview={"cache": self.cache})
            self.done.emit(self.gen, self.job.out_path, "")
        except Exception as ex:
            traceback.print_exc()
            self.done.emit(self.gen, self.job.out_path, str(ex))


class ExportWorker(QObject):
    progress = Signal(int, int, str)
    finished = Signal(int, list, bool, float)

    def __init__(self, jobs, recipe):
        super().__init__()
        self.jobs = jobs
        self.recipe = recipe
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        total = sum(len(j.frames) for j in self.jobs)
        done = [0]
        ok, errors = 0, []
        t0 = time.time()
        cur = [""]

        def tick():
            done[0] += 1
            self.progress.emit(done[0], total, cur[0])

        for j in self.jobs:
            if self._cancel:
                break
            cur[0] = os.path.basename(j.out_path)
            self.progress.emit(done[0], total, cur[0])
            before = done[0]
            try:
                run_job(j, self.recipe, tick, lambda: self._cancel)
                ok += 1
            except Cancelled:
                try:
                    os.remove(j.out_path)
                except OSError:
                    pass
                break
            except Exception as ex:
                errors.append(f"{cur[0]}: {ex}")
                traceback.print_exc()
                done[0] = before + len(j.frames)
        self.finished.emit(ok, errors, self._cancel, time.time() - t0)


# ---------------------------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ImageStudios")
        self.setWindowIcon(app_icon())
        self.resize(1480, 900)
        self.setAcceptDrops(True)
        self.settings = QSettings("ImageStudios", "ImageStudios")
        self.sources = []
        self.recipe = Recipe()
        self._load_settings()
        self.jobs = []
        self._thread = None
        self._worker = None
        self._play_axis = None
        self._play_timer = QTimer(self, timeout=self._play_step)
        self._plan_timer = QTimer(self, singleShot=True, interval=200, timeout=self.refresh_plan)
        self._building_axes = False

        self._build_ui()
        self._sync_recipe_to_ui()
        self.refresh_axes_table()
        self.refresh_plan()

    # ---------------- UI construction ----------------
    def _build_ui(self):
        tb = QToolBar("Main")
        tb.setMovable(False)
        tb.setIconSize(QSize(18, 18))
        tb.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.addToolBar(tb)
        st = self.style()
        a_add = QAction(st.standardIcon(QStyle.SP_FileIcon), "Add files…", self, shortcut=QKeySequence.Open,
                        triggered=self.add_files_dialog)
        a_dir = QAction(st.standardIcon(QStyle.SP_DirOpenIcon), "Add folder…", self, triggered=self.add_folder_dialog)
        a_rm = QAction(st.standardIcon(QStyle.SP_TrashIcon), "Remove", self, shortcut=QKeySequence.Delete,
                       triggered=self.remove_selected)
        a_clear = QAction("Clear all", self, triggered=self.clear_all)
        for a in (a_add, a_dir, a_rm, a_clear):
            tb.addAction(a)
        self.act_remove, self.act_clear = a_rm, a_clear
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        tb.addWidget(spacer)
        title = QLabel("  ImageStudios  ")
        title.setStyleSheet("font-weight:600; font-size:15px; color:#cfd6ff;")
        tb.addWidget(title)

        # Left: file list
        self.file_list = QListWidget()
        self.file_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.file_list.setDragDropMode(QAbstractItemView.InternalMove)
        self.file_list.setIconSize(QSize(56, 56))
        self.file_list.setSpacing(2)
        self.file_list.currentItemChanged.connect(lambda *_: self.on_select())
        self.file_list.model().rowsMoved.connect(self._on_rows_moved)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(8, 8, 4, 8)
        self.files_label = QLabel("Files")
        self.files_label.setObjectName("h")
        ll.addWidget(self.files_label)
        ll.addWidget(self.file_list, 1)
        hint = QLabel("Drag to reorder (order is used for combined PDFs / animations).")
        hint.setWordWrap(True)
        hint.setObjectName("hint")
        ll.addWidget(hint)

        # Center: preview
        center = QWidget()
        cl = QVBoxLayout(center)
        cl.setContentsMargins(4, 8, 4, 8)
        self.preview = PreviewView()
        self.preview_stack = QStackedWidget()
        self.preview_stack.addWidget(self.preview)
        self.web_box = QWidget()
        wl = QVBoxLayout(self.web_box)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.setSpacing(2)
        self.web_status = QLabel("")
        self.web_status.setObjectName("hint")
        wl.addWidget(self.web_status)
        self.web = None
        if QWebEngineView is not None:
            self.web = QWebEngineView()
            st_ = self.web.settings()
            st_.setAttribute(QWebEngineSettings.LocalContentCanAccessFileUrls, True)
            st_.setAttribute(QWebEngineSettings.LocalContentCanAccessRemoteUrls, False)
            wl.addWidget(self.web, 1)
        else:
            msg = QLabel("The live HTML preview needs Qt WebEngine, which isn't available in this installation.")
            msg.setWordWrap(True)
            wl.addWidget(msg, 1)
        self.preview_stack.addWidget(self.web_box)
        cl.addWidget(self.preview_stack, 1)
        self._html_cache = {}
        self._html_gen = 0
        self._html_busy = False
        self._html_pending = False
        self._html_thread = None
        self._html_flip = 0
        self._html_timer = QTimer(self, singleShot=True, interval=350, timeout=self._build_html_preview)
        self.info_label = QLabel("")
        self.info_label.setObjectName("hint")
        cl.addWidget(self.info_label)
        self.axes_box = QWidget()
        self.axes_layout = QGridLayout(self.axes_box)
        self.axes_layout.setContentsMargins(0, 0, 0, 0)
        cl.addWidget(self.axes_box)
        self.chan_box = QWidget()
        self.chan_layout = QHBoxLayout(self.chan_box)
        self.chan_layout.setContentsMargins(0, 0, 0, 0)
        cl.addWidget(self.chan_box)
        disp_row = QHBoxLayout()
        disp_row.addWidget(QLabel("Contrast"))
        self.contrast_combo = QComboBox()
        for k, v in CONTRAST_MODES.items():
            self.contrast_combo.addItem(v, k)
        self.contrast_combo.currentIndexChanged.connect(self._on_display_changed)
        disp_row.addWidget(self.contrast_combo)
        disp_row.addWidget(QLabel("Saturate %"))
        self.sat_spin = QDoubleSpinBox(decimals=2, minimum=0.0, maximum=20.0, singleStep=0.1, value=0.1)
        self.sat_spin.valueChanged.connect(self._on_display_changed)
        disp_row.addWidget(self.sat_spin)
        self.gray_single = QCheckBox("Single channels in grayscale")
        self.gray_single.setChecked(True)
        self.gray_single.toggled.connect(self._on_display_changed)
        disp_row.addWidget(self.gray_single)
        disp_row.addStretch(1)
        self.preview_out_chk = QCheckBox("Preview output (annotations / panel)")
        self.preview_out_chk.setChecked(True)
        self.preview_out_chk.toggled.connect(lambda *_: self.update_preview())
        disp_row.addWidget(self.preview_out_chk)
        cl.addLayout(disp_row)

        meta_row = QHBoxLayout()
        meta_row.addWidget(QLabel("Pixel size"))
        self.px_spin = QDoubleSpinBox(decimals=4, minimum=0.0, maximum=100000.0, singleStep=0.01)
        self.px_spin.setSpecialValueText("unknown")
        self.px_spin.setSuffix(" \u00b5m/px")
        self.px_spin.setToolTip("Physical pixel size, read from the file's metadata. Used by the scale bar.")
        meta_row.addWidget(self.px_spin)
        meta_row.addWidget(QLabel("Frame interval"))
        self.int_spin = QDoubleSpinBox(decimals=3, minimum=0.0, maximum=10_000_000.0, singleStep=1.0)
        self.int_spin.setSpecialValueText("unknown")
        self.int_spin.setSuffix(" s")
        self.int_spin.setToolTip("Time between T frames. Per-frame timestamps from the metadata are used unless you "
                                 "change this value.")
        meta_row.addWidget(self.int_spin)
        meta_row.addWidget(QLabel("Z step"))
        self.zstep_spin = QDoubleSpinBox(decimals=3, minimum=0.0, maximum=100000.0, singleStep=0.1)
        self.zstep_spin.setSpecialValueText("unknown")
        self.zstep_spin.setSuffix(" \u00b5m")
        meta_row.addWidget(self.zstep_spin)
        for w in (self.px_spin, self.int_spin, self.zstep_spin):
            w.valueChanged.connect(self._on_meta_edited)
        self.meta_reset_btn = QPushButton("Reset")
        self.meta_reset_btn.setToolTip("Restore the values read from the file")
        self.meta_reset_btn.clicked.connect(self._reset_meta)
        meta_row.addWidget(self.meta_reset_btn)
        self.meta_btn = QPushButton("Metadata\u2026")
        self.meta_btn.clicked.connect(self._show_metadata)
        meta_row.addWidget(self.meta_btn)
        meta_row.addStretch(1)
        self.meta_box = QWidget()
        self.meta_box.setLayout(meta_row)
        meta_row.setContentsMargins(0, 0, 0, 0)
        cl.addWidget(self.meta_box)
        self._meta_updating = False

        # Right: settings
        right_inner = QWidget()
        rl = QVBoxLayout(right_inner)
        rl.setContentsMargins(4, 8, 8, 8)

        g_out = QGroupBox("Output")
        fo = QFormLayout(g_out)
        self.fo = fo
        self.out_combo = QComboBox()
        for k, v in OUTPUTS.items():
            self.out_combo.addItem(v, k)
        self.out_combo.currentIndexChanged.connect(self._on_output_changed)
        self.fmt_combo = QComboBox()
        self.fmt_combo.currentIndexChanged.connect(self._on_settings_changed)
        fo.addRow("Make", self.out_combo)
        fo.addRow("Format", self.fmt_combo)
        self.fmt_hint = QLabel("")
        self.fmt_hint.setWordWrap(True)
        self.fmt_hint.setObjectName("hint")
        fo.addRow(self.fmt_hint)
        self.combine_chk = QCheckBox("Combine all files into one output")
        self.combine_chk.setToolTip("Chain every loaded file (in list order) into a single PDF or animation.")
        self.combine_chk.toggled.connect(self._on_settings_changed)
        fo.addRow(self.combine_chk)
        rl.addWidget(g_out)

        g_axes = QGroupBox("Axes  (T time · M position · Z slice · C channel · P page)")
        al = QVBoxLayout(g_axes)
        self.axes_grid_host = QWidget()
        self.axes_grid = QGridLayout(self.axes_grid_host)
        self.axes_grid.setContentsMargins(0, 0, 0, 0)
        self.axes_grid.setHorizontalSpacing(6)
        self.axes_grid.setVerticalSpacing(4)
        self.axes_grid.setColumnStretch(1, 3)
        self.axes_grid.setColumnStretch(2, 2)
        al.addWidget(self.axes_grid_host)
        tip = QLabel("Range examples: all · current · 1-10 · 1-50:5 · 3, 7, 9 · last. "
                     "“current” uses the slider position of each file.")
        tip.setWordWrap(True)
        tip.setObjectName("hint")
        al.addWidget(tip)
        rl.addWidget(g_axes)

        g_name = QGroupBox("File names")
        fn = QFormLayout(g_name)
        self.fn = fn
        self.tpl_edit = QLineEdit()
        self.tpl_edit.setPlaceholderText("{name}{auto}")
        self.tpl_edit.textChanged.connect(self._on_settings_changed)
        fn.addRow("Template", self.tpl_edit)
        tok = QLabel("Tokens: {name} {auto} {t} {m} {z} {c} {p} {i} {cname}")
        tok.setObjectName("hint")
        tok.setTextInteractionFlags(Qt.TextSelectableByMouse)
        fn.addRow(tok)
        self.onebased_chk = QCheckBox("Number from 1 (unchecked: from 0)")
        self.onebased_chk.toggled.connect(self._on_settings_changed)
        fn.addRow(self.onebased_chk)
        self.combined_edit = QLineEdit()
        self.combined_edit.textChanged.connect(self._on_settings_changed)
        fn.addRow("Combined name", self.combined_edit)
        rl.addWidget(g_name)

        g_anim = QGroupBox("Animation")
        fa = QFormLayout(g_anim)
        self.fa = fa
        row = QHBoxLayout()
        self.fps_spin = QDoubleSpinBox(decimals=2, minimum=0.1, maximum=240.0, singleStep=1.0)
        self.fps_spin.setSuffix(" fps")
        self.fps_spin.valueChanged.connect(self._on_settings_changed)
        row.addWidget(self.fps_spin)
        self.native_fps_btn = QPushButton("Use file's rate")
        self.native_fps_btn.clicked.connect(self._use_native_fps)
        row.addWidget(self.native_fps_btn)
        fa.addRow("Frame rate", row)
        self.loop_chk = QCheckBox("Loop forever (GIF / WebP)")
        self.loop_chk.toggled.connect(self._on_settings_changed)
        fa.addRow(self.loop_chk)
        self.anim_group = g_anim
        rl.addWidget(g_anim)

        g_q = QGroupBox("Quality & size")
        fq = QFormLayout(g_q)
        self.fq = fq
        self.q_group = g_q
        self.quality_spin = QSpinBox(minimum=1, maximum=100)
        self.quality_spin.setToolTip("JPEG / WebP / MP4 / PDF quality. 100 = lossless WebP.")
        self.quality_spin.valueChanged.connect(self._on_settings_changed)
        fq.addRow("Quality", self.quality_spin)
        srow = QHBoxLayout()
        self.scale_mode = QComboBox()
        self.scale_mode.addItem("Automatic", "auto")
        self.scale_mode.addItem("Manual", "manual")
        self.scale_mode.setToolTip("Automatic enlarges small microscope images by whole-number factors (crisp pixels)\n"
                                   "and keeps large panels within 4096 px. Manual uses your percentage.")
        self.scale_mode.currentIndexChanged.connect(self._on_settings_changed)
        srow.addWidget(self.scale_mode)
        self.scale_spin = QDoubleSpinBox(decimals=0, minimum=1, maximum=3200, singleStep=25)
        self.scale_spin.setSuffix(" %")
        self.scale_spin.valueChanged.connect(self._on_settings_changed)
        srow.addWidget(self.scale_spin)
        self.scale_info = QLabel("")
        self.scale_info.setObjectName("hint")
        srow.addWidget(self.scale_info, 1)
        self._size_row = fq.rowCount()
        fq.addRow("Image size", srow)
        self.bg_combo = QComboBox()
        for k, v in (("white", "White"), ("black", "Black"), ("transparent", "Keep transparency (PNG/WebP/TIFF)")):
            self.bg_combo.addItem(v, k)
        self.bg_combo.currentIndexChanged.connect(self._on_settings_changed)
        fq.addRow("Background", self.bg_combo)
        self.svg_scale = QDoubleSpinBox(decimals=2, minimum=0.05, maximum=50, singleStep=0.5, value=1.0)
        self.svg_scale.setSuffix(" ×")
        self.svg_scale.valueChanged.connect(self._on_render_res_changed)
        fq.addRow("SVG render scale", self.svg_scale)
        self.pdf_dpi = QSpinBox(minimum=18, maximum=1200, singleStep=25, value=150)
        self.pdf_dpi.setSuffix(" dpi")
        self.pdf_dpi.valueChanged.connect(self._on_render_res_changed)
        fq.addRow("PDF page render", self.pdf_dpi)
        rl.addWidget(g_q)

        self._build_html_group(rl)
        self._build_annot_group(rl)
        self._build_panel_group(rl)

        g_dst = QGroupBox("Export folder")
        fd = QVBoxLayout(g_dst)
        drow = QHBoxLayout()
        self.dir_edit = QLineEdit()
        self.dir_edit.setPlaceholderText("Folder where ImageStudios saves everything")
        self.dir_edit.textChanged.connect(self._on_settings_changed)
        drow.addWidget(self.dir_edit, 1)
        b = QPushButton("Browse…")
        b.clicked.connect(self._browse_dir)
        drow.addWidget(b)
        fd.addLayout(drow)
        self.beside_chk = QCheckBox("Save next to each source file instead of the export folder")
        self.beside_chk.toggled.connect(self._on_settings_changed)
        fd.addWidget(self.beside_chk)
        self.sub_chk = QCheckBox("Put each file's outputs in its own subfolder")
        self.sub_chk.toggled.connect(self._on_settings_changed)
        fd.addWidget(self.sub_chk)
        rl.addWidget(g_dst)
        rl.addStretch(1)

        right = QScrollArea()
        right.setWidgetResizable(True)
        right.setWidget(right_inner)
        right.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        right_inner.adjustSize()
        side_w = max(440, right_inner.minimumSizeHint().width() + right.verticalScrollBar().sizeHint().width() + 8)
        right.setMinimumWidth(side_w)
        right.setMaximumWidth(side_w + 160)
        right.setFrameShape(QFrame.NoFrame)
        self.right_panel = right_inner

        top = QSplitter(Qt.Horizontal)
        top.addWidget(left)
        top.addWidget(center)
        top.addWidget(right)
        top.setSizes([300, 760, side_w])
        top.setCollapsible(0, False)
        top.setCollapsible(1, False)
        top.setCollapsible(2, False)
        top.setStretchFactor(1, 1)

        # Bottom: plan
        bottom = QWidget()
        bl = QVBoxLayout(bottom)
        bl.setContentsMargins(8, 4, 8, 8)
        hrow = QHBoxLayout()
        self.plan_label = QLabel("Proposed batch")
        self.plan_label.setObjectName("h")
        hrow.addWidget(self.plan_label, 1)
        self.dest_label = QLabel("")
        self.dest_label.setObjectName("hint")
        self.dest_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        hrow.addWidget(self.dest_label)
        self.change_dir_btn = QPushButton("Change\u2026")
        self.change_dir_btn.setToolTip("Choose the folder ImageStudios exports into")
        self.change_dir_btn.clicked.connect(self._browse_dir)
        hrow.addWidget(self.change_dir_btn)
        self.open_out_btn = QPushButton("Open")
        self.open_out_btn.setToolTip("Open the export folder")
        self.open_out_btn.clicked.connect(self._open_out_dir)
        hrow.addWidget(self.open_out_btn)
        self.export_btn = QPushButton("Export")
        self.export_btn.setObjectName("primary")
        self.export_btn.clicked.connect(self.start_export)
        hrow.addWidget(self.export_btn)
        bl.addLayout(hrow)
        self.plan_tree = QTreeWidget()
        self.plan_tree.setHeaderLabels(["Output file", "Frames", "From", "Folder"])
        self.plan_tree.setRootIsDecorated(False)
        self.plan_tree.setUniformRowHeights(True)
        self.plan_tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.plan_tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.plan_tree.header().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.plan_tree.header().setSectionResizeMode(3, QHeaderView.Interactive)
        bl.addWidget(self.plan_tree, 1)
        self.warn_label = QLabel("")
        self.warn_label.setObjectName("warn")
        self.warn_label.setWordWrap(True)
        self.warn_label.hide()
        bl.addWidget(self.warn_label)
        prow = QHBoxLayout()
        self.progress = QProgressBar()
        self.progress.setTextVisible(True)
        self.progress.hide()
        prow.addWidget(self.progress, 1)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.hide()
        self.cancel_btn.clicked.connect(self.cancel_export)
        prow.addWidget(self.cancel_btn)
        bl.addLayout(prow)

        vs = QSplitter(Qt.Vertical)
        vs.addWidget(top)
        vs.addWidget(bottom)
        vs.setSizes([640, 260])
        vs.setStretchFactor(0, 1)
        self.setCentralWidget(vs)
        self.statusBar().showMessage(f"ImageStudios {__version__} — add or drop files to begin")

    # ---------------- settings persistence ----------------
    def _load_settings(self):
        s, r = self.settings, self.recipe
        r.output = s.value("output", r.output)
        if r.output not in OUTPUTS:
            r.output = "images"
        r.fmt = s.value("fmt", r.fmt)
        if r.fmt not in FORMATS[r.output]:
            r.fmt = next(iter(FORMATS[r.output]))
        r.out_dir = s.value("out_dir", "") or default_export_dir()
        r.fps = float(s.value("fps", 10.0))
        r.quality = int(s.value("quality", 90))
        r.one_based = s.value("one_based", "true") in (True, "true")
        r.loop = s.value("loop", "true") in (True, "true")
        r.background = s.value("background", "white")
        r.html_budget_mb = float(s.value("html_budget", r.html_budget_mb))
        try:
            a = json.loads(s.value("annot", "") or "{}")
            fields = {f.name for f in dataclasses.fields(Annot)}
            r.annot = Annot(**{k: v for k, v in a.items() if k in fields})
        except Exception:
            r.annot = Annot()
        try:
            hd = json.loads(s.value("html", "") or "{}")
            fields = {f.name for f in dataclasses.fields(HtmlOpts)}
            r.html = HtmlOpts(**{k: v for k, v in hd.items() if k in fields})
        except Exception:
            r.html = HtmlOpts()
        try:
            pnl = json.loads(s.value("panel", "") or "{}")
            for k in ("panel_axis", "panel_fill", "panel_count", "panel_gap", "panel_bg", "panel_merge", "scale_mode", "scale_pct"):
                if k in pnl:
                    setattr(r, k, pnl[k])
        except Exception:
            pass

    def _save_settings(self):
        s, r = self.settings, self.recipe
        for k in ("output", "fmt", "out_dir", "fps", "quality", "background"):
            s.setValue(k, getattr(r, k))
        s.setValue("one_based", "true" if r.one_based else "false")
        s.setValue("loop", "true" if r.loop else "false")
        s.setValue("annot", json.dumps(dataclasses.asdict(r.annot)))
        s.setValue("html", json.dumps(dataclasses.asdict(r.html)))
        s.setValue("html_budget", r.html_budget_mb)
        s.setValue("panel", json.dumps({k: getattr(r, k) for k in
                                        ("panel_axis", "panel_fill", "panel_count", "panel_gap", "panel_bg", "panel_merge", "scale_mode", "scale_pct")}))

    def _sync_recipe_to_ui(self):
        r = self.recipe
        self._building_axes = True
        self.out_combo.setCurrentIndex(self.out_combo.findData(r.output))
        self._fill_formats()
        self.fmt_combo.setCurrentIndex(max(0, self.fmt_combo.findData(r.fmt)))
        self.tpl_edit.setText(r.template)
        self.onebased_chk.setChecked(r.one_based)
        self.combined_edit.setText(r.combined_name)
        self.fps_spin.setValue(r.fps)
        self.html_fps.setValue(r.fps)
        self.html_budget.setValue(int(r.html_budget_mb))
        self._html_to_ui()
        self.loop_chk.setChecked(r.loop)
        self.quality_spin.setValue(r.quality)
        self.scale_spin.setValue(r.scale_pct)
        self.scale_mode.setCurrentIndex(max(0, self.scale_mode.findData(r.scale_mode)))
        self.bg_combo.setCurrentIndex(max(0, self.bg_combo.findData(r.background)))
        self.dir_edit.setText(r.out_dir)
        self.beside_chk.setChecked(r.beside_source)
        self.sub_chk.setChecked(r.subfolders)
        self.combine_chk.setChecked(r.combine)
        self.contrast_combo.setCurrentIndex(self.contrast_combo.findData(r.display.contrast))
        self._annot_to_ui()
        self._building_axes = False
        self._update_enabled()

    def _fill_formats(self):
        out = self.out_combo.currentData()
        self.fmt_combo.blockSignals(True)
        self.fmt_combo.clear()
        for k, v in FORMATS[out].items():
            self.fmt_combo.addItem(v, k)
        self.fmt_combo.blockSignals(False)

    def _update_enabled(self):
        src = self.current_source()
        self._update_visibility()
        self.dir_edit.setEnabled(not self.recipe.beside_source)
        if self.recipe.beside_source:
            self.dest_label.setText("Saving next to each source file")
        else:
            self.dest_label.setText(f"Export folder: {self.recipe.out_dir or '(not set)'}")
        self.meta_box.setVisible(bool(src and src.kind in ("microscopy", "video", "image")))
        src = self.current_source()
        self.native_fps_btn.setEnabled(bool(src and src.fps))
        self.native_fps_btn.setText(f"Use file's rate ({src.fps:g})" if src and src.fps else "Use file's rate")

    def _update_visibility(self):
        """Only show the settings that the chosen output actually uses."""
        r = self.recipe
        out, fmt = r.output, r.fmt
        raw = out == "images" and fmt == "tif-raw"
        has_svg = any(isinstance(x, SvgSource) for x in self.sources)
        has_pdf_in = any(isinstance(x, PdfSource) for x in self.sources)
        has_alpha = has_svg or any(x.kind == "image" and x.rgb for x in self.sources)
        self.fo.setRowVisible(self.fmt_combo, out != "pdf")
        self.fo.setRowVisible(self.combine_chk, out in ("animation", "pdf"))
        combined = (out in ("animation", "pdf") and r.combine) or r.panel_axis == "F"
        self.fn.setRowVisible(self.combined_edit, combined)
        self.anim_group.setVisible(out == "animation")
        self.fa.setRowVisible(self.loop_chk, fmt in ("gif", "webp"))
        self.annot_group.setVisible(not raw)
        self.panel_group.setVisible(not raw)
        self.fq.setRowVisible(self.quality_spin, fmt in ("jpg", "webp", "mp4") or out == "pdf")
        self.fq.setRowVisible(self.bg_combo, has_alpha and not raw)
        self.fq.setRowVisible(self.svg_scale, has_svg)
        self.fq.setRowVisible(self.pdf_dpi, has_pdf_in)
        i = self.bg_combo.findData("transparent")
        if i >= 0:
            self.bg_combo.view().setRowHidden(i, not (out == "images" and fmt in ("png", "webp", "tif")))
        self.q_group.setTitle("Quality & size" if self.fq.isRowVisible(self.quality_spin) else "Size")
        html_out = out == "html"
        self.html_group.setVisible(html_out)
        self.fo.setRowVisible(self.fmt_combo, out not in ("pdf", "html"))
        photos = [x for x in self.sources if getattr(x, "lossy_photo", False)]
        lossless = out == "images" and fmt in ("png", "tif", "bmp")
        self.fmt_hint.setText(
            f"{fmt.upper()} is lossless: a HEIC/JPEG photo becomes about 3\u20135\u00d7 larger than the original. "
            "JPEG or WebP stay close to the original size (HEIC itself is about 1.5× more compact than JPEG)." if photos and lossless else "")
        self.fo.setRowVisible(self.fmt_hint, bool(photos and lossless))
        if hasattr(self, "pn_grid"):
            self._update_grid_rows()
        if html_out:
            self.annot_group.setVisible(False)
            self.panel_group.setVisible(True)
            self.q_group.setVisible(has_svg or has_pdf_in)
            for row_w in (self.quality_spin, self.bg_combo):
                self.fq.setRowVisible(row_w, False)
            self.fq.setRowVisible(self._size_row, False)
        else:
            self.q_group.setVisible(not raw or has_svg or has_pdf_in)
            self.fq.setRowVisible(self._size_row, not raw)

    # ---------------- recipe <- UI ----------------
    def _on_output_changed(self):
        if self._building_axes:
            return
        out = self.out_combo.currentData()
        self.recipe.output = out
        self._fill_formats()
        self.recipe.fmt = self.fmt_combo.currentData()
        if out == "animation":
            if not any(r.mode == "animate" for r in self.recipe.rules.values()):
                present = set()
                for s in self.sources:
                    present |= set(s.axes)
                for a in ("T", "Z", "P", "I", "M"):
                    if a in present:
                        self.recipe.rule(a).mode = "animate"
                        break
        else:
            for r in self.recipe.rules.values():
                if r.mode == "animate":
                    r.mode = "iterate"
        self.refresh_axes_table()
        self._on_settings_changed()

    def _on_settings_changed(self, *_):
        if self._building_axes:
            return
        r = self.recipe
        r.fmt = self.fmt_combo.currentData() or r.fmt
        r.template = self.tpl_edit.text()
        r.one_based = self.onebased_chk.isChecked()
        r.combined_name = self.combined_edit.text() or "ImageStudios_combined"
        r.fps = self.fps_spin.value()
        r.html_budget_mb = self.html_budget.value()
        if abs(self.html_fps.value() - r.fps) > 1e-9:
            self.html_fps.blockSignals(True)
            self.html_fps.setValue(r.fps)
            self.html_fps.blockSignals(False)
        r.loop = self.loop_chk.isChecked()
        r.quality = self.quality_spin.value()
        r.scale_pct = self.scale_spin.value()
        r.scale_mode = self.scale_mode.currentData() or "auto"
        self.scale_spin.setEnabled(r.scale_mode == "manual")
        self._update_scale_info()
        self.update_preview()
        r.background = self.bg_combo.currentData()
        r.out_dir = self.dir_edit.text().strip()
        r.beside_source = self.beside_chk.isChecked()
        r.subfolders = self.sub_chk.isChecked()
        r.combine = self.combine_chk.isChecked()
        self._update_enabled()
        self._plan_timer.start()

    def _on_display_changed(self, *_):
        d = self.recipe.display
        d.contrast = self.contrast_combo.currentData()
        sat = self.sat_spin.value()
        d.low_pct, d.high_pct = sat, 100.0 - sat
        d.gray_single = self.gray_single.isChecked()
        self.update_preview()

    def _on_render_res_changed(self, *_):
        for s in self.sources:
            if isinstance(s, SvgSource):
                s.set_scale(self.svg_scale.value())
            elif isinstance(s, PdfSource):
                s.set_dpi(self.pdf_dpi.value())
        self._refresh_item_texts()
        self.update_preview()

    def _use_native_fps(self):
        src = self.current_source()
        if src and src.fps:
            self.fps_spin.setValue(src.fps)

    def _browse_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Output folder", self.dir_edit.text() or os.path.expanduser("~"))
        if d:
            self.dir_edit.setText(os.path.normpath(d))
            self.beside_chk.setChecked(False)
            self._save_settings()

    def _open_out_dir(self):
        path = None
        if self.recipe.out_dir and not self.recipe.beside_source:
            path = self.recipe.out_dir
            os.makedirs(path, exist_ok=True)
        elif self.jobs:
            path = os.path.dirname(self.jobs[0].out_path)
        if path and os.path.isdir(path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    # ---------------- HTML viewer ----------------
    def _build_html_group(self, rl):
        g = QGroupBox("HTML viewer format")
        self.html_group = g
        v = QVBoxLayout(g)
        info = QLabel("One self-contained .html page per file, holding the original intensities. "
                      "Choose what the page offers its viewers; the axis ranges above choose what is included.")
        info.setWordWrap(True)
        info.setObjectName("hint")
        v.addWidget(info)
        ch = self._on_html_changed

        top = QFormLayout()
        self.html_preset = QComboBox()
        for k, (label, _tools) in HTML_PRESETS.items():
            self.html_preset.addItem(label, k)
        self.html_preset.setToolTip("Full explorer: every tool. Movie player: playback, gallery and zoom only.\n"
                                    "Interactive figure: a fixed layout you can zoom, inspect and measure.")
        self.html_preset.currentIndexChanged.connect(self._on_html_preset)
        top.addRow("Start from", self.html_preset)
        v.addLayout(top)

        tl = QLabel("Tools in the page")
        tl.setObjectName("hint")
        v.addWidget(tl)
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        self.html_tool_chk = {}
        for i, (k, (label, tip)) in enumerate(HTML_TOOLS.items()):
            cb = QCheckBox(label)
            cb.setToolTip(tip)
            cb.toggled.connect(self._on_html_tool_toggled)
            grid.addWidget(cb, i // 2, i % 2)
            self.html_tool_chk[k] = cb
        v.addLayout(grid)

        f = QFormLayout()
        panel_note = QLabel("Tiles: set with the Panel box below (same settings as an image panel); "
                            "they are fixed in the page.")
        panel_note.setWordWrap(True)
        panel_note.setObjectName("hint")
        f.addRow(panel_note)
        self.html_lut_view = QComboBox()
        self.html_lut_view.addItem("For the selected tile (click a tile)", "selected")
        self.html_lut_view.addItem("Beside every tile", "beside")
        self.html_lut_view.setToolTip("Selected tile: the LUT histograms show the tile you click (e.g. one position "
                                      "or time point).\nBeside every tile: each tile gets its own small histogram "
                                      "per channel next to it.")
        self.html_lut_view.currentIndexChanged.connect(ch)
        f.addRow("LUT histograms", self.html_lut_view)
        orow = QHBoxLayout()
        self.html_ovl_chk = {}
        for k, label in (("scalebar", "Scale bar"), ("time", "Time"), ("z", "Z"), ("names", "Channels"),
                         ("position", "Position")):
            cb = QCheckBox(label)
            cb.toggled.connect(ch)
            orow.addWidget(cb)
            self.html_ovl_chk[k] = cb
        orow.addStretch(1)
        f.addRow("Overlays shown", orow)
        self.html_title = QLineEdit()
        self.html_title.setPlaceholderText("file name ({name} works here)")
        self.html_title.textChanged.connect(ch)
        f.addRow("Title", self.html_title)
        self.html_caption = QLineEdit()
        self.html_caption.setPlaceholderText("optional subtitle / description")
        self.html_caption.textChanged.connect(ch)
        f.addRow("Caption", self.html_caption)
        self.html_theme = QComboBox()
        self.html_theme.addItem("Dark", "dark")
        self.html_theme.addItem("Light", "light")
        self.html_theme.currentIndexChanged.connect(ch)
        f.addRow("Theme", self.html_theme)
        srow = QHBoxLayout()
        self.html_start = QComboBox()
        self.html_start.addItem("First frame", "first")
        self.html_start.addItem("Current slider position", "current")
        self.html_start.currentIndexChanged.connect(ch)
        srow.addWidget(self.html_start, 1)
        self.html_autoplay = QCheckBox("Autoplay")
        self.html_autoplay.toggled.connect(ch)
        srow.addWidget(self.html_autoplay)
        self.html_autoframe = QCheckBox("Auto contrast on every frame")
        self.html_autoframe.setToolTip("The page re-stretches each channel's contrast for every frame it shows\n"
                                       "(viewers can still switch it off per channel).")
        self.html_autoframe.toggled.connect(ch)
        f.addRow("Opens at", srow)
        f.addRow("", self.html_autoframe)
        self.html_fps = QDoubleSpinBox(decimals=1, minimum=0.5, maximum=120, singleStep=1)
        self.html_fps.setSuffix(" fps")
        self.html_fps.setToolTip("Initial playback speed in the viewer")
        self.html_fps.valueChanged.connect(self._on_html_fps)
        f.addRow("Frame rate", self.html_fps)
        self.html_budget = QSpinBox(minimum=16, maximum=4000, singleStep=50)
        self.html_budget.setSuffix(" MB")
        self.html_budget.setToolTip("Raw data above this size is binned 2\u00d72 (then 4\u00d74 \u2026) so the page "
                                    "stays quick to open. Narrow the axis ranges to keep full resolution.")
        self.html_budget.valueChanged.connect(self._on_settings_changed)
        f.addRow("Data size limit", self.html_budget)
        v.addLayout(f)
        rl.addWidget(g)

    def _html_to_ui(self):
        h = self.recipe.html
        self._html_updating = True
        try:
            self.html_preset.setCurrentIndex(max(0, self.html_preset.findData(h.preset)))
            for k, cb in self.html_tool_chk.items():
                cb.setChecked(bool(h.tools.get(k, True)))
            for k, cb in self.html_ovl_chk.items():
                cb.setChecked(bool(h.overlays.get(k, True)))
            self.html_lut_view.setCurrentIndex(max(0, self.html_lut_view.findData(getattr(h, "lut_view", "selected"))))
            self.html_title.setText(h.title)
            self.html_caption.setText(h.caption)
            self.html_theme.setCurrentIndex(max(0, self.html_theme.findData(h.theme)))
            self.html_start.setCurrentIndex(max(0, self.html_start.findData(h.start)))
            self.html_autoplay.setChecked(h.autoplay)
            self.html_autoframe.setChecked(bool(getattr(h, "auto_frame", False)))
        finally:
            self._html_updating = False

    def _on_html_preset(self, *_):
        if getattr(self, "_html_updating", False):
            return
        key = self.html_preset.currentData()
        tools = HTML_PRESETS.get(key, (None, None))[1]
        self.recipe.html.preset = key
        if tools:
            self._html_updating = True
            for k, cb in self.html_tool_chk.items():
                cb.setChecked(tools.get(k, False))
            self.html_autoplay.setChecked(key == "player")
            self._html_updating = False
        self._on_html_changed()

    def _on_html_tool_toggled(self, *_):
        if getattr(self, "_html_updating", False):
            return
        tools = {k: cb.isChecked() for k, cb in self.html_tool_chk.items()}
        match = next((k for k, (_l, t) in HTML_PRESETS.items() if t and t == tools), "custom")
        self._html_updating = True
        self.html_preset.setCurrentIndex(self.html_preset.findData(match))
        self._html_updating = False
        self._on_html_changed()

    def _on_html_changed(self, *_):
        if getattr(self, "_html_updating", False) or self._building_axes:
            return
        h = self.recipe.html
        h.preset = self.html_preset.currentData() or "custom"
        h.tools = {k: cb.isChecked() for k, cb in self.html_tool_chk.items()}
        h.overlays = {k: cb.isChecked() for k, cb in self.html_ovl_chk.items()}
        h.lut_view = self.html_lut_view.currentData() or "selected"
        h.title = self.html_title.text()
        h.caption = self.html_caption.text()
        h.theme = self.html_theme.currentData()
        h.start = self.html_start.currentData()
        h.autoplay = self.html_autoplay.isChecked()
        h.auto_frame = self.html_autoframe.isChecked()
        self.update_preview()

    def _on_html_fps(self, v):
        if not self._building_axes:
            self.fps_spin.setValue(v)

    # ---------------- annotations ----------------
    def _build_annot_group(self, rl):
        g = QGroupBox("Annotations (burned into the output)")
        self.annot_group = g
        grid = QGridLayout(g)
        grid.setColumnStretch(2, 1)
        a = self.recipe.annot
        ch = self._on_annot_changed
        self.an = {}

        def row(r, key, label, corner_attr, extra=None, tip=""):
            cb = QCheckBox(label)
            cb.setToolTip(tip)
            cb.toggled.connect(ch)
            grid.addWidget(cb, r, 0)
            cc = _corner_combo(getattr(a, corner_attr), ch)
            grid.addWidget(cc, r, 1)
            if extra is not None:
                grid.addWidget(extra, r, 2)
            self.an[key] = (cb, cc, corner_attr)

        self.ts_fmt = QComboBox()
        for k, v in TIME_FORMATS.items():
            self.ts_fmt.addItem(v, k)
        self.ts_fmt.currentIndexChanged.connect(ch)
        row(0, "timestamp", "Time stamp", "ts_pos", self.ts_fmt,
            "Elapsed time from the metadata (each position keeps its own clock)")
        tz = QHBoxLayout()
        self.ts_zero = QComboBox()
        self.ts_zero.addItem("t = 0 at first frame of each position", "position")
        self.ts_zero.addItem("t = 0 at start of acquisition", "experiment")
        self.ts_zero.currentIndexChanged.connect(ch)
        tz.addWidget(self.ts_zero, 1)
        self.ts_offset = QDoubleSpinBox(decimals=2, minimum=-1e6, maximum=1e6, singleStep=1)
        self.ts_offset.setPrefix("\u2212 ")
        self.ts_offset.setSuffix(" min")
        self.ts_offset.setToolTip("Shift time zero, e.g. 30 min so that a treatment at 30 min reads t = 0")
        self.ts_offset.valueChanged.connect(ch)
        tz.addWidget(self.ts_offset)
        self.ts_prefix = QLineEdit()
        self.ts_prefix.setPlaceholderText("prefix e.g. t = ")
        self.ts_prefix.setMaximumWidth(110)
        self.ts_prefix.textChanged.connect(ch)
        tz.addWidget(self.ts_prefix)
        grid.addLayout(tz, 1, 0, 1, 3)

        sb = QHBoxLayout()
        self.sb_len = QDoubleSpinBox(decimals=2, minimum=0.0, maximum=1e6, singleStep=5)
        self.sb_len.setSpecialValueText("auto length")
        self.sb_len.setSuffix(" \u00b5m")
        self.sb_len.valueChanged.connect(ch)
        sb.addWidget(self.sb_len)
        sbw = QWidget()
        sbw.setLayout(sb)
        sb.setContentsMargins(0, 0, 0, 0)
        row(2, "scalebar", "Scale bar", "sb_pos", sbw, "Needs the pixel size (shown under the preview)")
        sb2 = QHBoxLayout()
        self.sb_label = QCheckBox("Show length")
        self.sb_label.toggled.connect(ch)
        sb2.addWidget(self.sb_label)
        self.sb_every = QCheckBox("On every panel tile")
        self.sb_every.toggled.connect(ch)
        sb2.addWidget(self.sb_every)
        sb2.addWidget(QLabel("Thickness"))
        self.sb_thick = QDoubleSpinBox(decimals=1, minimum=0.2, maximum=10, singleStep=0.2)
        self.sb_thick.setSuffix(" %")
        self.sb_thick.valueChanged.connect(ch)
        sb2.addWidget(self.sb_thick)
        sb2.addStretch(1)
        grid.addLayout(sb2, 3, 0, 1, 3)
        row(4, "zpos", "Z depth", "z_pos", None, "z position in \u00b5m (or slice number if unknown)")
        row(5, "channels", "Channel names", "ch_pos", None, "Channel names in their colours")
        row(6, "position", "Position name", "pos_pos", None, "Multipoint / stage position name from the metadata")
        row(7, "filename", "File name", "name_pos")
        self.text_edit = QLineEdit()
        self.text_edit.setPlaceholderText("Custom text: {name} {pos} {time} {cname}")
        self.text_edit.textChanged.connect(ch)
        tl = QLabel("Text")
        grid.addWidget(tl, 8, 0)
        self.text_pos = _corner_combo(a.text_pos, ch)
        grid.addWidget(self.text_pos, 8, 1)
        grid.addWidget(self.text_edit, 9, 0, 1, 3)
        st = QHBoxLayout()
        st.addWidget(QLabel("Text size"))
        self.font_pct = QDoubleSpinBox(decimals=1, minimum=1.0, maximum=20.0, singleStep=0.5)
        self.font_pct.setSuffix(" %")
        self.font_pct.setToolTip("Text height as a percentage of the image's shorter side")
        self.font_pct.valueChanged.connect(ch)
        st.addWidget(self.font_pct)
        self.an_color = QComboBox()
        for k, v in (("white", "White"), ("black", "Black"), ("yellow", "Yellow")):
            self.an_color.addItem(v, k)
        self.an_color.currentIndexChanged.connect(ch)
        st.addWidget(self.an_color)
        self.an_outline = QCheckBox("Outline")
        self.an_outline.toggled.connect(ch)
        st.addWidget(self.an_outline)
        st.addStretch(1)
        grid.addLayout(st, 10, 0, 1, 3)
        rl.addWidget(g)

    def _build_panel_group(self, rl):
        g = QGroupBox("Panel (m \u00d7 n montage)")
        self.panel_group = g
        f = QFormLayout(g)
        ch = self._on_annot_changed
        self.pn_axis = QComboBox()
        self.pn_axis.setToolTip("Which axis to lay out as tiles, e.g. all channels side by side, a Z stack, "
                                "time points, positions, or several files next to each other.")
        self.pn_axis.currentIndexChanged.connect(self._on_panel_axis_changed)
        f.addRow("Make a panel of", self.pn_axis)
        arow = QHBoxLayout()
        self.pn_count = QSpinBox(minimum=0, maximum=200)
        self.pn_count.setSpecialValueText("auto")
        self.pn_count.setToolTip("How many images fit in one row (or column). 'auto' makes a near-square grid.")
        self.pn_count.valueChanged.connect(ch)
        arow.addWidget(self.pn_count)
        self.pn_fill = QComboBox()
        for k, v in PANEL_FILL.items():
            self.pn_fill.addItem(v.lower(), k)
        self.pn_fill.currentIndexChanged.connect(ch)
        arow.addWidget(self.pn_fill, 1)
        f.addRow("Layout", arow)
        self.pn_shape = QLabel("")
        self.pn_shape.setObjectName("hint")
        f.addRow(self.pn_shape)
        self.pn_merge = QCheckBox("Add a merged tile when the panel shows channels")
        self.pn_merge.toggled.connect(ch)
        f.addRow(self.pn_merge)
        self.pn_gap = QSpinBox(minimum=0, maximum=200)
        self.pn_gap.setSuffix(" px")
        self.pn_gap.valueChanged.connect(ch)
        f.addRow("Spacing", self.pn_gap)
        self.pn_bg = QComboBox()
        self.pn_bg.addItem("White", "white")
        self.pn_bg.addItem("Black", "black")
        self.pn_bg.currentIndexChanged.connect(ch)
        f.addRow("Background", self.pn_bg)
        # HTML only: tiles per page for each axis (the page splits longer panels into pages,
        # and the time / Z panels a viewer opens from a tile use their own grid)
        self.pn_grid_note = QLabel("Tiles per page in the HTML page (0 = all on one page). The page makes as "
                                   "many pages as needed; double-clicking a tile opens it, and from there its "
                                   "time or Z panel uses that axis's grid.")
        self.pn_grid_note.setWordWrap(True)
        self.pn_grid_note.setObjectName("hint")
        f.addRow(self.pn_grid_note)
        self.pn_grid = {}
        for a, nice in (("M", "Positions"), ("T", "Time points"), ("Z", "Z-slices")):
            row = QHBoxLayout()
            rs = QSpinBox(minimum=0, maximum=20)
            cs = QSpinBox(minimum=0, maximum=20)
            for sp, what in ((rs, "rows"), (cs, "columns")):
                sp.setSpecialValueText("auto")
                sp.setToolTip(f"{what.capitalize()} of {nice.lower()} per page (auto = fit all on one page)")
                sp.valueChanged.connect(self._on_grid_changed)
            row.addWidget(rs)
            row.addWidget(QLabel("×"))
            row.addWidget(cs)
            row.addWidget(QLabel("per page"), 1)
            host = QWidget()
            host.setLayout(row)
            row.setContentsMargins(0, 0, 0, 0)
            f.addRow(nice, host)
            self.pn_grid[a] = (rs, cs, host)
        self._pn_form = f
        self.pn_widgets = (self.pn_count, self.pn_fill, self.pn_merge, self.pn_gap, self.pn_bg)
        rl.addWidget(g)

    def _on_grid_changed(self, *_):
        if self._building_axes or getattr(self, "_grid_updating", False):
            return
        self.recipe.html.grids = {a: [rs.value(), cs.value()] for a, (rs, cs, _h) in self.pn_grid.items()}
        self._update_panel_widgets()
        self.update_preview()

    def _update_grid_rows(self):
        html_out = self.recipe.output == "html"
        src = self.current_source()
        present = {}
        for s in self.sources:
            for a, n in s.axes.items():
                present[a] = max(present.get(a, 1), n)
        self.pn_grid_note.setVisible(html_out)
        for a, (rs, cs, host) in self.pn_grid.items():
            self._pn_form.setRowVisible(host, html_out and present.get(a, 1) > 1)
        g = getattr(self.recipe.html, "grids", None) or {}
        self._grid_updating = True
        for a, (rs, cs, _h) in self.pn_grid.items():
            v = g.get(a, [0, 0])
            rs.setValue(int(v[0]))
            cs.setValue(int(v[1]))
        self._grid_updating = False
        # in HTML the grid of the panel axis replaces the "N per row" count
        ax = self.recipe.panel_axis
        self.pn_count.setVisible(not (html_out and ax in self.pn_grid))
        del src

    def _fill_panel_axes(self, present):
        cur = self.recipe.panel_axis
        self.pn_axis.blockSignals(True)
        self.pn_axis.clear()
        self.pn_axis.addItem("No panel", "")
        for a in ordered_axes(present):
            nice = {"C": "Channels", "T": "Time points", "Z": "Z-slices", "M": "Positions", "P": "Pages",
                    "I": "Frames"}.get(a, axis_label(a))
            self.pn_axis.addItem(f"{nice} ({a}, up to {present[a]})", a)
        if len(self.sources) > 1 and self.recipe.output != "html":
            self.pn_axis.addItem("Files (side by side)", "F")
        i = self.pn_axis.findData(cur)
        if i < 0:
            self.recipe.panel_axis = ""
            i = 0
        self.pn_axis.setCurrentIndex(i)
        self.pn_axis.blockSignals(False)
        self._update_panel_widgets()

    def _on_panel_axis_changed(self, *_):
        if self._building_axes:
            return
        self.recipe.panel_axis = self.pn_axis.currentData() or ""
        self.refresh_axes_table()
        self._on_annot_changed()

    def _update_panel_widgets(self):
        on = bool(self.recipe.panel_axis)
        for w in self.pn_widgets:
            w.setEnabled(on)
        self.pn_merge.setEnabled(self.recipe.panel_axis == "C")
        if hasattr(self, "pn_grid"):
            self._update_grid_rows()
        self.pn_shape.setText(self._panel_shape_text())

    def _panel_shape_text(self):
        import math

        ax = self.recipe.panel_axis
        if not ax:
            return "Turn on to lay several images out in one grid."
        if ax == "F":
            n = len(self.sources)
        else:
            src = self.current_source()
            if not src or ax not in src.axes:
                src = next((x for x in self.sources if ax in x.axes), None)
            if src is None:
                return ""
            n = len(parse_sel(self.recipe.rule(ax).sel, src.axes[ax], src.current.get(ax, 0)))
            if ax == "C" and self.recipe.panel_merge and len(src.channels) > 1:
                n += 1
        if self.recipe.output == "html" and ax in "MTZ":
            gr = (getattr(self.recipe.html, "grids", None) or {}).get(ax, [0, 0])
            if gr[0] > 0 or gr[1] > 0:
                rr = gr[0] or math.ceil(n / max(1, gr[1]))
                cc = gr[1] or math.ceil(n / max(1, gr[0]))
                pages = math.ceil(n / max(1, rr * cc))
                return (f"{n} image(s) → {rr} × {cc} per page, {pages} page(s). "
                        "The axis range above picks which images.")
        per = self.recipe.panel_count or (n if n <= 4 else max(1, math.ceil(math.sqrt(n))))
        per = min(per, n) if n else per
        other = math.ceil(n / per) if per else 0
        rows, cols = (other, per) if self.recipe.panel_fill == "row" else (per, other)
        return f"{n} image(s) \u2192 {rows} row(s) \u00d7 {cols} column(s). The axis range above picks which images."

    def _annot_to_ui(self):
        a, r = self.recipe.annot, self.recipe
        for key, (cb, cc, attr) in self.an.items():
            cb.setChecked(bool(getattr(a, key)))
            cc.setCurrentIndex(max(0, cc.findData(getattr(a, attr))))
        self.ts_fmt.setCurrentIndex(max(0, self.ts_fmt.findData(a.ts_format)))
        self.ts_zero.setCurrentIndex(max(0, self.ts_zero.findData(a.ts_zero)))
        self.ts_offset.setValue(a.ts_offset_min)
        self.ts_prefix.setText(a.ts_prefix)
        self.sb_len.setValue(a.sb_um)
        self.sb_label.setChecked(a.sb_label)
        self.sb_every.setChecked(a.sb_every_tile)
        self.sb_thick.setValue(a.sb_thick_pct)
        self.text_edit.setText(a.text)
        self.text_pos.setCurrentIndex(max(0, self.text_pos.findData(a.text_pos)))
        self.font_pct.setValue(a.font_pct)
        self.an_color.setCurrentIndex(max(0, self.an_color.findData(a.color)))
        self.an_outline.setChecked(a.outline)
        self.pn_count.setValue(int(r.panel_count))
        self.pn_fill.setCurrentIndex(max(0, self.pn_fill.findData(r.panel_fill)))
        self.pn_gap.setValue(int(r.panel_gap))
        self.pn_bg.setCurrentIndex(max(0, self.pn_bg.findData(r.panel_bg)))
        self.pn_merge.setChecked(bool(r.panel_merge))

    def _on_annot_changed(self, *_):
        if self._building_axes:
            return
        a, r = self.recipe.annot, self.recipe
        for key, (cb, cc, attr) in self.an.items():
            setattr(a, key, cb.isChecked())
            setattr(a, attr, cc.currentData())
        a.ts_format = self.ts_fmt.currentData()
        a.ts_zero = self.ts_zero.currentData()
        a.ts_offset_min = self.ts_offset.value()
        a.ts_prefix = self.ts_prefix.text()
        a.sb_um = self.sb_len.value()
        a.sb_label = self.sb_label.isChecked()
        a.sb_every_tile = self.sb_every.isChecked()
        a.sb_thick_pct = self.sb_thick.value()
        a.text = self.text_edit.text()
        a.text_pos = self.text_pos.currentData()
        a.font_pct = self.font_pct.value()
        a.color = self.an_color.currentData()
        a.outline = self.an_outline.isChecked()
        r.panel_count = self.pn_count.value()
        r.panel_fill = self.pn_fill.currentData() or "row"
        self._update_panel_widgets()
        r.panel_gap = self.pn_gap.value()
        r.panel_bg = self.pn_bg.currentData()
        r.panel_merge = self.pn_merge.isChecked()
        self._update_visibility()
        self.update_preview()
        self._plan_timer.start()

    def _update_scale_info(self):
        src = self.current_source()
        if not src or self.recipe.scale_mode == "manual":
            self.scale_info.setText("")
            return
        from .export import scale_factor, tile_dims

        try:
            unit = preview_unit(src, self.recipe)
            f = scale_factor(src, self.recipe, tile_dims(unit))
            self.scale_info.setText(f"this file: {f * 100:.0f} %")
        except Exception:
            self.scale_info.setText("")

    # ---------------- per-file metadata ----------------
    def _meta_to_ui(self, src):
        self._meta_updating = True
        try:
            for w, v in ((self.px_spin, getattr(src, "pixel_size", None)),
                         (self.int_spin, getattr(src, "interval_s", None)),
                         (self.zstep_spin, getattr(src, "z_step", None))):
                w.setValue(float(v) if v else 0.0)
            if src:
                self.int_spin.setEnabled("T" in src.axes)
                self.zstep_spin.setEnabled("Z" in src.axes)
        finally:
            self._meta_updating = False

    def _on_meta_edited(self, *_):
        if self._meta_updating:
            return
        src = self.current_source()
        if not src:
            return
        src.pixel_size = self.px_spin.value() or None
        iv = self.int_spin.value() or None
        if iv != src.interval_s:
            src.interval_s = iv
            src.use_interval = bool(iv) and bool(src._times) and iv != src.interval_meta
        src.z_step = self.zstep_spin.value() or None
        self.update_preview()
        self._plan_timer.start()

    def _reset_meta(self):
        src = self.current_source()
        if not src:
            return
        src.pixel_size = src.pixel_size_meta
        src.interval_s = src.interval_meta
        src.z_step = src.z_step_meta
        src.use_interval = False
        self._meta_to_ui(src)
        self.update_preview()
        self._plan_timer.start()

    def _show_metadata(self):
        src = self.current_source()
        if not src:
            return
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Metadata \u2014 {os.path.basename(src.path)}")
        dlg.resize(640, 420)
        lay = QVBoxLayout(dlg)
        txt = QPlainTextEdit("\n".join(src.info_lines()))
        txt.setReadOnly(True)
        lay.addWidget(txt)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(dlg.reject)
        lay.addWidget(bb)
        dlg.exec()

    def _edit_channel_range(self, src, c, ch):
        from .render import stack_limits

        auto = stack_limits(src, c, self.recipe.display)
        cur = ch.limits or auto
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Display range \u2014 {ch.name}")
        f = QFormLayout(dlg)
        mx = float(np.iinfo(src.dtype).max) if np.issubdtype(src.dtype, np.integer) else 1e9
        lo = QDoubleSpinBox(decimals=2, minimum=-1e9, maximum=mx, value=cur[0])
        hi = QDoubleSpinBox(decimals=2, minimum=-1e9, maximum=mx, value=cur[1])
        f.addRow(QLabel(f"Auto range for this channel: {auto[0]:.0f} \u2013 {auto[1]:.0f}"))
        f.addRow("Minimum (black)", lo)
        f.addRow("Maximum (full colour)", hi)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.Reset)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        reset = [False]

        def do_reset():
            reset[0] = True
            dlg.accept()

        bb.button(QDialogButtonBox.Reset).setText("Auto")
        bb.button(QDialogButtonBox.Reset).clicked.connect(do_reset)
        f.addRow(bb)
        if dlg.exec():
            ch.limits = None if reset[0] else (lo.value(), hi.value())
            self.update_preview()

    # ---------------- axes table ----------------
    def refresh_axes_table(self):
        present = {}
        for s in self.sources:
            for a, n in s.axes.items():
                present[a] = max(present.get(a, 0), n)
        axes = ordered_axes(present)
        self._building_axes = True
        g = self.axes_grid
        self._clear_layout(g)
        if not axes:
            empty = QLabel("Load files to see their axes.")
            empty.setObjectName("hint")
            g.addWidget(empty, 0, 0, 1, 3)
        else:
            for col, txt in enumerate(["Axis", "Handling", "Range (1-based)"]):
                h = QLabel(txt)
                h.setObjectName("hint")
                g.addWidget(h, 0, col)
        for row, a in enumerate(axes, start=1):
            rule = self.recipe.rule(a)
            lab = QLabel(f"<b>{a}</b> {axis_label(a)} <span style='color:#7f8494'>({present[a]})</span>")
            g.addWidget(lab, row, 0)
            combo = QComboBox()
            if a == "C":
                modes = ["composite", "iterate", "fixed"]
            else:
                modes = ["iterate", "fixed", "max"]
            if self.recipe.output == "animation":
                modes.append("animate")
            if self.recipe.output == "html" and a != self.recipe.panel_axis:
                combo.addItem(MODES["viewer"], "viewer")
                combo.setToolTip(MODE_TIPS["viewer"])
                combo.setEnabled(False)
                g.addWidget(combo, row, 1)
                edit = QLineEdit(rule.sel)
                edit.setPlaceholderText("all")
                edit.setToolTip("Which frames go into the viewer, e.g. all, 1-20, 1-100:5")
                edit.textChanged.connect(lambda txt, ax=a: self._on_rule_sel(ax, txt))
                g.addWidget(edit, row, 2)
                continue
            if a == self.recipe.panel_axis:
                combo.addItem(MODES["panel"], "panel")
                combo.setToolTip(MODE_TIPS["panel"])
                combo.setEnabled(False)
                g.addWidget(combo, row, 1)
                edit = QLineEdit(rule.sel)
                edit.setPlaceholderText("all")
                edit.setToolTip("Which images go into the panel, e.g. all, 1-9, 1-50:5")
                edit.textChanged.connect(lambda txt, ax=a: self._on_rule_sel(ax, txt))
                g.addWidget(edit, row, 2)
                continue
            for m in modes:
                combo.addItem(MODES[m], m)
                combo.setItemData(combo.count() - 1, MODE_TIPS[m], Qt.ToolTipRole)
            if rule.mode not in modes:
                rule.mode = modes[0]
            combo.setCurrentIndex(combo.findData(rule.mode))
            combo.currentIndexChanged.connect(lambda _i, ax=a, c=combo: self._on_rule_mode(ax, c.currentData()))
            g.addWidget(combo, row, 1)
            edit = QLineEdit(rule.sel)
            edit.setPlaceholderText("all")
            edit.textChanged.connect(lambda txt, ax=a: self._on_rule_sel(ax, txt))
            edit.setEnabled(rule.mode != "composite")
            g.addWidget(edit, row, 2)
        self._fill_panel_axes(present)
        self._building_axes = False

    def _on_rule_mode(self, axis, mode):
        if self._building_axes:
            return
        if mode == "animate":
            for a, r in self.recipe.rules.items():
                if a != axis and r.mode == mode:
                    r.mode = "composite" if a == "C" else "iterate"
        r = self.recipe.rule(axis)
        r.mode = mode
        if mode == "fixed" and r.sel.strip().lower() in ("", "all"):
            r.sel = "current"
        if mode != "fixed" and r.sel.strip().lower() == "current":
            r.sel = "all"
        QTimer.singleShot(0, self.refresh_axes_table)
        self._plan_timer.start()

    def _on_rule_sel(self, axis, txt):
        if self.recipe.output == "html" and not self._building_axes:
            self.recipe.rule(axis).sel = txt
            self.update_preview()
        if self._building_axes:
            return
        self.recipe.rule(axis).sel = txt
        if axis == self.recipe.panel_axis:
            self._update_panel_widgets()
            self.update_preview()
        self._plan_timer.start()

    # ---------------- files ----------------
    def add_files_dialog(self):
        exts = " ".join(sorted("*" + e for e in SUPPORTED_EXT if e.count(".") == 1))
        files, _ = QFileDialog.getOpenFileNames(self, "Add files", self.settings.value("last_in", ""),
                                                f"Supported files ({exts});;All files (*)")
        if files:
            self.settings.setValue("last_in", os.path.dirname(files[0]))
            self.add_paths(files)

    def add_folder_dialog(self):
        d = QFileDialog.getExistingDirectory(self, "Add folder", self.settings.value("last_in", ""))
        if d:
            self.settings.setValue("last_in", d)
            self.add_paths([d])

    def add_paths(self, paths):
        files = []
        for p in paths:
            if os.path.isdir(p):
                for root, _dirs, names in os.walk(p):
                    for n in sorted(names):
                        fp = os.path.join(root, n)
                        if is_supported(fp):
                            files.append(fp)
            elif os.path.isfile(p):
                files.append(p)
        existing = {os.path.normcase(os.path.abspath(s.path)) for s in self.sources}
        was_empty = not self.sources
        errors = []
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            for k, fp in enumerate(files):
                if os.path.normcase(os.path.abspath(fp)) in existing:
                    continue
                self.statusBar().showMessage(f"Opening {os.path.basename(fp)} ({k + 1}/{len(files)})…")
                QApplication.processEvents()
                try:
                    src = open_source(fp)
                except Exception as ex:
                    errors.append(f"{os.path.basename(fp)}: {ex}")
                    continue
                if isinstance(src, SvgSource):
                    src.set_scale(self.svg_scale.value())
                elif isinstance(src, PdfSource):
                    src.set_dpi(self.pdf_dpi.value())
                self.sources.append(src)
                existing.add(os.path.normcase(os.path.abspath(fp)))
                item = QListWidgetItem()
                item.setData(Qt.UserRole, src)
                item.setIcon(self._thumb(src))
                item.setSizeHint(QSize(0, 62))
                self.file_list.addItem(item)
        finally:
            QApplication.restoreOverrideCursor()
        self._refresh_item_texts()
        # a first batch of camera photos (HEIC / JPEG) converts to JPEG by default: PNG would be ~4x the size
        if (was_empty and self.sources and all(getattr(x, "lossy_photo", False) for x in self.sources)
                and self.recipe.output == "images" and self.recipe.fmt in ("png", "tif", "bmp")):
            i = self.fmt_combo.findData("jpg")
            if i >= 0:
                self.fmt_combo.setCurrentIndex(i)
        if self.recipe.output == "animation":
            self._on_output_changed()
        self.refresh_axes_table()
        if self.file_list.currentRow() < 0 and self.file_list.count():
            self.file_list.setCurrentRow(0)
        self._update_enabled()
        self._plan_timer.start()
        self.statusBar().showMessage(f"{len(self.sources)} file(s) loaded", 5000)
        if errors:
            QMessageBox.warning(self, "Some files could not be opened", "\n".join(errors[:30]))

    def _thumb(self, src) -> QIcon:
        try:
            arr = render(src, src.current, None, None, self.recipe.display)
            q = to_qimage(arr).scaled(56, 56, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            return QIcon(QPixmap.fromImage(q))
        except Exception:
            return self.style().standardIcon(QStyle.SP_FileIcon)

    def _refresh_item_texts(self):
        for i in range(self.file_list.count()):
            it = self.file_list.item(i)
            s = it.data(Qt.UserRole)
            it.setText(f"{os.path.basename(s.path)}\n{s.describe()}")
            it.setToolTip(s.path)
        self.files_label.setText(f"Files ({self.file_list.count()})")

    def _on_rows_moved(self, *_):
        self.sources = [self.file_list.item(i).data(Qt.UserRole) for i in range(self.file_list.count())]
        self._plan_timer.start()

    def remove_selected(self):
        if self._thread:
            return
        for it in self.file_list.selectedItems():
            s = it.data(Qt.UserRole)
            self.file_list.takeItem(self.file_list.row(it))
            if s in self.sources:
                self.sources.remove(s)
            s.close()
        self._after_remove()

    def clear_all(self):
        if self._thread:
            return
        for s in self.sources:
            s.close()
        self.sources.clear()
        self.file_list.clear()
        self._after_remove()

    def _after_remove(self):
        self._stop_play()
        self._refresh_item_texts()
        self.refresh_axes_table()
        self.on_select()
        self._plan_timer.start()

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if paths:
            self.add_paths(paths)

    # ---------------- preview ----------------
    def current_source(self):
        it = self.file_list.currentItem()
        return it.data(Qt.UserRole) if it else None

    def on_select(self):
        self._stop_play()
        src = self.current_source()
        self._build_axis_controls(src)
        self._build_channel_controls(src)
        self._meta_to_ui(src)
        self._update_scale_info()
        self._update_panel_widgets()
        self._update_enabled()
        self.update_preview()

    def _clear_layout(self, lay):
        while lay.count():
            item = lay.takeAt(0)
            w = item.widget()
            if w:
                w.hide()
                w.setParent(None)
                w.deleteLater()
            elif item.layout():
                self._clear_layout(item.layout())

    def _build_axis_controls(self, src):
        self._clear_layout(self.axes_layout)
        self._axis_widgets = {}
        if not src:
            return
        for row, a in enumerate(ordered_axes(src.axes)):
            if a == "C" and not src.rgb:
                pass
            n = src.axes[a]
            lab = QLabel(f"<b>{a}</b> {axis_label(a)}")
            lab.setMinimumWidth(90)
            sl = QSlider(Qt.Horizontal, minimum=0, maximum=n - 1, value=src.current.get(a, 0))
            val = QLabel()
            val.setMinimumWidth(70)
            play = QToolButton()
            play.setText("▶")
            play.setToolTip(f"Play through {axis_label(a)} at the animation frame rate")
            play.setCheckable(True)

            def on_val(v, ax=a, lb=val, nn=n):
                src.current[ax] = v
                extra = f" · {src.channel_name(v)}" if ax == "C" else ""
                lb.setText(f"{v + 1} / {nn}{extra}")
                self.update_preview()
                if any(r.sel.strip().lower() == "current" for r in self.recipe.rules.values()):
                    self._plan_timer.start()

            sl.valueChanged.connect(on_val)
            play.toggled.connect(lambda on, ax=a, b=play: self._toggle_play(ax, on, b))
            on_val(sl.value())
            self.axes_layout.addWidget(lab, row, 0)
            self.axes_layout.addWidget(play, row, 1)
            self.axes_layout.addWidget(sl, row, 2)
            self.axes_layout.addWidget(val, row, 3)
            self._axis_widgets[a] = (sl, play)

    def _build_channel_controls(self, src):
        self._clear_layout(self.chan_layout)
        if not src or not src.channels:
            return
        self.chan_layout.addWidget(QLabel("Channels:"))
        for i, ch in enumerate(src.channels):
            cb = QCheckBox(ch.name)
            cb.setChecked(ch.visible)
            cb.setToolTip("Show in composite / include in merged exports")
            btn = QToolButton()
            btn.setFixedSize(20, 20)
            btn.setStyleSheet(f"background: rgb{tuple(ch.color)}; border:1px solid #555; border-radius:4px;")
            btn.setToolTip("Change channel colour")

            def pick(_=False, c=ch, b=btn):
                col = QColorDialog.getColor(QColor(*c.color), self, f"Colour for {c.name}")
                if col.isValid():
                    c.color = (col.red(), col.green(), col.blue())
                    b.setStyleSheet(f"background: rgb{tuple(c.color)}; border:1px solid #555; border-radius:4px;")
                    self.update_preview()

            btn.clicked.connect(pick)
            cb.toggled.connect(lambda on, c=ch: (setattr(c, "visible", on), self.update_preview(),
                                                 self._plan_timer.start()))
            rng = QToolButton()
            rng.setText("\u25d0")
            rng.setToolTip("Set this channel's display range (min / max)")
            rng.clicked.connect(lambda _=False, c=ch, k=i, s_=src: self._edit_channel_range(s_, k, c))
            self.chan_layout.addWidget(btn)
            self.chan_layout.addWidget(cb)
            self.chan_layout.addWidget(rng)
            self.chan_layout.addSpacing(10)
        self.chan_layout.addStretch(1)

    def update_preview(self):
        src = self.current_source()
        live_html = self.recipe.output == "html" and self.preview_out_chk.isChecked()
        self.preview_stack.setCurrentIndex(1 if (live_html and src) else 0)
        if not src:
            self.preview.set_image(None)
            self.info_label.setText("")
            return
        if live_html:
            self.info_label.setText(f"{src.path}   \u00b7   {src.describe()}")
            if self.web is not None:
                self.web_status.setText("Live preview \u2014 updating\u2026")
                self._html_timer.start()
            return
        try:
            if self.preview_out_chk.isChecked():
                r = self.recipe
                unit = preview_unit(src, r)
                self.preview.set_image(pil_to_qimage(render_unit(unit, r, keep_alpha=True)))
            else:
                arr = render(src, src.current, None, None, self.recipe.display)
                self.preview.set_image(to_qimage(arr))
            self.info_label.setText(f"{src.path}   ·   {src.describe()}")
        except Exception as ex:
            self.preview.set_image(None, f"Could not render this frame:\n{ex}")

    # ---------------- live HTML preview ----------------
    def _build_html_preview(self):
        src = self.current_source()
        if self.web is None or not src or self.recipe.output != "html":
            return
        if self._html_busy:
            self._html_pending = True
            return
        import tempfile

        from .plan import Frame, Job

        self._html_gen += 1
        self._html_flip ^= 1
        path = os.path.join(tempfile.gettempdir(), f"ImageStudios_preview_{os.getpid()}_{self._html_flip}.html")
        r = copy.copy(self.recipe)
        r.html = copy.deepcopy(self.recipe.html)
        r.display = copy.copy(self.recipe.display)
        r.rules = copy.deepcopy(self.recipe.rules)
        job = Job(path, "html", [Frame(src, {"M": src.current.get("M", 0)}, {}, None)], src.name)
        self._html_busy = True
        self._html_pending = False
        self._html_thread = QThread(self)
        self._html_worker = HtmlPreviewWorker(self._html_gen, job, r, self._html_cache)
        self._html_worker.moveToThread(self._html_thread)
        self._html_thread.started.connect(self._html_worker.run)
        self._html_worker.done.connect(self._on_html_preview_done)
        self._html_thread.start()

    def _on_html_preview_done(self, gen, path, err):
        self._html_thread.quit()
        self._html_thread.wait()
        self._html_thread = None
        self._html_busy = False
        if self._html_pending:
            self._html_timer.start(10)
            return
        if err:
            self.web_status.setText(f"Preview failed: {err}")
            return
        if gen == self._html_gen and self.recipe.output == "html":
            self.web.load(QUrl.fromLocalFile(path))
            self.web_status.setText("Live preview of the HTML page (current position only; the exported page "
                                    "holds every position in the range). Changes to the format update it.")

    def _toggle_play(self, axis, on, btn):
        if on:
            if self._play_axis and self._play_axis != axis and self._play_axis in self._axis_widgets:
                self._axis_widgets[self._play_axis][1].setChecked(False)
            self._play_axis = axis
            self._play_timer.start(max(5, int(1000 / max(self.recipe.fps, 0.1))))
            btn.setText("❚❚")
        else:
            if self._play_axis == axis:
                self._play_timer.stop()
                self._play_axis = None
            btn.setText("▶")

    def _stop_play(self):
        self._play_timer.stop()
        self._play_axis = None

    def _play_step(self):
        w = getattr(self, "_axis_widgets", {}).get(self._play_axis)
        if not w:
            self._stop_play()
            return
        sl = w[0]
        sl.setValue((sl.value() + 1) % (sl.maximum() + 1))
        self._play_timer.setInterval(max(5, int(1000 / max(self.recipe.fps, 0.1))))

    # ---------------- plan ----------------
    def refresh_plan(self):
        self.plan_tree.clear()
        if not self.sources:
            self.jobs = []
            self.plan_label.setText("Proposed batch")
            self.export_btn.setEnabled(False)
            self.warn_label.hide()
            return
        try:
            self.jobs, warns = build_plan(self.sources, self.recipe)
        except Exception as ex:
            self.jobs, warns = [], [f"Could not build plan: {ex}"]
        nframes = sum(len(j.frames) for j in self.jobs)
        cap = 3000
        items = []
        for j in self.jobs[:cap]:
            it = QTreeWidgetItem([os.path.basename(j.out_path), str(len(j.frames)), j.label,
                                  os.path.dirname(j.out_path)])
            it.setToolTip(0, j.out_path)
            items.append(it)
        self.plan_tree.addTopLevelItems(items)
        if len(self.jobs) > cap:
            self.plan_tree.addTopLevelItem(QTreeWidgetItem([f"… and {len(self.jobs) - cap} more", "", "", ""]))
        self.plan_label.setText(f"Proposed batch — {len(self.jobs)} file(s), {nframes} frame(s) to render")
        if not self.recipe.out_dir and not self.recipe.beside_source and self.jobs:
            warns = ["No export folder set: files will be written next to each source file."] + warns
        if warns:
            uniq = list(dict.fromkeys(warns))
            self.warn_label.setText("⚠ " + "\n⚠ ".join(uniq[:6]) + (f"\n… {len(uniq) - 6} more" if len(uniq) > 6 else ""))
            self.warn_label.show()
        else:
            self.warn_label.hide()
        self.export_btn.setEnabled(bool(self.jobs) and self._thread is None)
        self.export_btn.setText(f"Export {len(self.jobs)} file(s)" if self.jobs else "Export")

    # ---------------- export ----------------
    def start_export(self):
        self.refresh_plan()
        if not self.jobs or self._thread:
            return
        existing = [j.out_path for j in self.jobs if os.path.exists(j.out_path)]
        if existing:
            res = QMessageBox.question(
                self, "Overwrite files?",
                f"{len(existing)} output file(s) already exist, e.g.\n{existing[0]}\n\nOverwrite them?")
            if res != QMessageBox.Yes:
                return
        self._save_settings()
        recipe = copy.copy(self.recipe)
        recipe.display = copy.copy(self.recipe.display)
        self._thread = QThread(self)
        self._worker = ExportWorker(list(self.jobs), recipe)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self.progress.setRange(0, max(1, sum(len(j.frames) for j in self.jobs)))
        self.progress.setValue(0)
        self.progress.show()
        self.cancel_btn.show()
        self.export_btn.setEnabled(False)
        self.right_panel.setEnabled(False)
        self.act_remove.setEnabled(False)
        self.act_clear.setEnabled(False)
        self._t_start = time.time()
        self._thread.start()

    def _on_progress(self, done, total, name):
        self.progress.setMaximum(max(1, total))
        self.progress.setValue(done)
        el = time.time() - self._t_start
        eta = (el / done * (total - done)) if done else 0
        self.progress.setFormat(f"{done}/{total} frames  ·  {name}  ·  ~{eta:.0f}s left")

    def cancel_export(self):
        if self._worker:
            self._worker.cancel()
            self.cancel_btn.setEnabled(False)

    def _on_finished(self, ok, errors, cancelled, secs):
        self._thread.quit()
        self._thread.wait()
        self._thread = None
        self._worker = None
        self.progress.hide()
        self.cancel_btn.hide()
        self.cancel_btn.setEnabled(True)
        self.right_panel.setEnabled(True)
        self.act_remove.setEnabled(True)
        self.act_clear.setEnabled(True)
        self.refresh_plan()
        msg = f"{'Cancelled — ' if cancelled else ''}{ok} file(s) written in {secs:.1f}s"
        self.statusBar().showMessage(msg, 15000)
        if errors:
            QMessageBox.warning(self, "Export finished with errors", msg + "\n\n" + "\n".join(errors[:25]))
        elif not cancelled:
            box = QMessageBox(self)
            box.setWindowTitle("Export complete")
            box.setText(msg)
            open_btn = box.addButton("Open folder", QMessageBox.AcceptRole)
            box.addButton(QMessageBox.Close)
            box.exec()
            if box.clickedButton() is open_btn:
                self._open_out_dir()

    def closeEvent(self, e):
        if self._worker:
            self._worker.cancel()
        if self._thread:
            self._thread.quit()
            self._thread.wait(3000)
        self._save_settings()
        for s in self.sources:
            s.close()
        super().closeEvent(e)


# ---------------------------------------------------------------------------
STYLE = f"""
QWidget {{ font-size: 13px; }}
QMainWindow, QScrollArea > QWidget > QWidget {{ background: #1e1f25; }}
QToolBar {{ background: #24262d; border: none; padding: 4px; spacing: 6px; }}
QToolBar QToolButton {{ padding: 4px 8px; border-radius: 6px; color: #dfe3ee; }}
QToolBar QToolButton:hover {{ background: #33363f; }}
QLabel#h {{ font-weight: 600; font-size: 14px; color: #dfe3ee; padding: 2px 0 4px 0; }}
QLabel#hint {{ color: #868b99; font-size: 12px; }}
QLabel#warn {{ color: #f0b45a; font-size: 12px; }}
QGroupBox {{ border: 1px solid #33363f; border-radius: 10px; margin-top: 14px; padding: 10px 8px 8px 8px;
            background: #23252c; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; color: #aeb6d6; font-weight: 600; }}
QListWidget, QTreeWidget, QTableWidget {{ background: #1a1b20; border: 1px solid #30333b; border-radius: 8px; }}
QListWidget::item {{ padding: 4px; border-radius: 6px; color: #dfe3ee; }}
QListWidget::item:selected {{ background: #2f3a66; }}
QTreeWidget::item {{ padding: 2px; }}
QHeaderView::section {{ background: #24262d; color: #aeb6d6; border: none; padding: 4px 6px; }}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{ background: #17181d; border: 1px solid #3a3d47; border-radius: 6px;
            padding: 4px 6px; color: #e6e9f2; min-height: 18px; }}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{ border-color: {ACCENT}; }}
QTableWidget QComboBox, QTableWidget QLineEdit {{ border-radius: 4px; margin: 2px; }}
QPushButton {{ background: #2d3039; border: 1px solid #3a3d47; border-radius: 7px; padding: 6px 12px; color: #e6e9f2; }}
QPushButton:hover {{ background: #363a45; }}
QPushButton:disabled {{ color: #6b7080; }}
QPushButton#primary {{ background: {ACCENT}; border: none; color: white; font-weight: 600; padding: 7px 18px; }}
QPushButton#primary:hover {{ background: #7f9bff; }}
QPushButton#primary:disabled {{ background: #3a4060; color: #9aa0b5; }}
QSlider::groove:horizontal {{ height: 4px; background: #3a3d47; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {ACCENT}; width: 14px; margin: -6px 0; border-radius: 7px; }}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 2px; }}
QProgressBar {{ background: #17181d; border: 1px solid #3a3d47; border-radius: 6px; text-align: center; color: #e6e9f2; height: 20px; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 5px; }}
QSplitter::handle {{ background: #1e1f25; }}
QStatusBar {{ background: #24262d; color: #9aa0b5; }}
"""


def run(argv=None):
    argv = sys.argv if argv is None else argv
    QApplication.setApplicationName("ImageStudios")
    QApplication.setOrganizationName("ImageStudios")
    QApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
    app = QApplication.instance() or QApplication(argv)
    app.setStyle("Fusion")
    pal = QPalette()
    for role, col in [(QPalette.Window, "#1e1f25"), (QPalette.WindowText, "#e6e9f2"), (QPalette.Base, "#17181d"),
                      (QPalette.AlternateBase, "#22242b"), (QPalette.Text, "#e6e9f2"), (QPalette.Button, "#2d3039"),
                      (QPalette.ButtonText, "#e6e9f2"), (QPalette.Highlight, ACCENT),
                      (QPalette.HighlightedText, "#ffffff"), (QPalette.ToolTipBase, "#2d3039"),
                      (QPalette.ToolTipText, "#e6e9f2"), (QPalette.PlaceholderText, "#6b7080")]:
        pal.setColor(role, QColor(col))
    app.setPalette(pal)
    app.setStyleSheet(STYLE)
    app._wheel_guard = WheelGuard(app)
    app.installEventFilter(app._wheel_guard)
    app.setWindowIcon(app_icon())
    w = MainWindow()
    w.showMaximized()
    files = [a for a in argv[1:] if os.path.exists(a)]
    if files:
        QTimer.singleShot(50, lambda: w.add_paths(files))
    return app.exec()
