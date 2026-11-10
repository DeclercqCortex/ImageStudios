"""Render the app icon (same artwork as the in-app icon) to packaging/ImageStudios.ico."""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image
from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtWidgets import QApplication

app = QApplication([])
from imagestudios.gui import app_icon  # noqa: E402

pm = app_icon().pixmap(256, 256)
buf = QBuffer()
buf.open(QIODevice.WriteOnly)
pm.save(buf, "PNG")
here = os.path.dirname(os.path.abspath(__file__))
png = os.path.join(here, "icon.png")
with open(png, "wb") as fh:
    fh.write(bytes(buf.data()))
Image.open(png).save(os.path.join(here, "ImageStudios.ico"),
                     sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("icon written")
