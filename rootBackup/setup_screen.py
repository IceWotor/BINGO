"""Bingo setup screen: choose a term set, a difficulty and the game options.

Sits between Content Review ("Complete reviewer") and the game.

EASY TO CHANGE
  * ASSETS       every image the screen uses. Drop a PNG with the listed name into
                 assets/pageAssets/bingosetup/ (or edit the path) and it is used. If no
                 file exists the widget draws a plain fallback, so the screen always works.
  * DIFFICULTIES the cards in section 2 (grid size, labels, which one gets the star).
  * OPTIONS      the checkboxes in section 3 (text and default value).
  * HOW_TO       the text in the "How to play" box.
"""
import math
import os

from kivy.app import App
from kivy.core.image import Image as CoreImage
from kivy.core.text import Label as CoreLabel
from kivy.graphics import Color, Ellipse, Line, Rectangle, RoundedRectangle, Triangle
from kivy.metrics import dp
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.dropdown import DropDown
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.screenmanager import Screen
from kivy.uix.widget import Widget

# ----------------------------------------------------------------- settings
FOLDER = "./assets/pageAssets/bingosetup/"

# name -> list of paths, first one that exists wins. No file at all -> drawn fallback.
ASSETS = {
    "frame":       [FOLDER + "frame.png",
                    "./assets/pageAssets/extractedcontent/setContainer.png"],  # big panel
    "continue":    [FOLDER + "continue.png",
                    "./assets/pageAssets/manual/continueButton.png"],          # pink button
    "back":        [FOLDER + "back.png", "./assets/icons/backButton.png"],
    "arrow":       [FOLDER + "dropdown_arrow.png"],   # little box with a triangle
    "info":        [FOLDER + "info.png"],             # the (i) next to the hint
    "divider":     [FOLDER + "divider.png"],          # dotted line between sections
    "diff_easy":   [FOLDER + "diff_easy.png"],        # 3 x 3 dots icon
    "diff_medium": [FOLDER + "diff_medium.png"],      # 4 x 4 dots icon
    "diff_hard":   [FOLDER + "diff_hard.png"],        # 5 x 5 dots icon
    "card":        [FOLDER + "diff_card.png"],        # difficulty card, not selected
    "card_on":     [FOLDER + "diff_card_on.png"],     # difficulty card, selected
    "badge":       [FOLDER + "badge_star.png"],       # round star on the recommended card
    "check_on":    [FOLDER + "check_on.png"],
    "check_off":   [FOLDER + "check_off.png"],
    "howto_star":  [FOLDER + "howto_star.png"],
}

# key, grid size, big label, small label
DIFFICULTIES = [
    ("easy", 3, "3 x 3", "Easy"),
    ("medium", 4, "4 x 4", "Medium"),
    ("hard", 5, "5 x 5", "Hard"),
]
DEFAULT_DIFFICULTY = "easy"
RECOMMENDED = "medium"          # gets the star badge; "" = no badge

# key, title, description, default value
OPTIONS = [
    ("shuffle", "Shuffle terms on card",
     "Shuffle terms every time a new game is started", True),
    ("free_center", "Free center",
     "Enables the free space in the middle of each card", True),
    ("show_answer", "Show correct answer after selection",
     "Reveal the correct term after answering incorrectly", False),
]
NO_FREE_CENTER_NOTE = "Only on 3 x 3 and 5 x 5 cards (they have a middle square)"

HOW_TO = ("Read the definition, then choose the correct term.\n"
          "Get all answers correct (blackout) to BINGO!")

FONT = "./assets/fonts/PixelifySans.ttf"
FONT_PX = "./assets/fonts/PressStart2P.ttf"
AMBER = (1, 0.749, 0.2, 1)
PURPLE = (0.38, 0.2, 0.9, 1)
CYAN = (0.2, 0.75, 1, 1)
DIM = (0.55, 0.45, 0.85, 1)
WHITE = (1, 1, 1, 1)
PANEL = (0.08, 0.04, 0.22, 1)


