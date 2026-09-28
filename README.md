<div align="center">

# 🖨️ Bambu2AD5X

### Turn **any** 3MF into an **AD5X-ready OrcaSlicer project** in one click

*MakerWorld · Bambu Studio · OrcaSlicer · Printables (PrusaSlicer) → Flashforge AD5X*

![Platform](https://img.shields.io/badge/platform-Windows%2011-0078D6?style=for-the-badge&logo=windows&logoColor=white)
![Python](https://img.shields.io/badge/python-3.8+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![OrcaSlicer](https://img.shields.io/badge/OrcaSlicer-2.4.2-2ea44f?style=for-the-badge)
![Dependencies](https://img.shields.io/badge/core%20deps-none-brightgreen?style=for-the-badge)

<br>

<img src="docs/hero.png" alt="Bambu2AD5X - turn any 3MF into an AD5X-ready OrcaSlicer project" width="900">

</div>

---

## 📢 Important: please read

> ### 🧪 Current testing status
> | | Status |
> |---|---|
> | **Printer** | ✅ Flashforge **AD5X** only |
> | **OS** | ✅ **Windows 11** only |
> | **Linux / macOS** | ❌ Not tested. **Contributors wanted!** |
> | **Other Flashforge machines** | ❓ Untested, should work as a starting point |
>
> ### 🤝 Help make this better
> This is a community project, so it *will* have bugs and gaps. If you find:
> - 🐛 **a bug** or a file that fails to convert,
> - 💡 **an improvement**, or
> - 🔍 **a value that is not consistent with the author's original settings or with what the AD5X actually does**,
>
> please **[open an issue](../../issues)** or, even better, **[send a pull request](../../pulls)**. Getting every value right for both the author's intent *and* real printer behaviour is the main goal, and it needs many eyes and many test files.
>
> ### 🐧 Linux & macOS
> The conversion engine is pure Python (standard library only) and the GUI uses Tkinter, so it *should* run on Linux and macOS with `python bambu2ad5x_gui.py`. But nobody has tested it, and the build scripts are Windows-only (`.bat`). If you can test or add a `build_exe.sh` / AppImage / macOS build, **please contribute!**

---

## ✨ What is this?

You found a great model on **MakerWorld** or **Printables**, but the project file was made for a Bambu Lab printer (or PrusaSlicer). Opening it in OrcaSlicer with a Flashforge AD5X gives you the wrong printer profile, wrong G-code, wrong speeds, and usually loses the author's carefully tuned settings.

**Bambu2AD5X** fixes that. Drop in a `.3mf`, click **Convert**, and get a new project that:

- ✅ Uses the **Flashforge AD5X 0.4 nozzle** machine profile (start/end G-code, limits, build area)
- ✅ **Keeps the author's settings**: layers, walls, infill, supports, seam, brim, ironing, fuzzy skin, temperatures, colours, painted colours/supports/seams
- ✅ Uses **AD5X-appropriate speeds**, matched to the layer height
- ✅ Picks the right **AD5X filament preset** by material type (PLA → PLA Basic, PETG → PETG Pro, ...)
- ✅ Opens straight in **OrcaSlicer 2.4.2**, ready to slice

> **Tested on the Flashforge AD5X.** It should also work as a starting point for other Flashforge machines (see [Other Flashforge machines](#-other-flashforge-machines)).

---

## 📥 Download

Grab the ready-to-run **`Bambu2AD5X.exe`** from the [**Releases**](../../releases) page.
It is a single file, needs no installation and no Python, and has everything built in. Just double-click it.

Prefer to build it yourself? See [Build from source](#-build-from-source).

---

## 🚀 How to use

1. **Add files**: click *Add files*, or **drag & drop** `.3mf` files / whole folders into the window.
2. **Tick** the ones you want to convert (or *Check all*).
3. **Choose the output**: next to each file, into a folder, or replace the originals.
4. Click **Convert**.
5. In **OrcaSlicer 2.4.2**, open the result with **`File → Open Project`**.

> ⚠️ **Do not drag the converted file into OrcaSlicer.** Use *File → Open Project*, otherwise the project profile may not load correctly.

---

## 🧩 Supported sources

| Source | How to get the file | Status |
|---|---|---|
| **MakerWorld** | Download the *print profile* 3MF | ✅ |
| **Bambu Studio** projects | Saved `.3mf` project | ✅ |
| **OrcaSlicer** projects | Saved `.3mf` project | ✅ |
| **Printables** | Open the model → **Download** the project the designer saved in PrusaSlicer | ✅ |
| Creality Cloud, Snapmaker Space, makeronline, Meshy ... | Any Bambu/Orca-style project 3MF | ✅ (should work) |

> A plain mesh-only 3MF (no slicer project inside) has no settings to carry over. The geometry still works, but there is nothing to preserve.

---

## 🎛️ Features

### 🖥️ Modern GUI
- Gradient header, cards, rounded buttons, **light + dark mode** (follows Windows on first run)
- **Big live preview** with chips: source, layer height, filaments + material
- Shows *"Bambu Lab P1S → Flashforge AD5X"*, warnings, and the exact output path
- File list with **thumbnails**, sortable columns, **live search**, filters (*All / Ready / Converted / Can't convert*)
- **Right-click menu**: tick, show in folder, copy path, remove
- **Drag & drop** files and folders
- Files are read in the **background**, so big folders never freeze the window
- Built-in log panel, progress bar, total time, and an *Open output folder* button
- Remembers window size and all your settings
- **"How it works"** window and tooltips on every option

### ⚙️ Conversion engine
- Rebuilds `different_settings_to_system` so OrcaSlicer **keeps the author's values** instead of silently swapping in system defaults
- Machine half (printer profile, G-code, limits, build area) comes from an AD5X template; the author's half is copied over
- **Speeds always replaced by AD5X values**, matched to the layer height (interpolated between 0.16 / 0.20 / 0.24)
- **Drops unused filaments** (like the web converter) and renumbers everything consistently
- **Prime tower** follows the model, and you get a warning if it would overlap the object
- Model is centred by its **real bounding box**
- Temperatures are capped to AD5X limits (nozzle 280 °C, bed 110 °C)
- Geometry, painted colours, supports and seams are **never touched** (bit-for-bit)
- Optional `.report.txt` listing what was kept, replaced and discarded

### ⌨️ Shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+O` | Add files |
| `Ctrl+A` | Check all shown |
| `Ctrl+Enter` | Convert |
| `F5` | Rescan |
| `Ctrl+F` | Search |
| `Ctrl+L` | Toggle log |
| `Space` | Tick / untick |
| `Del` | Remove from list |

---

## 🛠️ Build from source

You need **Windows** (tested on Windows 11) and **Python 3.8+** ([python.org](https://www.python.org/downloads/), tick *"Add python.exe to PATH"*).

```bat
git clone https://github.com/iChristGit/3MF-to-AD5X.git
cd 3MF-to-AD5X
build_exe.bat
```

`build_exe.bat` installs PyInstaller (plus the optional extras), builds the exe in about a minute, and leaves **`Bambu2AD5X.exe`** in the folder. You can copy that one file anywhere.

**Just want to run it without building?**

```bat
run_gui.bat
```

**Optional extras** (auto-detected, the app works without them):

| Package | Gives you |
|---|---|
| `pillow` | Smooth, larger previews and row thumbnails |
| `tkinterdnd2` | Drag & drop |

```bat
pip install pillow tkinterdnd2
```

---

## 💻 Command line

The converter also works without the GUI, using only the Python standard library:

```bash
python bambu2ad5x.py model.3mf                       # -> model_AD5X.3mf (+ .report.txt)
python bambu2ad5x.py *.3mf                           # batch convert
python bambu2ad5x.py model.3mf -o out.3mf            # custom output (single input)
python bambu2ad5x.py model.3mf --overwrite           # replace the original (safe swap)
python bambu2ad5x.py model.3mf --keep-unused-filaments
python bambu2ad5x.py model.3mf --template my_ad5x_project.3mf
```

| Option | Description |
|---|---|
| `-o, --output` | Output file (single input only) |
| `--template` | Use your own AD5X project as the machine template |
| `--report` | Write a `.report.txt` next to the output |
| `--overwrite` | Replace the original. Built in a temp file and swapped in only on success, so a failure never damages your file |
| `--keep-unused-filaments` | Don't remove filaments the model doesn't use |

---

## 🔬 How it works

OrcaSlicer loads a project's print/filament/printer preset **by name**. For every key that is *not* listed in `different_settings_to_system`, it silently swaps in the installed system preset's value, so the author's tuning gets lost.

Bambu2AD5X:

1. Takes the **machine half** (printer profile, G-code, limits, build area) from a bundled **AD5X template** (`ad5x_template.json`).
2. Copies the **author's half** (layers, walls, infill, supports, seam, brim, ironing, fuzzy skin, prime tower, temperatures, colours, painting).
3. Rebuilds `different_settings_to_system` so Orca **keeps** those values.
4. Replaces speeds with AD5X-appropriate ones for the layer height, removes unused filaments, repositions the prime tower.
5. Writes a new `.3mf` and leaves the geometry untouched.

### Speeds by layer height

| Layer | Sparse infill | Internal solid | Gap infill |
|---|---|---|---|
| 0.16 mm | 330 | 300 | 200 |
| 0.20 mm | 270 | 250 | 200 |
| 0.24 mm | 230 | 230 | 180 |

Heights in between are interpolated; outside 0.16–0.24 the nearest preset is used and a note is added.

### Printables / PrusaSlicer files
Settings are mapped to Orca names (walls, infill, supports, seam, brim, ironing, temps, bed temps, colours, per-object/part extruders, painted colours/supports/seam). Modifier and support-blocker volumes are skipped and reported.

---

## 🧵 Other Flashforge machines

Built and tested for the **AD5X** on **Windows 11** only. Other Flashforge printers should work as a starting point, but bed size, limits and G-code may differ. To target a different machine, save an empty project for it in OrcaSlicer and pass it with `--template my_project.3mf`. Please report how it goes in the Issues tab.

---

## ❓ Troubleshooting

| Problem | Fix |
|---|---|
| Result looks wrong when dragged into Orca | Use **File → Open Project** instead |
| "Replace original" fails | Close the file in OrcaSlicer first |
| No drag & drop | `pip install tkinterdnd2` and rebuild |
| Blurry / no thumbnails | `pip install pillow` and rebuild |
| Build says Python not found | Reinstall Python with *Add to PATH* ticked |
| Windows SmartScreen warns about the exe | It's an unsigned PyInstaller build. Build it yourself from source if you prefer |

---

## 📁 Project structure

```
3MF-to-AD5X/
├── docs/
│   ├── hero.png           # README banner
│   └── screenshot.png     # app screenshot
├── bambu2ad5x.py          # conversion engine (stdlib only) + CLI
├── bambu2ad5x_gui.py      # Tkinter GUI
├── ad5x_template.json     # AD5X 0.4 nozzle machine template
├── build_exe.bat          # builds Bambu2AD5X.exe with PyInstaller
├── run_gui.bat            # runs the GUI without building
├── LICENSE
└── README.md
```

---

## 🤝 Contributing

Contributions of any size are welcome, from a typo to a whole new platform build.

**Good ways to help:**
- 🧪 **Test more files**: convert models from different sources and check the result in OrcaSlicer 2.4.2. Report anything that looks off.
- 🔍 **Verify values**: compare converted settings against the author's original *and* against real AD5X behaviour (speeds, temperatures, G-code, flush volumes, prime tower). Wrong or inconsistent values are the most valuable bugs to report.
- 🐧 **Linux / macOS support**: testing, fixes, and build scripts.
- 🖨️ **Other Flashforge printers**: templates and test results.
- 🌍 **Docs & translations**.

**When opening an issue, please include:**
1. Where the 3MF came from (MakerWorld, Printables, ...) and a link if possible
2. Your OS and Python version (or that you used the exe)
3. What you expected vs what happened
4. The generated `.report.txt` and the log output

**Pull requests:** keep the engine (`bambu2ad5x.py`) dependency-free, and mention which printer/OS/files you tested with.

---

## 📄 License

Released under the [MIT License](LICENSE).

---

## 🙏 Credits

- 🌐 **[ForgeBridge](https://forgebridge.app)**: the website that inspired this project and can also convert files online. Go check it out!
- 🤖 Vibe coded with [Claude](https://claude.ai).
- 🧡 **[OrcaSlicer](https://github.com/SoftFever/OrcaSlicer)** for the slicer and its open Flashforge profiles.

---

## ⚠️ Disclaimer

This is an unofficial community tool, not affiliated with Flashforge, Bambu Lab, Prusa, OrcaSlicer or ForgeBridge. Converted profiles are a best effort: **always check the result in the slicer preview** before printing, and keep a backup of your originals (especially if you use *Replace originals*). Use at your own risk.

---

<div align="center">

**If this saved you time, drop a ⭐ on the repo!**

</div>
