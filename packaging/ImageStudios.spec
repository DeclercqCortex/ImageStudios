# PyInstaller spec — build with:  .venv\Scripts\pyinstaller.exe packaging\ImageStudios.spec --noconfirm
import os

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

datas = []
datas += collect_data_files("imageio_ffmpeg")          # bundled ffmpeg.exe
datas += collect_data_files("dask")                    # dask.yaml config (used by nd2)
datas += collect_data_files("nd2")
datas += collect_data_files("ome_types")
binaries = collect_dynamic_libs("pypdfium2_raw") + collect_dynamic_libs("pillow_heif")
hidden = (collect_submodules("nd2") + collect_submodules("imagecodecs")
          + ["pypdfium2", "pypdfium2_raw", "pillow_heif", "PySide6.QtSvg",
             "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebChannel"])

excludes = [
    # Qt WebEngine (and the Qml/Quick/WebChannel modules it needs) stays: it powers the live HTML preview.
    "PySide6.Qt3DCore", "PySide6.QtMultimedia", "PySide6.QtCharts", "PySide6.QtDataVisualization",
    "PySide6.QtBluetooth", "PySide6.QtNetworkAuth", "PySide6.QtSql", "PySide6.QtTest",
    "tkinter", "matplotlib", "IPython", "pytest",
]

a = Analysis(
    [os.path.join(ROOT, "ImageStudios.pyw")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hidden,
    excludes=excludes,
    noarchive=False,
)


def _keep(entry):
    """Drop WebEngine extras the live preview never uses (dev tools, other languages, QML)."""
    path = entry[0].replace("\\", "/").lower()
    if "devtools" in path or path.endswith(".debug.pak"):
        return False
    if "/translations/" in path and not ("en-us" in path or path.endswith("_en.qm")):
        return False
    if "/qml/" in path:
        return False
    return True


a.datas = [d for d in a.datas if _keep(d)]
a.binaries = [b for b in a.binaries if "/qml/" not in b[0].replace("\\", "/").lower()]
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="ImageStudios",
    icon=os.path.join(SPECPATH, "ImageStudios.ico"),
    console=False,
    version=None,
)
coll = COLLECT(exe, a.binaries, a.datas, name="ImageStudios", strip=False, upx=False)
