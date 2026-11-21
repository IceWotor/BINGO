"""Shared pieces for the pixel-style pages.

  * Asset lookup with drawn fallbacks (Art, ArtButton). A page lists its images in an ASSETS
    dict and calls register_assets(ASSETS). Drop a PNG with the listed name into the listed
    folder and it is used; if no file exists a plain drawing is shown instead.
  * Small widgets and helpers (add_border, text, line_label, notice).
  * StepBar: the SCAN > PREVIEW > RECOVER > BINGO! progress row at the bottom of a page.
    Its images are listed in STEP_ASSETS below.
"""
import math
import os

from kivy.core.image import Image as CoreImage
from kivy.core.text import Label as CoreLabel
from kivy.graphics import Color, Line, Rectangle, RoundedRectangle, Triangle
from kivy.metrics import dp
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.widget import Widget

FONT = "./assets/fonts/PixelifySans.ttf"
FONT_PX = "./assets/fonts/PressStart2P.ttf"
AMBER = (1, 0.749, 0.2, 1)
PURPLE = (0.38, 0.2, 0.9, 1)
CYAN = (0.2, 0.75, 1, 1)
DIM = (0.55, 0.45, 0.85, 1)
WHITE = (1, 1, 1, 1)
PANEL = (0.08, 0.04, 0.22, 1)

# ----------------------------------------------------------------- step bar settings
STEP_FOLDER = "./assets/pageAssets/steps/"
# key -> [paths], first existing wins. "_off" is the not-reached-yet look.
STEP_ASSETS = {
    "stepbar_scan":    [STEP_FOLDER + "stepbar_scan.png"],
    "stepbar_preview": [STEP_FOLDER + "stepbar_preview.png"],
    "stepbar_recover": [STEP_FOLDER + "stepbar_recover.png"],
    "stepbar_bingo":   [STEP_FOLDER + "stepbar_bingo.png"],
}
# key, label (markup allowed)
STEPS = [
    ("scan", "SCAN"),
    ("preview", "PREVIEW"),
    ("recover", "RECOVER"),
    ("bingo", "[color=ff5555]B[/color][color=ffa940]I[/color][color=ffe14d]N[/color]"
              "[color=3fc78c]G[/color][color=33c4ff]O[/color][color=b07cff]![/color]"),
]

# ----------------------------------------------------------------- asset lookup
_REGISTRY = {}


def register_assets(table):
    _REGISTRY.update(table)


def find_asset(key):
    for path in _REGISTRY.get(key, ()):
        if os.path.exists(path):
            return path
    return None


register_assets(STEP_ASSETS)

_tex = {}


def texture(path):
    if path not in _tex:
        t = CoreImage(path).texture
        t.mag_filter = "nearest"          # keep pixel art crisp
        t.min_filter = "nearest"
        _tex[path] = t
    return _tex[path]


class Art(Widget):
    """Shows the asset registered under `key` stretched to its size, or calls
    fallback(widget) to draw a plain version when no file exists."""

    def __init__(self, key=None, fallback=None, **kwargs):
        super().__init__(**kwargs)
        self.key = key
        self.fallback = fallback
        self.bind(pos=self.redraw, size=self.redraw)
        self.redraw()

    def redraw(self, *args):
        self.canvas.clear()
        src = find_asset(self.key)
        with self.canvas:
            if src:
                Color(1, 1, 1, 1)
                Rectangle(texture=texture(src), pos=self.pos, size=self.size)
            elif self.fallback:
                self.fallback(self)

    def set_art(self, key, fallback=None):
        self.key = key
        self.fallback = fallback
        self.redraw()


class ArtButton(ButtonBehavior, Art):
    """Art you can tap. Bind on_release as usual."""

    def __init__(self, key, fallback=None, **kwargs):
        super().__init__(**kwargs)
        self.key, self.fallback = key, fallback
        self.redraw()


# ----------------------------------------------------------------- fallback drawings
def star(cx, cy, r, color):
    pts = []
    for k in range(10):
        ang = math.pi / 2 + k * math.pi / 5
        rad = r if k % 2 == 0 else r * 0.42
        pts.append((cx + rad * math.cos(ang), cy + rad * math.sin(ang)))
    Color(*color)
    for k in range(10):
        a, b = pts[k], pts[(k + 1) % 10]
        Triangle(points=[cx, cy, a[0], a[1], b[0], b[1]])


def fb_frame(wd):
    Color(*PANEL)
    Rectangle(pos=wd.pos, size=wd.size)
    Color(0.3, 0.15, 0.85, 1)
    Line(rectangle=(wd.x, wd.y, wd.width, wd.height), width=2.5)
    Color(0.5, 0.35, 1, 0.5)
    Line(rectangle=(wd.x + dp(6), wd.y + dp(6), wd.width - dp(12), wd.height - dp(12)),
         width=1)


def fb_continue(wd):
    Color(0.95, 0.25, 0.5, 1)
    Rectangle(pos=wd.pos, size=wd.size)
    Color(1, 0.6, 0.75, 1)
    Line(rectangle=(wd.x, wd.y, wd.width, wd.height), width=2)
    lab = CoreLabel(text="CONTINUE", font_size=dp(15), font_name=FONT_PX)
    lab.refresh()
    t = lab.texture
    Color(1, 1, 1, 1)
    Rectangle(texture=t, size=t.size,
              pos=(wd.x + (wd.width - t.width) / 2, wd.y + (wd.height - t.height) / 2))


