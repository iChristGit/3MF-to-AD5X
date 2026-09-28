#!/usr/bin/env python3
"""
Bambu2AD5X v1.0.0 - Turn any 3MF into an AD5X-ready OrcaSlicer project.

Bambu Studio / OrcaSlicer / MakerWorld  and  PrusaSlicer / Printables  .3mf  ->  Flashforge AD5X.

Keep together: bambu2ad5x.py  ad5x_template.json  bambu2ad5x_gui.py        Run: python bambu2ad5x_gui.py
Optional extras (auto-detected): pillow (smooth, larger previews), tkinterdnd2 (drag & drop files).
"""
import base64
import io
import json
import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from fractions import Fraction
from tkinter import filedialog, messagebox, ttk
from tkinter import font as tkfont

import bambu2ad5x as core

try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except Exception:
    HAS_PIL = False

APP = "Bambu2AD5X"
APP_VER = "v1.0.0"
HOME = os.path.expanduser("~")
DOWNLOADS = os.path.join(HOME, "Downloads")
IS_WIN = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"

if IS_WIN:                      # crisp text on high-DPI screens (must happen before the first Tk window)
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass


def _probe_dnd():
    """Drag & drop needs tkinterdnd2 AND its native tkdnd library to load; test once, fall back quietly."""
    try:
        from tkinterdnd2 import TkinterDnD
        r = TkinterDnD.Tk()
        r.withdraw()
        r.destroy()
        return TkinterDnD.Tk
    except Exception:
        return None


_DND_TK = _probe_dnd()
HAS_DND = _DND_TK is not None
_Base = _DND_TK or tk.Tk
if HAS_DND:
    from tkinterdnd2 import DND_FILES

# ------------------------------------------------------------------------------------------ palettes
LIGHT = dict(bg="#f4f5fa", card="#ffffff", card2="#f8f9fd", fg="#0f172a", muted="#64748b", border="#e2e5ef",
             accent="#4f46e5", accent_hover="#4338ca", accent_fg="#ffffff", field="#ffffff",
             ok="#15803d", warn="#b45309", fail="#b91c1c", head="#eef0f7", sel="#e0e7ff",
             g1="#4f46e5", g2="#0ea5e9", hero_fg="#ffffff", hero_sub="#e0e7ff")
DARK = dict(bg="#0b1020", card="#141b2f", card2="#182038", fg="#e6e9f2", muted="#8b95b0", border="#263152",
            accent="#6366f1", accent_hover="#818cf8", accent_fg="#ffffff", field="#0f1526",
            ok="#4ade80", warn="#fbbf24", fail="#f87171", head="#1c2545", sel="#27336b",
            g1="#3730a3", g2="#0e7490", hero_fg="#ffffff", hero_sub="#c7d2fe")

KIND_LABEL = {"bambu": "Bambu / Orca", "prusa": "PrusaSlicer", "ad5x": "AD5X", "plain": "Model only", "bad": "Unreadable"}
STATUS = {"bambu": "Ready", "prusa": "Ready", "ad5x": "Already AD5X", "plain": "No print profile", "bad": "Unreadable"}
CONVERTIBLE = ("bambu", "prusa")
FILTERS = ["All files", "Ready to convert", "Converted", "Can't convert"]

HELP_TEXT = """\
TURN ANY 3MF INTO AD5X-READY

Bambu2AD5X takes a sliced project (.3mf) and rebuilds it as a Flashforge AD5X project for OrcaSlicer, keeping the \
author's print settings (walls, infill, supports, seam, brim, ironing, temperatures, colours) and swapping in \
AD5X-correct machine values.

WORKS WITH
  •  MakerWorld, Bambu Studio and OrcaSlicer projects (print profile download)
  •  Printables projects saved in PrusaSlicer  (Download button)

WHAT CHANGES
  •  Printer: Flashforge AD5X 0.4 nozzle, with the AD5X start G-code and prime-tower setup.
  •  Speeds: always replaced by AD5X values matched to the layer height (0.16 / 0.20 / 0.24 mm; heights in
     between are interpolated).
  •  Filaments: preset chosen by material type (PLA > PLA Basic, PETG > PETG Pro ...). The author's
     temperatures and colours are kept.
  •  Unused filaments are dropped, unless the project has painted colours or colour-change layers.
  •  The prime tower moves with the model, and you are warned if it would overlap the model.
  •  Every converted file can come with a .report.txt listing what was kept, renamed, replaced or discarded.

OPEN THE RESULT
  In OrcaSlicer use  File > Open Project.  Do not drag the file in.

SHORTCUTS
  Ctrl+O  add files        Ctrl+A  check all shown      Ctrl+Enter  convert
  F5      rescan folder    Ctrl+F  search               Ctrl+L      show / hide log
  Space   tick / untick    Del     remove from list     Double-click a row  show in folder
  Right-click a row for more.
"""


# ------------------------------------------------------------------------------------------ helpers
def settings_file():
    return os.path.join(os.environ.get("APPDATA") or os.path.join(HOME, ".config"), APP, "settings.json")


