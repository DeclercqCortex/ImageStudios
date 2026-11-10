import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def selftest(out_dir, files):
    """Headless check used to verify packaged builds: ImageStudios --selftest OUT FILE..."""
    import traceback

    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication(["x", "-platform", "offscreen"])
    from imagestudios.annotate import Annot
    from imagestudios.export import run_job
    from imagestudios.plan import AxisRule, Recipe, build_plan
    from imagestudios.sources import open_source

    os.makedirs(out_dir, exist_ok=True)
    lines, ok = [], True
    srcs = []
    for f in files:
        try:
            s = open_source(f)
            srcs.append(s)
            lines.append(f"open ok   {os.path.basename(f)}: {s.describe()}")
        except Exception:
            ok = False
            lines.append(f"open FAIL {f}\n{traceback.format_exc()}")
    recipes = [
        Recipe(output="images", fmt="png", out_dir=out_dir, rules={a: AxisRule("fixed", "1") for a in "MTZPI"}),
        Recipe(output="animation", fmt="mp4", out_dir=out_dir, rules={"M": AxisRule("fixed", "1")}),
        Recipe(output="animation", fmt="gif", out_dir=out_dir, combine=True, combined_name="selftest"),
        Recipe(output="images", fmt="png", out_dir=out_dir, template="{name}_annotated_panel",
               annot=Annot(timestamp=True, scalebar=True, channels=True, zpos=True, position=True),
               panel_axis="C", rules={a: AxisRule("fixed", "1") for a in "MTZPI"}),
        Recipe(output="html", fmt="html", out_dir=out_dir, rules={"M": AxisRule("iterate", "1-3")}),
        Recipe(output="pdf", out_dir=out_dir, combine=True, combined_name="selftest",
               rules={a: AxisRule("fixed", "1") for a in "MTZPI"}),
    ]
    for r in recipes:
        jobs, _ = build_plan(srcs, r)
        for j in jobs[:6]:
            try:
                run_job(j, r)
                lines.append(f"write ok  {os.path.basename(j.out_path)} ({os.path.getsize(j.out_path)} bytes)")
            except Exception:
                ok = False
                lines.append(f"write FAIL {j.out_path}\n{traceback.format_exc()}")
    lines.append("RESULT: " + ("PASS" if ok else "FAIL"))
    with open(os.path.join(out_dir, "selftest.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    return 0 if ok else 1


def selftest_web(out_dir, file):
    """Check the live HTML preview: build a preview page and load it in Qt WebEngine."""
    import json

    from PySide6.QtCore import QEventLoop, Qt, QTimer, QUrl
    from PySide6.QtWidgets import QApplication

    QApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
    app = QApplication.instance() or QApplication(["x"])
    from PySide6.QtWebEngineWidgets import QWebEngineView

    from imagestudios.html_export import write_html
    from imagestudios.plan import Frame, Job, Recipe
    from imagestudios.sources import open_source

    os.makedirs(out_dir, exist_ok=True)
    src = open_source(file)
    path = os.path.join(out_dir, "preview.html")
    write_html(Job(path, "html", [Frame(src, {"M": 0}, {}, None)], src.name), Recipe(output="html", fmt="html"),
               preview={"cache": {}})
    view = QWebEngineView()
    view.resize(900, 600)
    view.show()
    loop = QEventLoop()
    view.loadFinished.connect(loop.quit)
    view.load(QUrl.fromLocalFile(path))
    QTimer.singleShot(30000, loop.quit)
    loop.exec()
    res = {}
    for _ in range(40):
        QTimer.singleShot(250, loop.quit)
        loop.exec()
        view.page().runJavaScript("JSON.stringify({loaded: !!data, n: data ? data.length : 0, stats: "
                                  "ch.map(c => c.el ? c.el.stats.textContent : '')})", 0,
                                  lambda r: (res.__setitem__("v", r), loop.quit()))
        loop.exec()
        if res.get("v") and json.loads(res["v"]).get("loaded"):
            break
    ok = bool(res.get("v")) and json.loads(res["v"]).get("loaded")
    with open(os.path.join(out_dir, "selftest_web.txt"), "w", encoding="utf-8") as fh:
        fh.write(f"{res.get('v')}\nRESULT: {'PASS' if ok else 'FAIL'}\n")
    view.close()
    src.close()
    return 0 if ok else 1


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--selftest":
        raise SystemExit(selftest(sys.argv[2], sys.argv[3:]))
    if len(sys.argv) > 3 and sys.argv[1] == "--selftest-web":
        raise SystemExit(selftest_web(sys.argv[2], sys.argv[3]))
    from imagestudios.gui import run

    raise SystemExit(run())
