# ImageStudios

Batch converter for images, microscopy stacks, vector graphics, PDFs and videos.
Load as many files as you like, choose what to make, review the proposed batch (every output file name is listed before anything is written), then export.

## Run it

Use the **ImageStudios** shortcut on the Desktop or in the Start menu. It points to `dist\ImageStudios\ImageStudios.exe`, a standalone build that doesn't need Python. You can also drop files onto the exe or onto the window.
From source: double-click **`ImageStudios.bat`**.

To rebuild the exe after code changes:

```bash
.venv\Scripts\pyinstaller.exe packaging\ImageStudios.spec --noconfirm --distpath dist --workpath build
```

Check a build without opening the window: `dist\ImageStudios\ImageStudios.exe --selftest <out-folder> <files…>` writes `selftest.txt` to the output folder.

First-time setup on a new machine (Python 3.10–3.13):

```bash
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## What it reads

| Input | Axes exposed |
|---|---|
| **ND2** (Nikon) | T (time), M (multipoint/position), Z, C (with channel names and colours from metadata) |
| **TIFF / OME-TIFF / ImageJ hyperstacks** | T, M (OME series), Z, C (OME channel names, ImageJ LUT colours), I (frames of unlabelled multi-page TIFFs) |
| **SVG / SVGZ** | rendered at any scale (the SVG render scale setting) |
| **PDF** | P (pages), rendered at a chosen DPI |
| **PNG, JPEG, BMP, WebP, HEIC/AVIF, JP2, PSD, TGA, ICO…** | single image; animated GIF / WebP / APNG give a T axis |
| **MP4, MOV, AVI, MKV, WebM…** | T (frames) |

## What it makes

* **Image files**: PNG, JPEG, TIFF (8-bit rendered), **TIFF raw** (original bit depth, multi-channel ImageJ TIFF when channels are merged), WebP, BMP.
* **Animation / video**: GIF, MP4 (H.264), animated WebP. Each one plays through one axis at a fixed frame rate (for example scrubbing through Z, or a time-lapse along T).
* **PDF document**: one page per frame. Use one PDF per file, or tick *Combine all files* to chain everything into a single PDF in list order (drag files to reorder).

## Axis handling (applies to every loaded file that has that axis)

| Mode | Meaning |
|---|---|
| Iterate | one output per index, e.g. `cells_M02_T015_Z07.png` |
| Fixed index | a single index; `current` = the slider position for each file |
| Max projection | maximum-intensity projection over the range |
| Animate | the frames of the GIF/MP4 run along this axis |
| Merge channels (C only) | overlay the visible channels with their colours |

Ranges are 1-based: `all`, `current`, `5`, `1-10`, `1-100:5` (every 5th), `3, 7, 9`, `last`.

**File names** use the template `{name}{auto}` by default: `{auto}` adds one `_<axis><index>` part for each iterated axis, zero-padded to the axis size, plus the channel name for channels. Custom templates can use `{name} {t} {m} {z} {c} {p} {i} {cname}`, for example `{name}_t{t}_z{z}`.

## Microscopy metadata

ND2 and TIFF (OME-TIFF, ImageJ) metadata is read automatically:

* pixel size (µm/px), Z step, per-frame timestamps (ND2: every frame of every multipoint position has its own time), frame interval
* position names, channel names and colours, objective, NA, zoom, emission wavelengths, bit depth and acquisition date. Click **Metadata…** under the preview to see them all.

The pixel size, frame interval and Z step appear under the preview and can be corrected there. **Reset** restores the file's values. The **◐** button next to a channel sets its display range (min/max) by hand.

## Annotations

Burned into exported images, panels, GIFs/MP4s and PDFs, each in a chosen corner:

* **Time stamp**: elapsed time from the metadata. Formats: auto, hh:mm:ss, mm:ss, s, min, h, d. Choose whether t = 0 is the first frame of each position or the start of acquisition, shift time zero (e.g. treatment at 30 min), and add a prefix such as `t = `.
* **Scale bar**: automatic "nice" length (about 20 % of the width) or a fixed length in µm, with an optional label. Its thickness is adjustable, and it is drawn after resizing, so it stays accurate.
* **Z depth** (µm), **channel names** (in their colours), **position name**, **file name**, and **custom text** with `{name} {pos} {time} {cname}`.
* Text size (% of the image), colour (white/black/yellow) and outline.

The mouse wheel never changes dropdowns, number boxes or sliders. It scrolls the settings sidebar instead. The window opens maximized, and the sidebar always keeps its full width.

In panels, an annotation tied to a laid-out axis appears on every tile. For example, channel names go on each channel tile and times on each time-point tile. Other annotations appear once per file, and the scale bar goes on the last tile.

## Panels (m × n montages)

Panels are set up in the **Panel** settings box, not under Axes:

1. **Make a panel of**: pick the axis to lay out as tiles, i.e. channels, Z-slices, time points, positions or pages. Pick **Files (side by side)** to put the loaded files next to each other.
2. **Layout**: how many images go in each row (or each column). *auto* puts up to 4 images in one row and makes a near-square grid for more, e.g. 9 Z-slices in 3 × 3. The resulting grid is shown below the setting.
3. The panel axis's **range** under Axes picks which images go in, e.g. `1-41:10`. Other axes still decide how many panels you get, for example one panel per time point.

For channels, a merged tile is added automatically. Panels work for image files, PDFs and animations; an MP4 of a channel panel playing through time is one example.

## Interactive HTML viewer

Choose **Make → Interactive HTML viewer** to get one self-contained `.html` file per input file. It works offline in any current browser, so you can email or share it. The original intensities are embedded as compressed raw 8/16-bit data, so LUT changes and the pixel inspector work on true values. In the viewer:

* **Sliders** for time, Z and position, with play/pause, frame rate and loop. Arrow keys step through time and Z, PgUp/PgDn through positions, and Space plays or pauses.
* **Position gallery**: thumbnails of every multipoint position; click one to open it.
* **Channel panel**: each channel in its own tile plus a merged tile, with tiles per row adjustable. Zoom (mouse wheel) and pan (drag) stay in sync across all tiles, and a minimap shows the visible area.
* **LUT editor per channel**: a histogram of the frame on screen (or of the projection) that updates as you scrub or play, with that frame's min/max/mean. It has draggable min/max handles, gamma, a colour picker and colour maps (colour, grey, fire, viridis, inverted). **Auto (this frame)** stretches to the current frame, **Auto contrast on every frame** re-stretches while playing, and **Full range** shows everything.
* **Projections**: mean, max or min over time or Z, computed live.
* **Orthogonal XZ/YZ views** for Z stacks, scaled by the real Z step. Click to move the crosshair.
* **Overlays**: scale bar, time stamp, Z depth, channel and position names, each with an on/off toggle, plus a **Metadata** window.
* **Pixel inspector**: hover to see x/y in pixels and µm and the raw value of every channel.
* **Ruler** (distance in µm) and **Snapshot** (saves the current view as a PNG).

**Live preview.** With HTML chosen, the preview area shows the real page as it will be exported, for the position selected in ImageStudios. It rebuilds within a second or two whenever you change the format, the axis ranges, channel colours or the selected position. The exported page contains every position in the range.

**Panels in the page.** The page's tiles come from the same **Panel** box as an image panel, and they are fixed: viewers can't rearrange them.
* *Make a panel of* sets the axis: channels (+ merged tile), time points, Z-slices or positions.
* *Layout* sets N images per row or per column (auto = up to 4 in one row, else near-square).
* *Spacing* and *Background* are applied too.
* The panel axis reads "In panel" under Axes, and its range picks the tiles, e.g. `1-41:10`.
* Every tile stays live: scrubbing or playing the other axes, LUTs, projections, zoom/pan and the pixel inspector apply to all tiles. Each tile is labelled with its own time, Z depth or position.
* **Pages.** For HTML, the Panel box has a *rows × columns per page* grid for each axis (positions, time points, Z-slices; auto = everything on one page). The page makes as many pages as needed: with 74 positions at 3 × 3 there are 9 pages, turned with the ◀ ▶ pager or PgUp/PgDn. The last page keeps the same tile size.
* With a panel, the left-hand position gallery is left out (the panel replaces it).

**Interacting with a panel**
* **Click** a tile: the LUT histograms and stats switch to it.
* **Double-click** a tile: it opens alone in a popup above the dimmed panel, with a breadcrumb such as *Positions panel › C6_0007*. You can scrub, play, zoom and measure there, and the position slider flips to other positions.
* **▦ Time points panel** (or **Z-slices panel**) in the popup replaces it with that position laid out over time, using the time grid from ImageStudios. It has its own pages, and double-clicking one of its tiles opens that frame alone.
* **✕ Back**, Esc, or a click outside the popup returns to the original panel, on the same page with the same selection.

**LUT histograms in panels** (*HTML viewer format → LUT histograms*):
* **For the selected tile**: click a tile (a position or time point) and the LUT editor's histograms and stats switch to that tile's frame. The selected tile is outlined.
* **Beside every tile**: each tile gets its own small histogram per channel next to it, drawn against the shared LUT window with min/max marked, plus the tile's mean.

**Formatting the page.** With HTML chosen, the *HTML viewer format* box decides what the page offers. The tools listed above are the full set; each can be switched off:

* **Start from** a preset:
  * *Full explorer*: every tool.
  * *Movie player*: playback, gallery, zoom, snapshot and metadata; it autoplays.
  * *Interactive figure*: zoom, pixel inspector, ruler and snapshot only.
* **Tools in the page**: tick exactly what to include: play controls, gallery, LUT editor, projections, ortho views, zoom & pan, pixel inspector, ruler, snapshot, metadata, overlay switches. Changing a tick makes the preset *Custom*.
* **Layout**: channel tiles + merge, merged image only, or channel tiles only, plus tiles per row.
* **Overlays shown**: scale bar, time, Z, channel and position names.
* **Title** (`{name}` = file name), **caption**, and a **dark or light theme**.
* **Opens at** the first frame or at the current slider position, optionally autoplaying, at the chosen frame rate. **Auto contrast on every frame** can be on from the start.

The axis ranges in ImageStudios choose what goes into the viewer. If the raw data is bigger than the *data size limit* (400 MB by default), it is binned 2×2, 4×4 and so on, and the viewer says so.

## Image size

**Automatic** (default): small microscope images are enlarged by a whole-number factor so pixels stay crisp, e.g. 64 px tiles become 512 px, or at least 256 px each in a panel. Large outputs are kept within 4096 px. The factor used for the selected file is shown next to the setting.
**Manual**: your own percentage.

## Export folder

Everything is saved to one export folder, `Pictures\ImageStudios` by default. It is shown next to the Export button, where **Change…** picks a new one and **Open** opens it, and the choice is remembered. Alternatively, save next to each source file, optionally in one subfolder per file.

**Display**: the contrast is auto-stretched consistently across the whole stack by default (percentiles sampled from many planes), so animations don't flicker. *Per frame* and *Full bit-depth* modes are also available. Click a channel's colour square to recolour it, and untick a channel to leave it out of merged outputs.

## Develop

```
imagestudios/sources.py   readers -> Source objects with named axes
imagestudios/render.py    raw planes -> 8-bit RGB (contrast, channel colours, projections)
imagestudios/plan.py      Recipe + build_plan(): the proposed batch with output names
imagestudios/export.py    writers (Pillow, tifffile, ffmpeg via imageio-ffmpeg)
imagestudios/gui.py       PySide6 window
```

Test: `.venv\Scripts\python.exe -m tests.test_pipeline`