def load_settings():
    try:
        with open(settings_file(), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def save_settings(d):
    try:
        os.makedirs(os.path.dirname(settings_file()), exist_ok=True)
        with open(settings_file(), "w", encoding="utf-8") as f:
            json.dump(d, f, indent=2)
    except Exception:
        pass


def find_3mf(folder, recursive, limit=400):
    out = []
    depth0 = folder.rstrip(os.sep).count(os.sep)
    for root, dirs, files in os.walk(folder):
        if not recursive or root.count(os.sep) - depth0 >= 3:
            dirs[:] = []
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for n in files:
            if n.lower().endswith(".3mf"):
                p = os.path.join(root, n)
                try:
                    out.append((os.path.getmtime(p), p))
                except OSError:
                    pass
    out.sort(reverse=True)
    return [p for _, p in out[:limit]]


def open_folder(path, select=None):
    try:
        if IS_WIN:
            if select:
                subprocess.Popen(["explorer", "/select,", os.path.normpath(select)])
            else:
                os.startfile(path)  # noqa
        elif IS_MAC:
            subprocess.Popen(["open", "-R", select] if select else ["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception:
        pass


def system_is_dark():
    try:
        if IS_WIN:
            import winreg
            k = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                               r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
            return winreg.QueryValueEx(k, "AppsUseLightTheme")[0] == 0
        if IS_MAC:
            r = subprocess.run(["defaults", "read", "-g", "AppleInterfaceStyle"], capture_output=True, text=True)
            return "Dark" in r.stdout
    except Exception:
        pass
    return False


def mix(c1, c2, t):
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def pil_fit(data, box, upscale=False):
    """PNG bytes -> PIL image fitted into box x box (worker-thread safe)."""
    im = Image.open(io.BytesIO(data))
    im.load()
    im = im.convert("RGBA")
    w, h = im.size
    s = box / max(w, h)
    if s < 1 or upscale:
        im = im.resize((max(1, int(w * s)), max(1, int(h * s))), Image.LANCZOS)
    return im


def tk_fit(data, box):
    """No-Pillow fallback: PNG bytes -> PhotoImage roughly fitted into box (integer zoom / subsample)."""
    try:
        img = tk.PhotoImage(data=base64.b64encode(data))
        s = min(box / img.width(), box / img.height())
        fr = Fraction(s).limit_denominator(8)
        if fr.numerator < 1:
            fr = Fraction(1, max(1, round(1 / s)))
        if fr != 1:
            img = img.zoom(fr.numerator).subsample(fr.denominator)
        return img
    except Exception:
        return None


class Tip:
    """Tiny hover tooltip."""

    def __init__(self, widget, text, app):
        self.w, self.text, self.app, self.tw, self.job = widget, text, app, None, None
        widget.bind("<Enter>", self._enter, add="+")
        widget.bind("<Leave>", self._leave, add="+")
        widget.bind("<ButtonPress>", self._leave, add="+")

    def _enter(self, _):
        self.job = self.w.after(450, self._show)

    def _leave(self, _=None):
        if self.job:
            self.w.after_cancel(self.job)
            self.job = None
        if self.tw:
            self.tw.destroy()
            self.tw = None

    def _show(self):
        c = self.app.c
        self.tw = tk.Toplevel(self.w)
        self.tw.wm_overrideredirect(True)
        self.tw.wm_geometry(f"+{self.w.winfo_rootx() + 14}+{self.w.winfo_rooty() + self.w.winfo_height() + 6}")
        tk.Label(self.tw, text=self.text, justify="left", wraplength=self.app.S(320), bg=c["fg"], fg=c["card"],
                 font=(self.app.font, 9), padx=10, pady=7).pack()


class Pill(tk.Canvas):
    """Rounded button drawn on a canvas (ttk buttons cannot be rounded)."""

    def __init__(self, master, app, text, command, kind="soft", size="m"):
        super().__init__(master, highlightthickness=0, bd=0, cursor="hand2")
        self.app, self.text, self.command, self.kind = app, text, command, kind
        self.font = (app.font, 11 if size == "l" else 9, "bold" if kind == "primary" else "normal")
        self.px, self.py = (app.S(26), app.S(11)) if size == "l" else (app.S(13), app.S(6))
        self.state, self.hover = "normal", False
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))
        self.bind("<ButtonRelease-1>", self._click)
        self._size()
        app.pills.append(self)

    def _size(self):
        f = tkfont.Font(font=self.font)
        self.configure(width=f.measure(self.text) + 2 * self.px, height=f.metrics("linespace") + 2 * self.py)
        self.redraw()

    def set_text(self, text):
        self.text = text
        self._size()

    def set_state(self, state):
        self.state = state
        self.configure(cursor="hand2" if state == "normal" else "arrow")
        self.redraw()

    def _set_hover(self, v):
        self.hover = v
        self.redraw()

    def _click(self, e):
        if self.state == "normal" and 0 <= e.x <= self.winfo_width() and 0 <= e.y <= self.winfo_height():
            self.command()

    def redraw(self):
        c = self.app.c
        try:
            outer = self.master.cget("bg")
        except tk.TclError:
            outer = c["bg"]
        self.configure(bg=outer)
        self.delete("all")
        w, h = int(self["width"]), int(self["height"])
        if self.state == "disabled":
            fill, fg = c["border"], c["muted"]
        elif self.kind == "primary":
            fill, fg = (c["accent_hover"] if self.hover else c["accent"]), c["accent_fg"]
        elif self.kind == "ghost":
            fill, fg = (c["head"] if self.hover else outer), (c["fg"] if self.hover else c["muted"])
        elif self.kind == "danger":
            fill, fg = (c["fail"] if self.hover else c["head"]), (c["accent_fg"] if self.hover else c["fail"])
        else:
            fill, fg = (c["sel"] if self.hover else c["head"]), c["fg"]
        r = h // 2
        x1, y1, x2, y2 = 1, 1, w - 1, h - 1
        pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2, x1, y2,
               x1, y2 - r, x1, y1 + r, x1, y1]
        self.create_polygon(pts, smooth=True, fill=fill, outline=fill)
        self.create_text(w / 2, h / 2, text=self.text, fill=fg, font=self.font)