# ----------------------------------------------------------------- asset helpers
def find_asset(key):
    for path in ASSETS.get(key, ()):
        if os.path.exists(path):
            return path
    return None


_tex = {}


def texture(path):
    if path not in _tex:
        t = CoreImage(path).texture
        t.mag_filter = "nearest"          # keep pixel art crisp
        t.min_filter = "nearest"
        _tex[path] = t
    return _tex[path]


class Art(Widget):
    """Shows ASSETS[key] stretched to its size, or draws fallback(widget) if no file."""

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


class ArtButton(ButtonBehavior, Art):
    """Art you can tap. Bind on_release as usual."""

    def __init__(self, key, fallback=None, **kwargs):
        super().__init__(**kwargs)
        self.key, self.fallback = key, fallback
        self.redraw()


# ----------------------------------------------------------------- fallback drawings
def _star(cx, cy, r, color):
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


def fb_back(wd):
    Color(1, 0.2, 0.6, 1)
    x, y, w, h = wd.x, wd.y, wd.width, wd.height
    Line(points=[x + .6 * w, y + .55 * h, 
                 x + .35 * w, y + .5 * h, 
                 x + .6 * w, y + .25 * h],
         width=1.2)


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


def fb_arrow(wd):
    x, y, w, h = wd.x, wd.y, wd.width, wd.height
    Color(0.12, 0.06, 0.4, 1)
    Rectangle(pos=wd.pos, size=wd.size)
    Color(0.55, 0.4, 1, 1)
    Line(rectangle=(x, y, w, h), width=1.6)
    Color(0.85, 0.7, 1, 1)
    Triangle(points=[x + .28 * w, y + .62 * h, x + .72 * w, y + .62 * h,
                     x + .5 * w, y + .3 * h])


def fb_info(wd):
    cx, cy = wd.center
    r = min(wd.width, wd.height) / 2
    Color(*DIM)
    Line(circle=(cx, cy, r), width=1.2)
    Rectangle(pos=(cx - r * .09, cy - r * .5), size=(r * .18, r * .6))
    Rectangle(pos=(cx - r * .09, cy + r * .3), size=(r * .18, r * .18))


def fb_divider(wd):
    Color(0.38, 0.2, 0.9, 1)
    Line(points=[wd.x, wd.center_y, wd.right, wd.center_y], width=1.6,
         dash_length=2, dash_offset=3)


def fb_dots(n):
    def draw(wd):
        side = min(wd.width, wd.height)
        d = side / (n + (n - 1) * 0.6)
        g = d * 0.6
        x0 = wd.center_x - side / 2
        y0 = wd.center_y - side / 2
        Color(*WHITE)
        for r in range(n):
            for c in range(n):
                Rectangle(pos=(x0 + c * (d + g), y0 + r * (d + g)), size=(d, d))
    return draw


def fb_card(on):
    def draw(wd):
        Color(*PANEL)
        RoundedRectangle(pos=wd.pos, size=wd.size, radius=[dp(8)])
        Color(*(CYAN if on else PURPLE))
        Line(rounded_rectangle=(wd.x, wd.y, wd.width, wd.height, dp(8)), width=1.8)
    return draw


def fb_badge(wd):
    cx, cy = wd.center
    r = min(wd.width, wd.height) / 2
    Color(0.15, 0.4, 0.95, 1)
    Ellipse(pos=(cx - r, cy - r), size=(2 * r, 2 * r))
    _star(cx, cy, r * .6, WHITE)


def fb_howto_star(wd):
    _star(wd.center_x, wd.center_y, min(wd.width, wd.height) / 2, (0.2, 0.55, 1, 1))


def fb_check(on):
    def draw(wd):
        x, y, w, h = wd.x, wd.y, wd.width, wd.height
        if on:
            Color(0.1, 0.55, 0.28, 1)
            Rectangle(pos=wd.pos, size=wd.size)
            Color(1, 1, 1, 1)
            Line(points=[x + .22 * w, y + .5 * h, x + .42 * w, y + .3 * h,
                         x + .78 * w, y + .7 * h], width=2)
        else:
            Color(0.45, 0.35, 0.85, 1)
            Line(rectangle=(x, y, w, h), width=1.4)
    return draw