def fb_chevron(direction):
    def draw(wd):
        x, y, w, h = wd.x, wd.y, wd.width, wd.height
        Color(0.25, 0.55, 1, 1)
        if direction == "down":
            pts = [x + .25 * w, y + .65 * h, x + .5 * w, y + .35 * h, x + .75 * w, y + .65 * h]
        else:
            pts = [x + .35 * w, y + .25 * h, x + .65 * w, y + .5 * h, x + .35 * w, y + .75 * h]
        Line(points=pts, width=2.2)
    return draw


def fb_file(wd):
    x, y, w, h = wd.x, wd.y, wd.width, wd.height
    Color(0.35, 0.4, 0.95, 1)
    Rectangle(pos=(x + .15 * w, y + .05 * h), size=(.7 * w, .9 * h))
    Color(0.85, 0.88, 1, 1)
    for k in range(3):
        Rectangle(pos=(x + .28 * w, y + (.28 + k * .17) * h), size=(.44 * w, .06 * h))


def fb_sparkle(wd):
    x, y, w, h = wd.x, wd.y, wd.width, wd.height
    Color(0.3, 0.55, 1, 1)
    Line(points=[x + .5 * w, y + .95 * h, x + .6 * w, y + .6 * h, x + .95 * w, y + .5 * h,
                 x + .6 * w, y + .4 * h, x + .5 * w, y + .05 * h, x + .4 * w, y + .4 * h,
                 x + .05 * w, y + .5 * h, x + .4 * w, y + .6 * h], width=1.8, close=True)
    Color(0.5, 0.75, 1, 1)
    Rectangle(pos=(x + .44 * w, y + .44 * h), size=(.12 * w, .12 * h))


def fb_swatch(fill, edge):
    def draw(wd):
        Color(*fill)
        RoundedRectangle(pos=wd.pos, size=wd.size, radius=[dp(3)])
        Color(*edge)
        Line(rounded_rectangle=(wd.x, wd.y, wd.width, wd.height, dp(3)), width=1.4)
    return draw


def fb_dash(done):
    def draw(wd):
        Color(*(AMBER if done else PURPLE))
        Line(points=[wd.x, wd.center_y, wd.right, wd.center_y], width=1.4,
             dash_length=3, dash_offset=3)
    return draw


def fb_step(key, done):
    col = AMBER if done else PURPLE

    def draw(wd):
        cx, cy = wd.center
        r = min(wd.width, wd.height) / 2
        pts = []
        for k in range(8):
            a = math.pi / 8 + k * math.pi / 4
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
        Color(0.06, 0.03, 0.2, 1)
        for k in range(8):
            a, b = pts[k], pts[(k + 1) % 8]
            Triangle(points=[cx, cy, a[0], a[1], b[0], b[1]])
        Color(*col)
        Line(points=[c for p in pts for c in p], close=True, width=1.8)
        if key == "scan":
            star(cx, cy, r * .5, col)
        elif key == "preview":
            Line(circle=(cx - r * .08, cy + r * .08, r * .3), width=1.6)
            Line(points=[cx + r * .14, cy - r * .14, cx + r * .42, cy - r * .42], width=2)
        elif key == "recover":
            Line(rectangle=(cx - r * .4, cy - r * .28, r * .8, r * .56), width=1.6)
            Line(points=[cx, cy - r * .28, cx, cy + r * .28], width=1.6)
    return draw


# ----------------------------------------------------------------- small widgets
def esc(s):
    return str(s).replace("&", "&amp;").replace("[", "&bl;").replace("]", "&br;")


def add_border(wd, color=PURPLE, radius=dp(8), width=1.8, fill=PANEL):
    with wd.canvas.before:
        Color(*fill)
        bg = RoundedRectangle(radius=[radius])
        Color(*color)
        ln = Line(width=width)

    def upd(*args):
        bg.pos, bg.size = wd.pos, wd.size
        ln.rounded_rectangle = (wd.x, wd.y, wd.width, wd.height, radius)

    wd.bind(pos=upd, size=upd)
    upd()


def text(txt, size, color=WHITE, font=FONT, halign="left", height=None, **kwargs):
    """Label that wraps to its width. height=None -> grows with the text."""
    lab = Label(text=txt, font_name=font, font_size=size, color=color, markup=True,
                halign=halign, valign="middle", size_hint_y=None, **kwargs)
    lab.bind(width=lambda i, v: setattr(i, "text_size", (v, None)))
    if height is None:
        lab.bind(texture_size=lambda i, v: setattr(i, "height", v[1] + dp(4)))
    else:
        lab.height = height
    return lab


def line_label(txt, size, color=WHITE, font=FONT, halign="left", **kwargs):
    """Single-line label that fills the height of its row, text centred vertically."""
    lab = Label(text=txt, font_name=font, font_size=size, color=color, markup=True,
                halign=halign, valign="middle", **kwargs)
    lab.bind(size=lambda i, v: setattr(i, "text_size", v))
    return lab


def notice(msg):
    lab = Label(text=msg, font_name=FONT, font_size="13sp", halign="center", valign="middle")
    lab.bind(size=lambda i, v: setattr(i, "text_size", v))
    Popup(title="", separator_height=0, content=lab, size_hint=(0.85, 0.3)).open()

class StepBar(Art):
    """The whole SCAN > PREVIEW > RECOVER > BINGO! row as one image."""

    def __init__(self, current="recover", **kwargs):
        super().__init__("stepbar_" + current, None, size_hint=(0.6, None),
                         pos_hint={"center_x": .5}, height=dp(70), **kwargs)
        self.bind(width=self._fit_height)

    def _fit_height(self, *args):
        # keep the image's own proportions so it doesn't get squashed
        src = find_asset(self.key)
        if src:
            tw, th = texture(src).size
            self.height = self.width * th / tw