# ------------------------------------------------------------------------------------------ app
class App(_Base):
    def __init__(self):
        super().__init__()
        self.cfg = load_settings()
        have = set(tkfont.families(self))
        self.font = next((f for f in ("Segoe UI Variable Text", "Segoe UI", "SF Pro Text", "Helvetica Neue", "Inter",
                                      "Ubuntu", "Cantarell", "DejaVu Sans") if f in have), "TkDefaultFont")
        self.mono = next((f for f in ("Cascadia Mono", "Consolas", "Menlo", "DejaVu Sans Mono", "Courier New") if f in have),
                         "TkFixedFont")
        try:
            self.scale = max(1.0, self.winfo_fpixels("1i") / 96.0)
        except Exception:
            self.scale = 1.0
        self.title(f"{APP} {APP_VER}  -  Turn any 3MF into AD5X-ready")
        self._set_geometry()
        self.minsize(self.S(940), self.S(640))
        self.q = queue.Queue()
        self.files = {}              # path -> {"info","checked","status","msg","seq","small"}
        self.seq = 0
        self.scan_id = 0
        self.busy = False
        self.pills, self.themed, self.cards = [], [], []
        self.pv_photo = None
        self.pv_key = None
        self.pv_job = None
        self.last_out = []
        self.sort_col, self.sort_rev = None, False
        self.blank = tk.PhotoImage(width=self.S(40), height=self.S(40))

        dark = self.cfg["dark"] if "dark" in self.cfg else system_is_dark()
        self.v_dark = tk.BooleanVar(value=bool(dark))
        self.v_src = tk.StringVar(value=self.cfg.get("src") or (DOWNLOADS if os.path.isdir(DOWNLOADS) else HOME))
        self.v_sub = tk.BooleanVar(value=self.cfg.get("sub", False))
        mode = self.cfg.get("mode") or ("same" if self.cfg.get("same", True) else "folder")
        self.v_mode = tk.StringVar(value="same" if mode == "replace" else mode)   # never restore "replace" silently
        self.v_out = tk.StringVar(value=self.cfg.get("out", ""))
        self.v_prune = tk.BooleanVar(value=self.cfg.get("prune", True))
        self.v_report = tk.BooleanVar(value=self.cfg.get("report", True))
        self.v_open = tk.BooleanVar(value=self.cfg.get("open", True))
        self.v_skipdone = tk.BooleanVar(value=self.cfg.get("skipdone", True))
        self.v_search = tk.StringVar()
        self.v_filter = tk.StringVar(value=FILTERS[0])
        saved_tpl = self.cfg.get("tpl") or ""
        # never trust a remembered path that is gone (e.g. an old PyInstaller _MEI temp folder)
        self.v_tpl = tk.StringVar(value=saved_tpl if saved_tpl and os.path.isfile(saved_tpl) else core.find_default_template())
        self.v_count = tk.StringVar(value="")
        self.v_state = tk.StringVar(value="")

        self.style = ttk.Style(self)
        try:
            self.style.theme_use("clam")
        except tk.TclError:
            pass
        self.c = DARK if self.v_dark.get() else LIGHT
        self._build()
        self.apply_theme()
        self.protocol("WM_DELETE_WINDOW", self._close)
        self._bind_keys()
        if HAS_DND:
            try:
                self.drop_target_register(DND_FILES)
                self.dnd_bind("<<Drop>>", self._on_drop)
            except Exception:
                pass
        self.set_state("Ready  -  drop .3mf files anywhere in this window" if HAS_DND else "Ready", "muted")
        self.v_search.trace_add("write", lambda *_: self._rebuild())
        self.after(100, self._poll)
        self.after(250, self.scan)

    def S(self, v):
        return int(round(v * self.scale))

    def _set_geometry(self):
        w, h = self.S(1300), self.S(880)
        g = self.cfg.get("geom")
        try:
            gw, gh, gx, gy = [int(x) for x in g.replace("x", "+").split("+")]
            if 700 <= gw <= self.winfo_screenwidth() and 500 <= gh <= self.winfo_screenheight() and \
                    -50 <= gx < self.winfo_screenwidth() - 100 and -10 <= gy < self.winfo_screenheight() - 100:
                self.geometry(g)
                return
        except Exception:
            pass
        w, h = min(w, self.winfo_screenwidth() - 60), min(h, self.winfo_screenheight() - 90)
        self.geometry(f"{w}x{h}+{max(0, (self.winfo_screenwidth() - w) // 2)}+{max(0, (self.winfo_screenheight() - h) // 3)}")

    # ----------------------------------------------------------------- widget helpers
    def T(self, w, **opts):
        """register a plain tk widget for theming:  T(widget, bg='card', fg='muted')"""
        self.themed.append((w, opts))
        return w

    def frame(self, parent, bg="card", **kw):
        return self.T(tk.Frame(parent, **kw), bg=bg)

    def label(self, parent, text="", bg="card", fg="fg", size=10, weight="normal", **kw):
        return self.T(tk.Label(parent, text=text, font=(self.font, size, weight), **kw), bg=bg, fg=fg)

    def card(self, parent, expand=False, **pack):
        f = tk.Frame(parent, padx=self.S(14), pady=self.S(12), highlightthickness=1)
        self.cards.append(f)
        self.T(f, bg="card")
        f.pack(fill="both" if expand else "x", expand=expand, **pack)
        return f

    def pill(self, parent, text, command, kind="soft", size="m"):
        return Pill(parent, self, text, command, kind, size)

    def check(self, parent, text, var, tip=None, **kw):
        w = ttk.Checkbutton(parent, text=text, variable=var, **kw)
        if tip:
            Tip(w, tip, self)
        return w

    # ----------------------------------------------------------------- layout
    def _build(self):
        S = self.S
        # ---- hero
        self.hero = tk.Canvas(self, height=S(128), highlightthickness=0, bd=0)
        self.hero.pack(fill="x")
        self.hero.bind("<Configure>", lambda e: self._draw_hero())

        # ---- footer + log first, so they can never be pushed out of view
        self.ft = self.T(tk.Frame(self, padx=S(20), pady=S(12)), bg="bg")
        self.ft.pack(side="bottom", fill="x")
        self.body = self.T(tk.Frame(self, padx=S(20), pady=S(16)), bg="bg")
        self.body.pack(fill="both", expand=True)

        self.pb = ttk.Progressbar(self.ft, mode="determinate", length=S(200))
        self.lb_state = self.label(self.ft, "", bg="bg", fg="muted", size=9, anchor="w")
        self.lb_state.configure(textvariable=self.v_state)
        self.lb_state.pack(side="left", padx=S(12))
        self.btn_go = self.pill(self.ft, "Convert", self.convert, "primary", "l")
        self.btn_go.pack(side="right")
        self.btn_log = self.pill(self.ft, "Log", self.toggle_log, "ghost")
        self.btn_log.pack(side="right", padx=S(8))
        self.btn_openout = self.pill(self.ft, "Open output folder", self._open_out, "soft")   # shown after a run

        # ---- main split: file list | preview + output
        self.pw = self.T(tk.PanedWindow(self.body, orient="horizontal", sashwidth=S(12), sashrelief="flat", bd=0,
                                        opaqueresize=True), bg="bg")
        self.pw.pack(fill="both", expand=True)
        left = self.frame(self.pw, "bg")
        right = self.frame(self.pw, "bg")
        self.pw.add(left, stretch="always", minsize=S(520))
        self.pw.add(right, stretch="never", minsize=S(330), width=S(400))

        self._build_log(left)
        self._build_list(left)
        self._build_output(right)
        self._build_preview(right)

    def _build_log(self, parent):
        S = self.S
        self.logf = self.frame(parent, "bg")          # packed on demand, under the file list
        top = self.frame(self.logf, "bg")
        top.pack(fill="x", pady=(0, S(4)))
        self.label(top, "LOG", "bg", "muted", 8, "bold").pack(side="left")
        self.pill(top, "Clear", self.clear_log, "ghost").pack(side="right")
        lw = self.frame(self.logf, "card", highlightthickness=1)
        self.cards.append(lw)
        lw.pack(fill="x")
        self.txt_log = self.T(tk.Text(lw, height=7, wrap="word", relief="flat", bd=0, highlightthickness=0, padx=S(10),
                                      pady=S(8), font=(self.mono, 9), state="disabled"), bg="field", fg="fg")
        ls = ttk.Scrollbar(lw, command=self.txt_log.yview)
        self.txt_log.configure(yscrollcommand=ls.set)
        self.txt_log.pack(side="left", fill="x", expand=True)
        ls.pack(side="right", fill="y")
        self.log_open = False

    def _build_list(self, parent):
        S = self.S
        c = self.list_card = self.card(parent, expand=True)
        # source row
        r = self.frame(c)
        r.pack(fill="x")
        self.label(r, "FOLDER", "card", "muted", 8, "bold").pack(side="left", padx=(0, S(10)))
        ttk.Entry(r, textvariable=self.v_src).pack(side="left", fill="x", expand=True, padx=(0, S(8)))
        self.pill(r, "Browse", self.pick_src).pack(side="left", padx=2)
        self.pill(r, "Rescan", self.scan).pack(side="left", padx=2)
        self.check(r, "Subfolders", self.v_sub, "Also look inside subfolders (3 levels deep).", command=self.scan).pack(
            side="left", padx=(S(10), 0))
        # tools row
        r = self.frame(c)
        r.pack(fill="x", pady=(S(10), S(8)))
        self.pill(r, "+ Add files", self.add_files, "soft").pack(side="left", padx=(0, 4))
        self.pill(r, "Check all", lambda: self.set_all(True), "ghost").pack(side="left", padx=2)
        self.pill(r, "None", lambda: self.set_all(False), "ghost").pack(side="left", padx=2)
        self.pill(r, "Invert", self.invert, "ghost").pack(side="left", padx=2)
        self.cb = ttk.Combobox(r, textvariable=self.v_filter, values=FILTERS, state="readonly", width=15)
        self.cb.pack(side="right")
        self.cb.bind("<<ComboboxSelected>>", lambda e: (self._rebuild(), self.focus_set()))
        self.ent_search = ttk.Entry(r, textvariable=self.v_search, width=16)
        self.ent_search.pack(side="right", padx=(0, S(8)))
        ph = self.T(tk.Label(self.ent_search, text="Search files...", font=(self.font, 9), cursor="xterm"), bg="field", fg="muted")
        ph.place(x=S(8), rely=.5, anchor="w")
        ph.bind("<Button-1>", lambda e: self.ent_search.focus_set())
        self.v_search.trace_add("write", lambda *_: ph.place_forget() if self.v_search.get() else ph.place(x=S(8), rely=.5, anchor="w"))
        # tree
        tf = self.frame(c)
        tf.pack(fill="both", expand=True)
        cols = ("chk", "name", "src", "printer", "layer", "fil", "status")
        self.tree = ttk.Treeview(tf, columns=cols, show="tree headings", selectmode="extended")
        spec = (("#0", "", 52, False), ("chk", "", 34, False), ("name", "File", 150, True), ("src", "From", 90, False),
                ("printer", "Original printer", 120, False), ("layer", "Layer", 62, False),
                ("fil", "Col.", 42, False), ("status", "Status", 128, False))
        for k, t, w, s in spec:
            self.tree.heading(k, text=t, command=(self.toggle_all if k == "chk" else (lambda cc=k: self.sort_by(cc))) if k != "#0" else "")
            self.tree.column(k, width=S(w), minwidth=S(30), stretch=s,
                             anchor="center" if k in ("chk", "fil", "layer") else "w")
        sb = ttk.Scrollbar(tf, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.bind("<Button-1>", self._on_click)
        self.tree.bind("<space>", self._on_space)
        self.tree.bind("<<TreeviewSelect>>", self._show_details)
        self.tree.bind("<Double-1>", self._on_double)
        self.tree.bind("<Button-3>", self._on_menu)
        if IS_MAC:
            self.tree.bind("<Button-2>", self._on_menu)
        self.empty = self.T(tk.Label(tf, text="Drop .3mf files here\nor use  + Add files  /  Browse",
                                     font=(self.font, 12), justify="center"), bg="field", fg="muted")
        self.empty.place(relx=.5, rely=.5, anchor="center")
        # summary
        self.lb_count = self.label(c, "", "card", "muted", 9, anchor="w")
        self.lb_count.configure(textvariable=self.v_count)
        self.lb_count.pack(fill="x", pady=(S(8), 0))
        # context menu
        self.menu = tk.Menu(self, tearoff=0, bd=0, relief="flat")
        for item in (("Tick selected", lambda: self._tick_sel(True)), ("Untick selected", lambda: self._tick_sel(False)),
                           None, ("Show source in folder", self._m_show_src), ("Show converted file in folder", self._m_show_out),
                           ("Copy path", self._m_copy), None, ("Remove from list", self.remove_sel)):
            if item is None:
                self.menu.add_separator()
            else:
                self.menu.add_command(label=item[0], command=item[1])

    def _build_preview(self, parent):
        S = self.S
        c = self.card(parent, expand=True, pady=(0, S(12)))
        self.label(c, "PREVIEW", "card", "muted", 8, "bold", anchor="w").pack(fill="x")
        inf = self.frame(c)
        inf.pack(side="bottom", fill="x")
        self.pv_box = self.T(tk.Frame(c, highlightthickness=1, width=S(300), height=S(200)), bg="field")
        self.cards.append(self.pv_box)
        self.pv_box.pack(fill="both", expand=True, pady=(S(8), S(10)))
        self.pv_box.pack_propagate(False)
        self.pv_box.bind("<Configure>", lambda e: self._sched_preview())
        self.lb_thumb = self.T(tk.Label(self.pv_box, text="Select a file to see its preview", font=(self.font, 10),
                                        bd=0), bg="field", fg="muted")
        self.lb_thumb.place(relx=.5, rely=.5, anchor="center")
        self.lb_name = self.label(inf, "", "card", "fg", 12, "bold", anchor="w", justify="left")
        self.lb_name.pack(fill="x")
        self.chips = self.frame(inf)
        self.chips.pack(fill="x", pady=(S(6), S(4)))
        self.chip_lbls = []
        for _ in range(4):
            l = tk.Label(self.chips, font=(self.font, 9), padx=S(9), pady=S(2))
            self.T(l, bg="head", fg="fg")
            self.chip_lbls.append(l)
        self.lb_route = self.label(inf, "", "card", "muted", 9, anchor="w", justify="left")
        self.lb_route.pack(fill="x")
        self.lb_msg = self.label(inf, "", "card", "warn", 9, anchor="w", justify="left")
        self.lb_msg.pack(fill="x", pady=(S(4), 0))
        self.lb_outp = self.label(inf, "", "card", "muted", 8, anchor="w", justify="left")
        self.lb_outp.pack(fill="x", pady=(S(4), 0))
        c.bind("<Configure>", lambda e: [l.configure(wraplength=max(120, e.width - self.S(30)))
                                         for l in (self.lb_name, self.lb_route, self.lb_msg, self.lb_outp)])

    def _build_output(self, parent):
        S = self.S
        c = self.card(parent, side="bottom")
        self.label(c, "OUTPUT", "card", "muted", 8, "bold", anchor="w").pack(fill="x", pady=(0, S(6)))
        ttk.Radiobutton(c, text="Next to each file  (name_AD5X.3mf)", variable=self.v_mode, value="same",
                        command=self._sync_out).pack(anchor="w")
        r = self.frame(c)
        r.pack(fill="x", pady=(S(4), 0))
        ttk.Radiobutton(r, text="Folder:", variable=self.v_mode, value="folder", command=self._sync_out).pack(side="left")
        self.ent_out = ttk.Entry(r, textvariable=self.v_out)
        self.ent_out.pack(side="left", fill="x", expand=True, padx=(S(6), S(6)))
        self.btn_out = self.pill(r, "Browse", self.pick_out)
        self.btn_out.pack(side="left")
        self.rb_over = ttk.Radiobutton(c, text="Replace the original files", variable=self.v_mode, value="replace",
                                       command=self._sync_out)
        self.rb_over.pack(anchor="w", pady=(S(4), 0))
        Tip(self.rb_over, "Overwrites your .3mf with the AD5X version. Built in a temp file first, so a failed "
                          "conversion never damages the original. Close the file in OrcaSlicer first.", self)
        sep = tk.Frame(c, height=1)
        self.T(sep, bg="border")
        sep.pack(fill="x", pady=S(10))
        self.check(c, "Drop filaments the model doesn't use", self.v_prune,
                   "Removes unused filaments and renumbers the rest (like the web converter). Skipped automatically "
                   "for projects with painted colours or colour-change layers.").pack(anchor="w")
        self.check(c, "Write a .report.txt", self.v_report,
                   "Saves a list of everything kept, renamed, replaced or discarded next to each result.").pack(anchor="w", pady=(2, 0))
        self.btn_more = self.pill(c, "More options...", self.show_options, "ghost")
        self.btn_more.pack(anchor="w", pady=(S(8), 0))
        self._sync_out()

    def show_options(self):
        if getattr(self, "opt_win", None) and self.opt_win.winfo_exists():
            self.opt_win.lift()
            return
        c, S = self.c, self.S
        w = self.opt_win = tk.Toplevel(self)
        w.title(f"{APP} - More options")
        w.configure(bg=c["card"])
        w.transient(self)
        w.geometry(f"{S(560)}x{S(300)}+{self.winfo_rootx() + S(120)}+{self.winfo_rooty() + S(160)}")
        body = tk.Frame(w, bg=c["card"], padx=S(22), pady=S(18))
        body.pack(fill="both", expand=True)
        tk.Label(body, text="MORE OPTIONS", bg=c["card"], fg=c["muted"], font=(self.font, 8, "bold")).pack(anchor="w", pady=(0, S(8)))
        self.check(body, "Open the folder when done", self.v_open).pack(anchor="w")
        self.check(body, "'Check all' skips files that already have an _AD5X copy", self.v_skipdone).pack(anchor="w", pady=(S(4), 0))
        tk.Label(body, text="AD5X TEMPLATE", bg=c["card"], fg=c["muted"], font=(self.font, 8, "bold")).pack(anchor="w", pady=(S(18), S(4)))
        tk.Label(body, text="The bundled template is used unless you pick another one.", bg=c["card"], fg=c["muted"],
                 font=(self.font, 9)).pack(anchor="w", pady=(0, S(6)))
        r = tk.Frame(body, bg=c["card"])
        r.pack(fill="x")
        ttk.Entry(r, textvariable=self.v_tpl).pack(side="left", fill="x", expand=True, padx=(0, S(6)))
        Pill(r, self, "Browse", self.pick_tpl).pack(side="left", padx=2)
        Pill(r, self, "Default", lambda: self.v_tpl.set(core.find_default_template())).pack(side="left")
        Pill(body, self, "Close", w.destroy, "primary").pack(anchor="e", side="bottom")
        w.bind("<Escape>", lambda e: w.destroy())

    # ----------------------------------------------------------------- hero
    def _draw_hero(self):
        h = self.hero
        c = self.c
        S = self.S
        w, ht = h.winfo_width(), h.winfo_height()
        if w < 50:
            return
        h.delete("all")
        n = 72
        for i in range(n):
            h.create_rectangle(i * w / n, 0, (i + 1) * w / n + 1, ht, outline="", fill=mix(c["g1"], c["g2"], i / (n - 1)))
        # soft decorative circles
        h.create_oval(w - S(230), -S(120), w + S(60), S(150), outline="", fill=mix(c["g2"], "#ffffff", .12))
        x = S(28)
        t = h.create_text(x, S(34), text=APP, anchor="w", fill=c["hero_fg"], font=(self.font, 24, "bold"))
        bx = h.bbox(t)
        vt = h.create_text(bx[2] + S(24), S(35), text=APP_VER, anchor="w", fill=c["hero_fg"], font=(self.font, 9, "bold"))
        vb = h.bbox(vt)
        chip = h.create_polygon(self._rr(vb[0] - S(9), vb[1] - S(3), vb[2] + S(9), vb[3] + S(3)), smooth=True,
                                fill=mix(c["g1"], "#ffffff", .28), outline="")
        h.tag_lower(chip, vt)
        h.create_text(x, S(70), text="Turn any 3MF into an AD5X-ready OrcaSlicer project.", anchor="w",
                      fill=c["hero_fg"], font=(self.font, 13))
        # steps
        f = tkfont.Font(family=self.font, size=10)
        sx = x
        for i, txt in enumerate(("Add your files", "Tick what to convert", "Press Convert")):
            d = S(20)
            h.create_oval(sx, S(94), sx + d, S(94) + d, outline="", fill="#ffffff")
            h.create_text(sx + d / 2, S(94) + d / 2, text=str(i + 1), fill=c["g1"], font=(self.font, 9, "bold"))
            lt = h.create_text(sx + d + S(8), S(94) + d / 2, text=txt, anchor="w", fill=c["hero_sub"], font=(self.font, 10))
            sx = h.bbox(lt)[2] + S(26)
        # right side actions
        dark = self.v_dark.get()
        for tag, y, text in (("theme", S(30), ("Light mode" if dark else "Dark mode")), ("help", S(56), "How it works")):
            it = h.create_text(w - S(28), y, text=text, anchor="e", fill=c["hero_fg"], font=(self.font, 10, "underline"),
                               tags=(tag,))
            h.tag_bind(tag, "<Button-1>", (lambda e: self.toggle_theme()) if tag == "theme" else (lambda e: self.show_help()))
            h.tag_bind(tag, "<Enter>", lambda e: h.configure(cursor="hand2"))
            h.tag_bind(tag, "<Leave>", lambda e: h.configure(cursor=""))
        if w > S(1000):
            h.create_text(w - S(28), S(100), anchor="e", fill=c["hero_sub"], font=(self.font, 9),
                          text="MakerWorld  \u00B7  Bambu Studio  \u00B7  OrcaSlicer  \u00B7  Printables (PrusaSlicer)   \u2192   Flashforge AD5X")

    @staticmethod
    def _rr(x1, y1, x2, y2):
        r = (y2 - y1) / 2
        return [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2, x1, y2,
                x1, y2 - r, x1, y1 + r, x1, y1]

    # ----------------------------------------------------------------- theme
    def apply_theme(self):
        c = DARK if self.v_dark.get() else LIGHT
        self.c = c
        S = self.S
        self.configure(bg=c["bg"])
        st = self.style
        F = self.font
        st.configure(".", background=c["card"], foreground=c["fg"], fieldbackground=c["field"], bordercolor=c["border"],
                     lightcolor=c["card"], darkcolor=c["card"], troughcolor=c["head"], font=(F, 10))
        st.configure("TEntry", fieldbackground=c["field"], foreground=c["fg"], bordercolor=c["border"],
                     lightcolor=c["border"], darkcolor=c["border"], insertcolor=c["fg"], padding=S(6))
        st.map("TEntry", bordercolor=[("focus", c["accent"])], lightcolor=[("focus", c["accent"])],
               darkcolor=[("focus", c["accent"])])
        st.configure("TCombobox", fieldbackground=c["field"], background=c["head"], foreground=c["fg"],
                     arrowcolor=c["muted"], bordercolor=c["border"], lightcolor=c["border"], darkcolor=c["border"],
                     padding=S(5), selectbackground=c["field"], selectforeground=c["fg"])
        st.map("TCombobox", fieldbackground=[("readonly", c["field"])], foreground=[("readonly", c["fg"])],
               bordercolor=[("focus", c["accent"])])
        self.option_add("*TCombobox*Listbox.background", c["field"])
        self.option_add("*TCombobox*Listbox.foreground", c["fg"])
        self.option_add("*TCombobox*Listbox.selectBackground", c["sel"])
        self.option_add("*TCombobox*Listbox.selectForeground", c["fg"])
        for w in ("TCheckbutton", "TRadiobutton"):
            st.configure(w, background=c["card"], foreground=c["fg"], focuscolor=c["card"], padding=(0, S(2)),
                         indicatorbackground=c["field"], indicatorforeground=c["accent_fg"],
                         upperbordercolor=c["muted"], lowerbordercolor=c["muted"], indicatorcolor=c["field"])
            st.map(w, background=[("active", c["card"])],
                   indicatorbackground=[("selected", c["accent"]), ("!selected", c["field"])],
                   indicatorcolor=[("selected", c["accent"]), ("!selected", c["field"])],
                   upperbordercolor=[("selected", c["accent"]), ("!selected", c["muted"])],
                   lowerbordercolor=[("selected", c["accent"]), ("!selected", c["muted"])])
        st.configure("Treeview", background=c["field"], fieldbackground=c["field"], foreground=c["fg"],
                     rowheight=S(48), borderwidth=0, font=(F, 10))
        st.map("Treeview", background=[("selected", c["sel"])], foreground=[("selected", c["fg"])])
        st.configure("Treeview.Heading", background=c["head"], foreground=c["muted"], relief="flat", font=(F, 9, "bold"),
                     padding=(S(6), S(6)), bordercolor=c["head"], lightcolor=c["head"], darkcolor=c["head"])
        st.map("Treeview.Heading", background=[("active", c["sel"])])
        st.configure("Horizontal.TProgressbar", background=c["accent"], troughcolor=c["head"], bordercolor=c["head"],
                     lightcolor=c["accent"], darkcolor=c["accent"], thickness=S(8))
        st.configure("Vertical.TScrollbar", background=c["head"], troughcolor=c["field"], bordercolor=c["field"],
                     lightcolor=c["head"], darkcolor=c["head"], arrowcolor=c["muted"], arrowsize=S(14))
        st.map("Vertical.TScrollbar", background=[("active", c["sel"])])
        for w, opts in self.themed:
            try:
                w.configure(**{k: c[v] for k, v in opts.items()})
            except tk.TclError:
                pass
        for f in self.cards:
            f.configure(highlightbackground=c["border"], highlightcolor=c["border"])
        self.menu.configure(bg=c["card"], fg=c["fg"], activebackground=c["sel"], activeforeground=c["fg"])
        for tag, col in (("ok", "ok"), ("warn", "warn"), ("fail", "fail"), ("muted", "muted")):
            self.txt_log.tag_configure(tag, foreground=c[col])
        for tag, col in (("ok", "ok"), ("warn", "warn"), ("fail", "fail"), ("dim", "muted"), ("ready", "accent")):
            self.tree.tag_configure(tag, foreground=c[col])
        self.lb_state.configure(fg=self._tone_col)
        for p in self.pills:
            p.redraw()
        self._draw_hero()

    _tone_col = "#64748b"

    def toggle_theme(self):
        self.v_dark.set(not self.v_dark.get())
        self.apply_theme()

    def toggle_log(self, force=None):
        want = (not self.log_open) if force is None else force
        if want == self.log_open:
            return
        self.log_open = want
        if want:
            self.logf.pack(side="bottom", fill="x", pady=(self.S(10), 0), before=self.list_card)
        else:
            self.logf.pack_forget()
        self.btn_log.set_text("Hide log" if want else "Log")

    def clear_log(self):
        self.txt_log.configure(state="normal")
        self.txt_log.delete("1.0", "end")
        self.txt_log.configure(state="disabled")

    def show_help(self):
        c = self.c
        win = tk.Toplevel(self)
        win.title(f"{APP} - How it works")
        win.configure(bg=c["card"])
        win.geometry(f"{self.S(720)}x{self.S(640)}")
        win.transient(self)
        t = tk.Text(win, wrap="word", relief="flat", bd=0, padx=self.S(24), pady=self.S(20), bg=c["card"], fg=c["fg"],
                    font=(self.font, 10), spacing1=2, spacing3=3)
        t.tag_configure("h", font=(self.font, 16, "bold"), foreground=c["accent"], spacing3=8)
        t.tag_configure("s", font=(self.font, 9, "bold"), foreground=c["muted"], spacing1=12)
        for i, line in enumerate(HELP_TEXT.split("\n")):
            if i == 0:
                t.insert("end", line + "\n", "h")
            elif line and line == line.upper() and not line.startswith(" "):
                t.insert("end", line + "\n", "s")
            else:
                t.insert("end", line + "\n")
        t.configure(state="disabled")
        t.pack(fill="both", expand=True)
        win.bind("<Escape>", lambda e: win.destroy())

    def _bind_keys(self):
        def guard(fn):
            def h(e=None):
                if isinstance(self.focus_get(), (tk.Entry, ttk.Entry, ttk.Combobox)):
                    return
                fn()
                return "break"
            return h
        self.bind_all("<Control-a>", guard(lambda: self.set_all(True)))
        self.bind_all("<Control-o>", lambda e: (self.add_files(), "break")[1])
        self.bind_all("<Control-Return>", lambda e: (self.convert(), "break")[1])
        self.bind_all("<F5>", lambda e: (self.scan(), "break")[1])
        self.bind_all("<Control-f>", lambda e: (self.ent_search.focus_set(), "break")[1])
        self.bind_all("<Control-l>", lambda e: (self.toggle_log(), "break")[1])
        self.tree.bind("<Delete>", lambda e: self.remove_sel())

    def _close(self):
        try:
            geom = self.geometry() if self.state() == "normal" else self.cfg.get("geom")
        except Exception:
            geom = None
        save_settings(dict(dark=self.v_dark.get(), src=self.v_src.get(), sub=self.v_sub.get(), mode=self.v_mode.get(),
                           out=self.v_out.get(), report=self.v_report.get(), open=self.v_open.get(),
                           prune=self.v_prune.get(), skipdone=self.v_skipdone.get(), geom=geom,
                           tpl="" if self.v_tpl.get() == core.find_default_template() else self.v_tpl.get()))
        self.destroy()

    def set_state(self, text, tone="muted"):
        self._tone_col = self.c[tone]
        self.v_state.set(text)
        self.lb_state.configure(fg=self._tone_col)

    # ----------------------------------------------------------------- list handling
    def out_path(self, src):
        mode = self.v_mode.get()
        if mode == "replace":
            return src
        base = os.path.basename(src)
        name = (base[:-4] if base.lower().endswith(".3mf") else base) + "_AD5X.3mf"
        folder = os.path.dirname(src) if (mode == "same" or not self.v_out.get().strip()) else self.v_out.get().strip()
        return os.path.join(folder, name)

    def _tag(self, f):
        st, i = f["status"], f["info"]
        if st.startswith("Done"):
            return "warn" if "warning" in st else "ok"
        if st.startswith("Failed"):
            return "fail"
        if st == "Already converted":
            return "ok"
        if i["kind"] not in CONVERTIBLE:
            return "dim"
        return ""

    def _values(self, p):
        f = self.files[p]
        i = f["info"]
        return ("\u2611" if f["checked"] else "\u2610", os.path.basename(p), KIND_LABEL.get(i["kind"], "?"),
                i["printer"] or "-", (i["layer"] + " mm") if i["layer"] else "-", i["filaments"] or "-", f["status"])

    def _visible(self, p):
        f = self.files[p]
        q = self.v_search.get().strip().lower()
        if q and q not in os.path.basename(p).lower() and q not in (f["info"]["printer"] or "").lower():
            return False
        m = self.v_filter.get()
        conv = f["info"]["kind"] in CONVERTIBLE
        done = f["status"].startswith("Done") or f["status"] == "Already converted"
        if m == FILTERS[1]:
            return conv and not done
        if m == FILTERS[2]:
            return done
        if m == FILTERS[3]:
            return not conv
        return True

    def _insert(self, p):
        f = self.files[p]
        tag = self._tag(f)
        self.tree.insert("", "end", iid=p, image=f["small"] or self.blank, values=self._values(p), tags=(tag,) if tag else ())

    def _rebuild(self):
        keep = set(self.tree.selection())
        self.tree.delete(*self.tree.get_children(""))
        paths = [p for p in self.files if self._visible(p)]
        keyf = {"name": lambda p: os.path.basename(p).lower(), "src": lambda p: KIND_LABEL.get(self.files[p]["info"]["kind"]),
                "printer": lambda p: (self.files[p]["info"]["printer"] or "").lower(),
                "layer": lambda p: float(self.files[p]["info"]["layer"] or 0) if str(self.files[p]["info"]["layer"] or "0").replace(".", "", 1).isdigit() else 0,
                "fil": lambda p: int(self.files[p]["info"]["filaments"] or 0), "status": lambda p: self.files[p]["status"],
                "chk": lambda p: not self.files[p]["checked"]}.get(self.sort_col)
        paths.sort(key=keyf if keyf else (lambda p: self.files[p]["seq"]), reverse=self.sort_rev if keyf else False)
        for p in paths:
            self._insert(p)
        self.tree.selection_set([p for p in keep if self.tree.exists(p)])
        for k, t in (("name", "File"), ("src", "From"), ("printer", "Original printer"), ("layer", "Layer"),
                     ("fil", "Col."), ("status", "Status")):
            self.tree.heading(k, text=t + (("  \u25BC" if self.sort_rev else "  \u25B2") if k == self.sort_col else ""))
        if paths or self.files:
            self.empty.configure(text="Nothing matches the search / filter" if self.files else "")
            (self.empty.place(relx=.5, rely=.5, anchor="center") if not paths else self.empty.place_forget())
        else:
            self.empty.configure(text="Drop .3mf files here\nor use  + Add files  /  Browse")
            self.empty.place(relx=.5, rely=.5, anchor="center")
        self._update_count()

    def sort_by(self, col):
        if self.sort_col == col:
            if self.sort_rev:
                self.sort_col, self.sort_rev = None, False
            else:
                self.sort_rev = True
        else:
            self.sort_col, self.sort_rev = col, False
        self._rebuild()

    def _refresh(self, p):
        if self.tree.exists(p):
            tag = self._tag(self.files[p])
            self.tree.item(p, values=self._values(p), tags=(tag,) if tag else ())
        self._update_count()

    def _add(self, p, info):
        if p in self.files:
            return
        status = STATUS[info["kind"]]
        if info["kind"] in CONVERTIBLE and os.path.exists(self.out_path(p)) and self.v_mode.get() != "replace":
            status = "Already converted"
        small = None
        if info.get("thumb"):
            try:
                if info.get("_pil") is not None:
                    small = ImageTk.PhotoImage(info["_pil"])
                else:
                    small = tk_fit(info["thumb"], self.S(40))
            except Exception:
                small = None
        self.seq += 1
        self.files[p] = {"info": info, "checked": False, "status": status, "msg": "", "seq": self.seq, "small": small}
        if self._visible(p):
            self._insert(p)
            self.empty.place_forget()

    def _update_count(self):
        n = sum(1 for f in self.files.values() if f["checked"])
        shown = len(self.tree.get_children(""))
        ready = sum(1 for f in self.files.values() if f["info"]["kind"] in CONVERTIBLE and f["status"] == "Ready")
        hidden = sum(1 for p, f in self.files.items() if f["checked"] and not self.tree.exists(p))
        s = f"{n} ticked  \u00B7  {shown} of {len(self.files)} shown  \u00B7  {ready} ready to convert"
        if hidden:
            s += f"  \u00B7  {hidden} ticked file(s) hidden by the filter"
        self.v_count.set(s)
        self.btn_go.set_text(f"Convert {n} file{'s' if n != 1 else ''}" if n else "Convert")

    def _eligible(self, p, value):
        f = self.files[p]
        if f["info"]["kind"] not in CONVERTIBLE:
            return False
        if value and self.v_skipdone.get() and f["status"] == "Already converted":
            return False
        return bool(value)

    def set_all(self, value):
        for p in self.tree.get_children(""):
            self.files[p]["checked"] = self._eligible(p, value)
            self._refresh(p)

    def toggle_all(self):
        rows = [p for p in self.tree.get_children("") if self.files[p]["info"]["kind"] in CONVERTIBLE]
        self.set_all(not all(self.files[p]["checked"] for p in rows) if rows else True)

    def invert(self):
        for p in self.tree.get_children(""):
            self.files[p]["checked"] = self._eligible(p, not self.files[p]["checked"])
            self._refresh(p)

    def _tick_sel(self, value):
        for p in self.tree.selection():
            f = self.files.get(p)
            if f and f["info"]["kind"] in CONVERTIBLE and not self.busy:
                f["checked"] = value
                self._refresh(p)

    def remove_sel(self):
        for p in self.tree.selection():
            self.files.pop(p, None)
            self.tree.delete(p)
        self._update_count()
        if not self.files:
            self._rebuild()

    def _toggle(self, p):
        f = self.files.get(p)
        if f and f["info"]["kind"] in CONVERTIBLE and not self.busy:
            f["checked"] = not f["checked"]
            self._refresh(p)

    def _on_click(self, e):
        if self.tree.identify_region(e.x, e.y) == "cell" and self.tree.identify_column(e.x) == "#1":
            self._toggle(self.tree.identify_row(e.y))
            return "break"

    def _on_space(self, e):
        for p in self.tree.selection():
            self._toggle(p)
        return "break"

    def _on_double(self, e):
        if self.tree.identify_region(e.x, e.y) in ("cell", "tree") and self.tree.identify_column(e.x) != "#1":
            p = self.tree.identify_row(e.y)
            if p:
                o = self.out_path(p)
                open_folder(os.path.dirname(o), o if os.path.exists(o) else p)

    def _on_menu(self, e):
        row = self.tree.identify_row(e.y)
        if row and row not in self.tree.selection():
            self.tree.selection_set(row)
        if self.tree.selection():
            self.menu.tk_popup(e.x_root, e.y_root)

    def _m_show_src(self):
        for p in self.tree.selection()[:1]:
            open_folder(os.path.dirname(p), p)

    def _m_show_out(self):
        for p in self.tree.selection()[:1]:
            o = self.out_path(p)
            if os.path.exists(o):
                open_folder(os.path.dirname(o), o)
            else:
                self.set_state("That file has not been converted yet", "warn")

    def _m_copy(self):
        sel = self.tree.selection()
        if sel:
            self.clipboard_clear()
            self.clipboard_append("\n".join(sel))
            self.set_state("Path copied", "muted")

    # ----------------------------------------------------------------- details + preview
    def _show_details(self, _=None):
        if not hasattr(self, "chip_lbls"):      # preview panel not built yet (output card is built first)
            return
        sel = self.tree.selection()
        p = sel[0] if sel else None
        f = self.files.get(p) if p else None
        for l in self.chip_lbls:
            l.pack_forget()
        if not f:
            self.lb_name.configure(text="")
            self.lb_route.configure(text="")
            self.lb_msg.configure(text="")
            self.lb_outp.configure(text="")
            self.pv_key = None
            self._render_preview()
            return
        i = f["info"]
        self.lb_name.configure(text=os.path.basename(p))
        chips = [KIND_LABEL.get(i["kind"], "?")]
        if i["layer"]:
            chips.append(f"{i['layer']} mm")
        if i["filaments"]:
            chips.append(f"{i['filaments']} filament{'s' if i['filaments'] != 1 else ''}" + (f" \u00B7 {i['types']}" if i["types"] else ""))
        for l, t in zip(self.chip_lbls, chips):
            l.configure(text=t)
            l.pack(side="left", padx=(0, self.S(6)))
        if i["kind"] in CONVERTIBLE:
            self.lb_route.configure(text=f"{i['printer'] or 'Unknown printer'}   \u2192   Flashforge AD5X")
        else:
            self.lb_route.configure(text=f["status"])
        self.lb_msg.configure(text=f.get("msg") or "", fg=self.c["fail"] if f["status"].startswith("Failed") else self.c["warn"])
        self.lb_outp.configure(text=("Output:  " + self.out_path(p)) if i["kind"] in CONVERTIBLE else "")
        self.pv_key = None
        self._render_preview()

    def _sched_preview(self):
        if self.pv_job:
            self.after_cancel(self.pv_job)
        self.pv_job = self.after(70, self._render_preview)

    def _render_preview(self):
        self.pv_job = None
        sel = self.tree.selection()
        p = sel[0] if sel else None
        f = self.files.get(p) if p else None
        box = min(self.pv_box.winfo_width(), self.pv_box.winfo_height()) - self.S(20)
        if box < 60:
            return
        if not f or not f["info"].get("thumb"):
            self.pv_photo = None
            self.pv_key = None
            self.lb_thumb.configure(image="", text="Select a file to see its preview" if not f else "No preview inside this file")
            return
        key = (p, box // 6)
        if key == self.pv_key:
            return
        photo = None
        try:
            photo = ImageTk.PhotoImage(pil_fit(f["info"]["thumb"], box, upscale=True)) if HAS_PIL else tk_fit(f["info"]["thumb"], box)
        except Exception:
            photo = tk_fit(f["info"]["thumb"], box)
        if photo is None:
            self.lb_thumb.configure(image="", text="No preview inside this file")
            return
        self.pv_photo, self.pv_key = photo, key
        self.lb_thumb.configure(image=photo, text="")

    # ----------------------------------------------------------------- pickers / scan
    def _sync_out(self):
        st = "normal" if self.v_mode.get() == "folder" else "disabled"
        self.ent_out.configure(state=st)
        self.btn_out.set_state(st)
        for p in self.files:
            self._refresh(p)
        self._show_details()

    def pick_src(self):
        d = filedialog.askdirectory(initialdir=self.v_src.get() or HOME, title="Folder with .3mf files")
        if d:
            self.v_src.set(os.path.normpath(d))
            self.scan()

    def pick_out(self):
        d = filedialog.askdirectory(initialdir=self.v_out.get() or self.v_src.get(), title="Output folder")
        if d:
            self.v_out.set(os.path.normpath(d))

    def pick_tpl(self):
        f = filedialog.askopenfilename(title="AD5X template (.3mf or .json)", filetypes=[("Template", "*.3mf *.json"), ("All", "*.*")])
        if f:
            self.v_tpl.set(f)

    def add_files(self):
        fs = filedialog.askopenfilenames(title="Select .3mf files", initialdir=self.v_src.get(), filetypes=[("3MF", "*.3mf")])
        if fs:
            self._ingest([os.path.normpath(p) for p in fs])

    def _on_drop(self, e):
        try:
            self._ingest([os.path.normpath(p) for p in self.tk.splitlist(e.data)])
        except Exception as ex:
            self.set_state(f"Drop failed: {ex}", "fail")
        return e.action

    def _ingest(self, paths):
        """add individual files / folders (drag & drop, Add files) without clearing the list"""
        sid = self.scan_id
        self.set_state("Reading files...", "muted")

        def work():
            found = []
            for p in paths:
                if os.path.isdir(p):
                    found += find_3mf(p, True)
                elif p.lower().endswith(".3mf"):
                    found.append(p)
            for p in dict.fromkeys(found):
                if p not in self.files:
                    self.q.put(("add", sid, self._inspect(p)))
            self.q.put(("scanned", sid, len(found)))
        threading.Thread(target=work, daemon=True).start()

    def _inspect(self, p):
        info = core.inspect(p)
        if HAS_PIL and info.get("thumb"):
            try:
                info["_pil"] = pil_fit(info["thumb"], self.S(40))
            except Exception:
                info["_pil"] = None
        return (p, info)

    def scan(self):
        folder = self.v_src.get().strip()
        if not os.path.isdir(folder):
            self.set_state("Source folder not found", "fail")
            return
        self.scan_id += 1
        sid = self.scan_id
        self.set_state("Scanning...", "muted")
        self.files.clear()
        self.tree.delete(*self.tree.get_children(""))
        self._show_details()
        self._update_count()

        def work():
            for p in find_3mf(folder, self.v_sub.get()):
                if sid != self.scan_id:
                    return
                self.q.put(("add", sid, self._inspect(p)))
            self.q.put(("scanned", sid, None))
        threading.Thread(target=work, daemon=True).start()

    # ----------------------------------------------------------------- convert
    def convert(self):
        if self.busy:
            return
        jobs = [p for p, f in self.files.items() if f["checked"] and f["info"]["kind"] in CONVERTIBLE]
        if not jobs:
            self.set_state("Nothing ticked yet  -  tick a file, or press Check all", "warn")
            messagebox.showinfo(APP, "Tick at least one file first (or press Check all).")
            return
        tpl = self.v_tpl.get().strip()
        if not os.path.isfile(tpl):
            tpl = core.find_default_template()      # stale / missing path -> fall back to the bundled one
            self.v_tpl.set(tpl)
        if not os.path.isfile(tpl):
            messagebox.showerror(APP, "ad5x_template.json is missing.\nRebuild with build_exe.bat (keep ad5x_template.json in "
                                 "the same folder), or pick a template under Advanced.")
            return
        outs = {p: self.out_path(p) for p in jobs}
        for o in set(outs.values()):
            try:
                os.makedirs(os.path.dirname(o), exist_ok=True)
            except OSError as ex:
                messagebox.showerror(APP, f"Cannot create output folder:\n{ex}")
                return
        if self.v_mode.get() == "replace":
            if not messagebox.askyesno(APP, f"This will REPLACE {len(jobs)} original .3mf file(s) with the converted "
                                            "AD5X version.\nThe originals cannot be recovered afterwards.\n\nContinue?",
                                       icon="warning"):
                return
        else:
            exist = [o for o in outs.values() if os.path.exists(o)]
            if exist and not messagebox.askyesno(APP, f"{len(exist)} output file(s) already exist and will be overwritten. Continue?"):
                return
        self.busy = True
        self.btn_go.set_state("disabled")
        self.btn_openout.pack_forget()
        self.pb.configure(maximum=len(jobs), value=0)
        self.pb.pack(side="left", before=self.lb_state)
        self.toggle_log(True)
        self.set_state(f"Converting {len(jobs)} file(s)...", "accent")
        keep, rep_on = False, self.v_report.get()   # speeds are always replaced by AD5X values, like the web converter
        threading.Thread(target=self._worker, args=(jobs, outs, tpl, keep, rep_on, self.v_prune.get()), daemon=True).start()

    def _worker(self, jobs, outs, tpl, keep, rep_on, prune=True):
        ok = bad = 0
        t0 = time.time()
        for n, src in enumerate(jobs, 1):
            dst = outs[src]
            self.q.put(("log", f"[{n}/{len(jobs)}] {os.path.basename(src)}", None))
            self.q.put(("status", src, "Converting...", ""))
            try:
                rep, _ = core.convert(src, dst, tpl, keep, prune)
                if rep_on:
                    core.write_report(dst + ".report.txt", src, dst, rep)
                warns = list(dict.fromkeys(rep["warn"]))
                summ = core.summary(rep)
                self.q.put(("log", f"    OK  -> {dst}\n    {summ}", "ok"))
                sp = rep.get("speeds", [])
                if sp:
                    chg = [s for s in sp if "(same)" not in s]
                    self.q.put(("log", f"    speeds: {len(sp)} replaced with AD5X values"
                                       + (f"  ({'; '.join(chg[:6])}{' ...' if len(chg) > 6 else ''})" if chg else ""), "muted"))
                for w in warns:
                    self.q.put(("log", f"    WARNING: {w}", "warn"))
                for w in dict.fromkeys(rep["notes"]):
                    self.q.put(("log", f"    note: {w}", "muted"))
                self.q.put(("status", src, "Done (warnings)" if warns else "Done",
                            ("Warnings:\n- " + "\n- ".join(warns)) if warns else "Converted without warnings."))
                ok += 1
            except BaseException as ex:      # core uses SystemExit for user-facing errors
                msg = str(ex) or ex.__class__.__name__
                self.q.put(("log", f"    FAILED: {msg}", "fail"))
                self.q.put(("status", src, "Failed", msg))
                bad += 1
            self.q.put(("progress", n, None))
        self.q.put(("done", (ok, bad, sorted({os.path.dirname(o) for o in outs.values()}), time.time() - t0), None))

    def _open_out(self):
        if self.last_out:
            open_folder(self.last_out[0])

    def _poll(self):
        try:
            for _ in range(200):
                m = self.q.get_nowait()
                kind, a, b, rest = m[0], m[1], m[2], m[3:]
                if kind == "add":
                    if a == self.scan_id:
                        self._add(*b)
                elif kind == "scanned":
                    if a == self.scan_id:
                        self._rebuild()
                        self.set_state(f"Found {len(self.files)} .3mf file(s)" if b is None else f"{len(self.files)} file(s) in the list",
                                       "muted")
                elif kind == "log":
                    self._say(a, b)
                elif kind == "status":
                    f = self.files.get(a)
                    if f:
                        f["status"] = b
                        f["msg"] = rest[0] if rest and rest[0] else ""
                        f["checked"] = f["checked"] and not b.startswith("Done")
                        self._refresh(a)
                        if self.tree.selection() and self.tree.selection()[0] == a:
                            self._show_details()
                    self.set_state(f"{b}: {os.path.basename(a)}", "accent")
                elif kind == "progress":
                    self.pb.configure(value=a)
                elif kind == "done":
                    ok, bad, folders, secs = a
                    self.busy = False
                    self.btn_go.set_state("normal")
                    self.last_out = folders
                    self.set_state(f"Finished in {secs:.1f} s:  {ok} converted, {bad} failed", "ok" if not bad else "warn")
                    self._say(f"\nFinished: {ok} converted, {bad} failed.\nOpen the result in OrcaSlicer with "
                              "File > Open Project (do not drag it in).", "ok" if not bad else "warn")
                    if ok:
                        self.btn_openout.pack(side="right", padx=self.S(8))
                        if self.v_open.get() and folders:
                            open_folder(folders[0])
                    self._rebuild()
        except queue.Empty:
            pass
        self.after(100, self._poll)

    def _say(self, text, tag=None):
        self.txt_log.configure(state="normal")
        self.txt_log.insert("end", text + "\n", tag or ())
        self.txt_log.see("end")
        self.txt_log.configure(state="disabled")


if __name__ == "__main__":
    App().mainloop()