# ----------------------------------------------------------------- small widgets
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


def notice(msg):
    lab = Label(text=msg, font_name=FONT, font_size="13sp", halign="center", valign="middle")
    lab.bind(size=lambda i, v: setattr(i, "text_size", v))
    Popup(title="", separator_height=0, content=lab, size_hint=(0.85, 0.3)).open()


class SetPicker(ButtonBehavior, FloatLayout):
    """Box showing the chosen term set; tap to open the list."""

    def __init__(self, **kwargs):
        super().__init__(size_hint_y=None, height=dp(64), **kwargs)
        add_border(self)
        col = BoxLayout(orientation="vertical", padding=(dp(14), dp(8), dp(60), dp(8)))
        self.name = text("", "14sp", height=dp(24))
        self.count = text("", "10sp", color=DIM, height=dp(18))
        col.add_widget(self.name)
        col.add_widget(self.count)
        self.add_widget(col)
        self.add_widget(Art("arrow", fb_arrow, size_hint=(None, None),
                            size=(dp(34), dp(34)), pos_hint={"right": 0.96, "center_y": .5}))


class DifficultyCard(ButtonBehavior, FloatLayout):
    def __init__(self, key, n, big, small, recommended, on_pick, **kwargs):
        super().__init__(**kwargs)
        self.key, self.on_pick = key, on_pick
        self.bg = Art("card", fb_card(False), size_hint=(1, 1))
        self.add_widget(self.bg)
        self.add_widget(Art("diff_" + key, fb_dots(n), size_hint=(None, None),
                            size=(dp(44), dp(44)), pos_hint={"center_x": .5, "top": .88}))
        big_lbl = text(big, "11sp", font=FONT, halign="center", height=dp(20))
        big_lbl.size_hint = (1, None)
        big_lbl.pos_hint = {"center_x": .5, "center_y": .30}
        small_lbl = text(small, "11sp", color=DIM, halign="center", height=dp(18))
        small_lbl.size_hint = (1, None)
        small_lbl.pos_hint = {"center_x": .5, "center_y": .14}
        self.add_widget(big_lbl)
        self.add_widget(small_lbl)
        if recommended:
            self.add_widget(Art("badge", fb_badge, size_hint=(None, None),
                                size=(dp(28), dp(28)), pos_hint={"right": 1.0, "top": 1.12}))

    def set_selected(self, on):
        self.bg.key = "card_on" if on else "card"
        self.bg.fallback = fb_card(on)
        self.bg.redraw()

    def on_release(self):
        self.on_pick(self.key)


class OptionRow(ButtonBehavior, BoxLayout):
    def __init__(self, key, title, desc, value, on_toggle, **kwargs):
        super().__init__(size_hint_y=None, height=dp(54), spacing=dp(12), **kwargs)
        self.key, self.value, self.enabled = key, value, True
        self.desc_text, self.on_toggle = desc, on_toggle
        self.box = Art("check_off", fb_check(False), size_hint=(None, None),
                       size=(dp(26), dp(26)), pos_hint={"center_y": .5})
        self.add_widget(self.box)
        col = BoxLayout(orientation="vertical", spacing=dp(2))
        self.title = text(title, "11sp", height=dp(18))
        self.desc = text(desc, "8sp", color=DIM, height=dp(30))
        col.add_widget(self.title)
        col.add_widget(self.desc)
        self.add_widget(col)
        self.refresh()

    def refresh(self):
        on = self.value and self.enabled
        self.box.key = "check_on" if on else "check_off"
        self.box.fallback = fb_check(on)
        self.box.redraw()
        self.opacity = 1 if self.enabled else 0.45

    def set_enabled(self, enabled, note=None):
        self.enabled = enabled
        self.desc.text = note if (not enabled and note) else self.desc_text
        self.refresh()

    def on_release(self):
        if not self.enabled:
            return
        self.value = not self.value
        self.refresh()
        self.on_toggle(self.key, self.value)


# ----------------------------------------------------------------- the screen
class BingoSetup(Screen):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.set_id = None
        self.sets = []                       # [(id, name, term count)]
        self.difficulty = DEFAULT_DIFFICULTY
        self.opts = {k: default for k, _, _, default in OPTIONS}
        self.cards, self.rows = {}, {}

        with self.canvas.before:
            Color(0.047, 0, 0.129, 1)
            self._bg = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._upd_bg, size=self._upd_bg)

        outer = BoxLayout(orientation="vertical")
        outer.add_widget(Widget(size_hint_y=None, height=dp(50)))
        body = FloatLayout()
        outer.add_widget(body)
        self.add_widget(outer)

        body.add_widget(Art("frame", fb_frame, size_hint=(0.97, 0.85),
                            pos_hint={"center_x": .5, "top": 0.96}))

        scroll = ScrollView(size_hint=(0.82, 0.71),
                            pos_hint={"center_x": .5, "center_y": 0.55}, bar_width=0)
        col = BoxLayout(orientation="vertical", size_hint_y=None,
                        padding=(dp(4), dp(14)), spacing=dp(12))
        col.bind(minimum_height=col.setter("height"))
        scroll.add_widget(col)
        body.add_widget(scroll)

        # 1. term set
        col.add_widget(text("1. SELECT A TERM SET", "13sp", AMBER, FONT, height=dp(26)))
        self.picker = SetPicker()
        self.picker.bind(on_release=self._open_list)
        col.add_widget(self.picker)
        hint = BoxLayout(size_hint_y=None, height=dp(30), spacing=dp(30))
        hint.add_widget(Art("info", fb_info, size_hint=(None, None), size=(dp(14), dp(14)),
                            pos_hint={"center_y": .5}))
        link = text("You can review or edit this set in "
                    "[ref=cr][color=33c4ff]Content Review[/color][/ref].",
                    "9sp", DIM, height=dp(30))
        link.bind(on_ref_press=lambda *a: self.go_content_review())
        hint.add_widget(link)
        col.add_widget(hint)
        col.add_widget(Art("divider", fb_divider, size_hint_y=None, height=dp(3)))

        # 2. difficulty
        col.add_widget(text("2. SELECT DIFFICULTY", "11sp", AMBER, FONT, height=dp(26)))
        row = BoxLayout(size_hint_y=None, height=dp(118), spacing=dp(10))
        for key, n, big, small in DIFFICULTIES:
            card = DifficultyCard(key, n, big, small, key == RECOMMENDED, self._pick)
            self.cards[key] = card
            row.add_widget(card)
        col.add_widget(row)
        col.add_widget(Art("divider", fb_divider, size_hint_y=None, height=dp(3)))

        # 3. options
        col.add_widget(text("3. GAME OPTIONS", "11sp", AMBER, FONT, height=dp(26)))
        box = BoxLayout(orientation="vertical", size_hint_y=None,
                        padding=dp(14), spacing=dp(10))
        box.bind(minimum_height=box.setter("height"))
        add_border(box)
        for key, title, desc, default in OPTIONS:
            r = OptionRow(key, title, desc, default, self._toggle)
            self.rows[key] = r
            box.add_widget(r)
        col.add_widget(box)
        col.add_widget(Art("divider", fb_divider, size_hint_y=None, height=dp(3)))

        # how to play
        how = BoxLayout(orientation="vertical", size_hint_y=None, padding=dp(12),
                        spacing=dp(6))
        how.bind(minimum_height=how.setter("height"))
        add_border(how)
        head = BoxLayout(size_hint_y=None, height=dp(20), spacing=dp(6))
        head.add_widget(Widget())
        head.add_widget(Art("howto_star", fb_howto_star, size_hint=(None, None),
                            size=(dp(16), dp(16)), pos_hint={"center_y": .5}))
        head.add_widget(text("HOW TO PLAY:", "12sp", CYAN, FONT, height=dp(20),
                             size_hint_x=None, width=dp(130)))
        head.add_widget(Widget())
        how.add_widget(head)
        how.add_widget(text(HOW_TO, "10sp", halign="center"))
        col.add_widget(how)

        # back and continue
        back = ArtButton("back", fb_back, size_hint=(None, None), size=(dp(64), dp(16)),
                         pos_hint={"x": 0.03, "top": 0.99})
        back.bind(on_release=lambda *a: self.go_back())
        body.add_widget(back)

        go = ArtButton("continue", fb_continue, size_hint=(0.58, 0.09),
                       pos_hint={"center_x": .5, "center_y": 0.09})
        go.bind(width=lambda i, v: setattr(i, "height", v * 70 / 344))
        go.bind(on_release=lambda *a: self.go_play())
        body.add_widget(go)

        self._refresh_difficulty()

    # ---------------------------------------------------------------- helpers
    def _upd_bg(self, *args):
        self._bg.pos, self._bg.size = self.pos, self.size

    def _grid_size(self):
        return next(n for k, n, _, _ in DIFFICULTIES if k == self.difficulty)

    def _refresh_difficulty(self):
        for key, card in self.cards.items():
            card.set_selected(key == self.difficulty)
        free = self.rows.get("free_center")
        if free is not None:
            free.set_enabled(self._grid_size() % 2 == 1, NO_FREE_CENTER_NOTE)

    def _pick(self, key):
        self.difficulty = key
        self._refresh_difficulty()

    def _toggle(self, key, value):
        self.opts[key] = value

    def _show_set(self):
        cur = next((s for s in self.sets if s[0] == self.set_id), None)
        if cur is None:
            self.picker.name.text = "No term sets yet"
            self.picker.count.text = ""
            return
        self.picker.name.text = cur[1]
        self.picker.count.text = "%d term%s" % (cur[2], "" if cur[2] == 1 else "s")

    def _open_list(self, *args):
        if not self.sets:
            return
        dd = DropDown(auto_width=False, width=self.picker.width)
        for sid, name, count in self.sets:
            btn = Button(text="%s  (%d)" % (name, count), font_name=FONT, font_size="12sp",
                         size_hint_y=None, height=dp(42), color=WHITE,
                         background_normal="", background_down="",
                         background_color=(0.12, 0.07, 0.35, 1))
            btn.bind(on_release=lambda b, s=sid: self._choose(dd, s))
            dd.add_widget(btn)
        dd.open(self.picker)

    def _choose(self, dd, set_id):
        dd.dismiss()
        self.set_id = set_id
        self._show_set()

    # ---------------------------------------------------------------- navigation
    def open_for(self, review_set_id):
        """Call before switching to this screen."""
        db = App.get_running_app().db
        self.sets = [(sid, name, db.get_term_count(sid))
                     for sid, name in db.get_review_sets()]
        ids = [s[0] for s in self.sets]
        self.set_id = review_set_id if review_set_id in ids else (ids[0] if ids else None)
        self._show_set()
        self._refresh_difficulty()

    def go_content_review(self):
        if self.set_id is None:
            return
        cr = self.manager.get_screen("contentreview")
        cr.review_set_id = self.set_id
        cr.ids.reviewSetName.text = next((s[1] for s in self.sets if s[0] == self.set_id), "")
        cr.load_entries()
        self.manager.transition.direction = "right"
        self.manager.current = "contentreview"

    def go_back(self):
        self.go_content_review()

    def go_play(self):
        cur = next((s for s in self.sets if s[0] == self.set_id), None)
        if cur is None or cur[2] == 0:
            notice("This term set has no terms yet. Add some in Content Review first.")
            return
        game = self.manager.get_screen("bingogame")
        game.start_game(cur[0], cur[1], size=self._grid_size(),
                        shuffle=self.opts["shuffle"],
                        free_center=self.opts["free_center"],
                        show_answer=self.opts["show_answer"])
        self.manager.transition.direction = "left"
        self.manager.current = "bingogame"