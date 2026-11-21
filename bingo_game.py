"""Bingo game screen. One definition per question and a card of terms to pick from.

Tap a term to select it (cyan), tap the same term again to confirm. The top panel then
turns green (correct) or red (incorrect), and the next question follows after a moment.

Built around the images in assets/pageAssets/bingogame/. Several of them have things drawn
into them (the scroll in the definition panel, "Correct!" / "Incorrect!", the "3 X 3 SET"
label in the card frame, the lines and sparkles around the streak), so the text of this
page is laid over them at the positions set in LAYOUT.

EASY TO CHANGE
  * ASSETS   the image files. Keep the names, or edit the names here. A missing image is
             drawn in code instead, so the page works without it.
  * TEXT     the words on the page.
  * STYLE    colours, font sizes, how long the result stays up.
  * LAYOUT   sizes and where the text sits on each image (fractions of that image).
  Shared helpers (Art, line_label...) are in ui_kit.py. The tap logic is in
  BingoGame.on_cell, the card building in build_card.
"""
import random
from types import SimpleNamespace

from kivy.app import App
from kivy.clock import Clock
from kivy.core.text import Label as CoreLabel
from kivy.graphics import Color, Line, Rectangle, RoundedRectangle, Triangle
from kivy.metrics import dp
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen
from kivy.uix.widget import Widget

from ui_kit import (AMBER, FONT, FONT_PX, WHITE, Art, fb_back, fb_frame, fb_sparkle,
                    find_asset, line_label, register_assets, star, texture)

# ----------------------------------------------------------------- assets
FOLDER = "./assets/pageAssets/bingogame/"
ASSETS = {
    "g_frame":        [FOLDER + "background.png"],            # whole page: frame and night sky
    "g_title":        [FOLDER + "bingotTopLogo.png", FOLDER + "bingoTopLogo.png"],
    "g_back":         [FOLDER + "back.png"],
    "g_star":         [FOLDER + "scoreStar.png"],             # star next to the score
    "g_divider":      [FOLDER + "divdier.png", FOLDER + "divider.png"],
    "g_def_card":     [FOLDER + "definitionPanel.png"],       # definition (scroll icon is in it)
    "g_card_ok":      [FOLDER + "correctDefinition.png"],     # "Correct!" is in it
    "g_card_bad":     [FOLDER + "incorrectDefinition.png"],   # "Incorrect!" is in it
    "g_grid_frame":   [FOLDER + "gameWindow.png"],            # frame around the card, with the label slot
    "g_cell":         [FOLDER + "termPanel.png"],             # a term
    "g_cell_selected": [FOLDER + "selectedTerm.png"],         # first tap (cyan)
    "g_cell_correct": [FOLDER + "correctTerm.png"],           # confirmed, right
    "g_cell_wrong":   [FOLDER + "incorrectTerm.png"],         # confirmed, wrong
    "g_cell_free":    [FOLDER + "free.png"],                  # the free space
    "g_streak":       [FOLDER + "streakCounter.png"],         # streak label with its lines
    "g_flame_on":     [FOLDER + "ongoingStreak.png"],         # streak 1 or more
    "g_flame_off":    [FOLDER + "noStreak.png"],              # streak 0
}
register_assets(ASSETS)

# width / height of each image, used when the file is missing (so the layout stays the same)
RATIOS = {
    "g_def_card": 305 / 84, "g_card_ok": 305 / 84, "g_card_bad": 305 / 84,
    "g_grid_frame": 339 / 398, "g_streak": 270 / 64, "g_cell": 93 / 86,
    "g_back": 11 / 16, "g_title": 102 / 21, "g_star": 25 / 27,
    "g_flame_on": 11 / 17, "g_flame_off": 11 / 17,
}

# ----------------------------------------------------------------- words
TEXT = dict(
    title="BINGO!",
    score="Score: %d / %d",
    question="Question %d / %d",
    set_banner="%d X %d SET",
    streak="Streak: %d",
    correct="Correct!",
    incorrect="Incorrect!",
    answer="Correct Answer: %s",
    free="FREE!",
    no_terms="This term set has no terms yet. Go back and add some first.",
)

# ----------------------------------------------------------------- look and behaviour
# per cell mode: fill, edge, text colour (fill and edge are only used for the drawn stand-ins)
STYLE = dict(
    cell={
        "normal":   ((0.09, 0.05, 0.28, 1), (0.37, 0.16, 0.84, 1), (0.72, 0.66, 0.98, 1)),
        "selected": ((0.06, 0.2, 0.42, 1), (0.36, 0.73, 0.89, 1), (0.35, 0.85, 1, 1)),
        "correct":  ((0.04, 0.3, 0.26, 1), (0.36, 0.89, 0.62, 1), (0.4, 1, 0.7, 1)),
        "wrong":    ((0.22, 0.05, 0.14, 1), (0.64, 0.12, 0.25, 1), (1, 0.35, 0.45, 1)),
    },
    # panel states for the drawn stand-ins: fill, edge
    panel={
        "question": ((0.07, 0.05, 0.25, 1), (0.2, 0.45, 0.9, 1)),
        "correct":  ((0.07, 0.25, 0.22, 1), (0.36, 0.89, 0.62, 1)),
        "wrong":    ((0.25, 0.06, 0.16, 1), (0.64, 0.12, 0.25, 1)),
    },
    correct_color=(0.4, 1, 0.7, 1),
    wrong_color=(1, 0.35, 0.45, 1),
    detail_color=(0.62, 0.6, 0.74, 1),
    banner_color=(0.85, 0.8, 1, 1),
    # definition font size by text length: (up to this many characters, size)
    def_sizes=((70, "12sp"), (130, "10sp"), (10 ** 9, "8sp")),
    cell_sizes={3: "13sp", 4: "11sp", 5: "9sp"},
    result_seconds=2.0,            # how long the green / red panel stays before the next question
    highlight_correct_cell=False,  # on a wrong answer, also turn the right term green
)

# lengths in dp, the other numbers are fractions
LAYOUT = dict(
    top_space=40,
    header_height=48,
    back_height=26,                 # arrow height (width follows the image)
    title_height=24,                # BINGO! logo height
    frame_size=(0.94, 1),           # the page frame: fraction of the page
    # where the content sits inside the frame: left, top, right, bottom (clouds are at the bottom)
    content_inset=(0.07, 0.035, 0.07, 0.115),
    gap=8,
    stats_height=34,
    star_height=26,
    divider_height=4,
    # the area of the card frame where the terms go: left, top, right, bottom
    grid_inset=(0.075, 0.14, 0.08, 0.05),
    grid_gap=10,
    banner_pos=(0.5, 0.917),        # "3 X 3 SET" centre on the card frame
    banner_size=(0.36, 0.07),
    # text areas on the definition panel: x, y, width, height (bottom left origin)
    question_text=(0.24, 0.12, 0.66, 0.76),
    answer_text=(0.10, 0.46, 0.80, 0.15),
    detail_text=(0.14, 0.05, 0.78, 0.34),
    # the inside of the streak pill
    streak_text=(0.285, 0.26, 0.40, 0.50),
    flame_height=22,
)
L = LAYOUT


# ----------------------------------------------------------------- the card (pure logic)
def build_card(terms, correct_index, n, shuffle, free):
    """-> list of n*n cells: (term, is_correct), None for the free space, ("", False) for
    padding when the set has too few terms. The right term is always on the card."""
    total = n * n
    free_on = bool(free) and n % 2 == 1                 # needs a middle square
    n_cells = total - (1 if free_on else 0)
    others = [i for i in range(len(terms)) if i != correct_index]
    if shuffle:
        random.shuffle(others)
    picked = others[:n_cells - 1] + [correct_index]
    if not shuffle:
        picked.sort()                                   # keep the set's own order
    cells = [(terms[i][0], i == correct_index) for i in picked]
    while len(cells) < n_cells:
        cells.append(("", False))
    if shuffle:
        random.shuffle(cells)
    it, out = iter(cells), []
    for pos in range(total):
        out.append(None if (free_on and pos == total // 2) else next(it))
    return out


# ----------------------------------------------------------------- image sizes
def ratio(key):
    """width / height of the image (or of its stand-in when the file is missing)."""
    src = find_asset(key)
    tex = texture(src) if src else None
    if tex is not None:
        return tex.width / float(tex.height)
    return RATIOS[key]


def scale_of(key):
    """How much bigger than a plain term cell this image is. The green, red and cyan cells
    and the free space have a glow around them, so they are drawn a little larger than the
    cell and still line up with it."""
    a, b = find_asset(key), find_asset("g_cell")
    if a and b:
        ta, tb = texture(a), texture(b)
        if ta is not None and tb is not None:
            return (ta.width / float(tb.width), ta.height / float(tb.height))
    return (1, 1)


def _frac(spec):
    """(x, y, w, h) fractions -> Kivy keyword arguments for a FloatLayout child."""
    x, y, w, h = spec
    return dict(size_hint=(w, h), pos_hint={"x": x, "y": y})


def _fill():
    """Keyword arguments that make a FloatLayout child cover its parent (a FloatLayout only
    moves children that have a pos_hint)."""
    return dict(size_hint=(1, 1), pos_hint={"x": 0, "y": 0})


# ----------------------------------------------------------------- drawn stand-ins
GOLD = (1, 0.8, 0.2, 1)


def _sub(wd, fx, fy, fw, fh):
    """A part of a widget, for drawing little pieces inside a stand-in."""
    return SimpleNamespace(x=wd.x + fx * wd.width, y=wd.y + fy * wd.height,
                           width=fw * wd.width, height=fh * wd.height,
                           center_x=wd.x + (fx + fw / 2) * wd.width,
                           center_y=wd.y + (fy + fh / 2) * wd.height)


def _text_at(txt, font, size, color, cx, cy):
    lab = CoreLabel(text=txt, font_size=size, font_name=font)
    lab.refresh()
    t = lab.texture
    Color(*color)
    Rectangle(texture=t, size=t.size, pos=(cx - t.width / 2, cy - t.height / 2))


def fb_title(wd):
    colors = [(1, 0.33, 0.33, 1), (1, 0.66, 0.25, 1), (1, 0.88, 0.3, 1),
              (0.25, 0.78, 0.55, 1), (0.2, 0.75, 1, 1), (0.69, 0.49, 1, 1)]
    letters = []
    for ch, col in zip(TEXT["title"], colors):
        lab = CoreLabel(text=ch, font_size=dp(18), font_name=FONT_PX)
        lab.refresh()
        letters.append((lab.texture, col))
    x = wd.center_x - sum(t.width for t, _ in letters) / 2
    for tex, col in letters:
        Color(*col)
        Rectangle(texture=tex, size=tex.size, pos=(x, wd.center_y - tex.height / 2))
        x += tex.width


def fb_star_score(wd):
    star(wd.center_x, wd.center_y, min(wd.width, wd.height) / 2, GOLD)


def fb_divider(wd):
    Color(0.38, 0.2, 0.9, 1)
    Line(points=[wd.x, wd.center_y, wd.right, wd.center_y], width=1.6,
         dash_length=2, dash_offset=3)


def fb_scroll(wd):
    x, y, w, h = wd.x, wd.y, wd.width, wd.height
    Color(0.2, 0.4, 0.9, 1)
    Rectangle(pos=(x + .1 * w, y + .08 * h), size=(.8 * w, .12 * h))
    Color(0.85, 0.9, 1, 1)
    Rectangle(pos=(x + .2 * w, y + .2 * h), size=(.6 * w, .7 * h))
    Color(0.3, 0.45, 0.9, 1)
    for k in range(3):
        Rectangle(pos=(x + .3 * w, y + (.35 + k * .15) * h), size=(.4 * w, .05 * h))


def fb_def_panel(mode):
    """The definition panel. For correct / incorrect the title is drawn too, like the images."""
    fill, edge = STYLE["panel"][mode]

    def draw(wd):
        Color(*fill)
        RoundedRectangle(pos=wd.pos, size=wd.size, radius=[dp(10)])
        Color(*edge)
        Line(rounded_rectangle=(wd.x, wd.y, wd.width, wd.height, dp(10)), width=1.8)
        if mode == "question":
            fb_scroll(_sub(wd, 0.05, 0.2, 0.15, 0.6))
            fb_sparkle(_sub(wd, 0.92, 0.1, 0.05, 0.18))
        else:
            ok = mode == "correct"
            _text_at(TEXT["correct"] if ok else TEXT["incorrect"], FONT_PX, dp(14),
                     STYLE["correct_color"] if ok else STYLE["wrong_color"],
                     wd.center_x, wd.y + .8 * wd.height)
    return draw


def fb_grid_frame(wd):
    """Card frame with the label slot on top."""
    Color(0.05, 0.03, 0.18, 1)
    Rectangle(pos=wd.pos, size=wd.size)
    Color(0.4, 0.25, 0.9, 1)
    Line(rectangle=(wd.x, wd.y, wd.width, wd.height * .92), width=2)
    Color(0.28, 0.16, 0.7, 1)
    Line(rectangle=(wd.x + dp(5), wd.y + dp(5), wd.width - dp(10), wd.height * .92 - dp(10)),
         width=1)
    Color(0.1, 0.06, 0.3, 1)
    RoundedRectangle(pos=(wd.x + .28 * wd.width, wd.y + .875 * wd.height),
                     size=(.44 * wd.width, .085 * wd.height), radius=[dp(6)])
    Color(0.5, 0.35, 1, 1)
    Line(rounded_rectangle=(wd.x + .28 * wd.width, wd.y + .875 * wd.height,
                            .44 * wd.width, .085 * wd.height, dp(6)), width=1.8)


def fb_cell(mode):
    fill, edge, _ = STYLE["cell"][mode]

    def draw(wd):
        Color(*fill)
        RoundedRectangle(pos=wd.pos, size=wd.size, radius=[dp(10)])
        if mode != "normal":                                    # glow
            Color(edge[0], edge[1], edge[2], 0.35)
            Line(rounded_rectangle=(wd.x - dp(2), wd.y - dp(2), wd.width + dp(4),
                                    wd.height + dp(4), dp(12)), width=dp(2))
        Color(*edge)
        Line(rounded_rectangle=(wd.x, wd.y, wd.width, wd.height, dp(10)), width=1.6)
    return draw


def fb_cell_free(wd):
    Color(0.1, 0.06, 0.3, 1)
    RoundedRectangle(pos=wd.pos, size=wd.size, radius=[dp(10)])
    Color(0.55, 0.35, 0.95, 1)
    Line(rounded_rectangle=(wd.x, wd.y, wd.width, wd.height, dp(10)), width=1.8)
    star(wd.center_x, wd.center_y + wd.height * .15, min(wd.width, wd.height) * .22, GOLD)
    _text_at(TEXT["free"], FONT_PX, dp(13), AMBER, wd.center_x, wd.y + wd.height * .28)


def fb_streak(wd):
    """The streak label: a line, a sparkle, the pill, a sparkle, a line."""
    cy = wd.center_y
    Color(0.38, 0.2, 0.9, 1)
    Line(points=[wd.x, cy, wd.x + .18 * wd.width, cy], width=1.2)
    Line(points=[wd.x + .78 * wd.width, cy, wd.right, cy], width=1.2)
    Color(0.1, 0.06, 0.3, 1)
    RoundedRectangle(pos=(wd.x + .25 * wd.width, wd.y + .25 * wd.height),
                     size=(.47 * wd.width, .5 * wd.height), radius=[dp(8)])
    Color(0.5, 0.35, 1, 1)
    Line(rounded_rectangle=(wd.x + .25 * wd.width, wd.y + .25 * wd.height,
                            .47 * wd.width, .5 * wd.height, dp(8)), width=1.8)
    fb_sparkle(_sub(wd, 0.2, 0.35, 0.05, 0.3))
    fb_sparkle(_sub(wd, 0.74, 0.35, 0.05, 0.3))


def fb_flame(on):
    def draw(wd):
        x, y, w, h = wd.x, wd.y, wd.width, wd.height
        if on:
            Color(1, 0.5, 0.1, 1)
            Triangle(points=[x + .5 * w, y + .95 * h, x + .1 * w, y + .1 * h, x + .9 * w, y + .1 * h])
            Color(1, 0.85, 0.3, 1)
            Triangle(points=[x + .5 * w, y + .6 * h, x + .3 * w, y + .1 * h, x + .7 * w, y + .1 * h])
        else:
            Color(0.45, 0.42, 0.55, 1)
            Triangle(points=[x + .5 * w, y + .6 * h, x + .25 * w, y + .1 * h, x + .75 * w, y + .1 * h])
    return draw


# ----------------------------------------------------------------- widgets
class TapArea(ButtonBehavior, Widget):
    """An invisible bigger target for a small image."""


class Cell(ButtonBehavior, FloatLayout):
    """One term on the card. mode: normal, selected, correct or wrong."""

    KEYS = {"normal": "g_cell", "selected": "g_cell_selected",
            "correct": "g_cell_correct", "wrong": "g_cell_wrong"}

    def __init__(self, term, is_correct, on_tap, font_size, **kwargs):
        super().__init__(**kwargs)
        self.term, self.is_correct, self.on_tap = term, is_correct, on_tap
        self.mode = "normal"
        self.bg = Art("g_cell", fb_cell("normal"), size_hint=(1, 1),
                      pos_hint={"center_x": .5, "center_y": .5})
        self.add_widget(self.bg)
        self.label = Label(text=term, font_name=FONT, font_size=font_size,
                           color=STYLE["cell"]["normal"][2], halign="center",
                           valign="middle", size_hint=(.9, .9),
                           pos_hint={"center_x": .5, "center_y": .5})
        self.label.bind(size=lambda i, v: setattr(i, "text_size", v))
        self.add_widget(self.label)
        if not term:                                    # padding cell
            self.disabled = True
            self.opacity = 0.35

    def set_mode(self, mode):
        self.mode = mode
        key = self.KEYS[mode]
        self.bg.size_hint = scale_of(key)               # glow images are a bit larger
        self.bg.set_art(key, fb_cell(mode))
        self.label.color = STYLE["cell"][mode][2]

    def on_release(self):
        self.on_tap(self)


class FreeCell(FloatLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.add_widget(Art("g_cell_free", fb_cell_free, size_hint=scale_of("g_cell_free"),
                            pos_hint={"center_x": .5, "center_y": .5}))


class DefPanel(FloatLayout):
    """The panel above the card: the definition, then Correct! / Incorrect!. The images carry
    the scroll icon and the titles, this only lays the text over them."""

    def __init__(self, **kwargs):
        super().__init__(size_hint_y=None, height=dp(90), **kwargs)
        self.bg = Art("g_def_card", fb_def_panel("question"), **_fill())
        self.add_widget(self.bg)

        self.q_lbl = Label(font_name=FONT, font_size="11sp", color=WHITE, halign="center",
                           valign="middle", **_frac(L["question_text"]))
        self.q_lbl.bind(size=lambda i, v: setattr(i, "text_size", v))
        self.add_widget(self.q_lbl)

        self.r_answer = Label(font_name=FONT, font_size="11sp", halign="center",
                              valign="middle", **_frac(L["answer_text"]))
        self.r_answer.bind(size=lambda i, v: setattr(i, "text_size", v))
        self.add_widget(self.r_answer)
        self.r_def = Label(font_name=FONT, font_size="8sp", color=STYLE["detail_color"],
                           halign="center", valign="top", **_frac(L["detail_text"]))
        self.r_def.bind(size=lambda i, v: setattr(i, "text_size", v))
        self.add_widget(self.r_def)
        self.r_answer.opacity = self.r_def.opacity = 0

    def show_text(self, txt):
        self.bg.set_art("g_def_card", fb_def_panel("question"))
        self.q_lbl.opacity = 1
        self.r_answer.opacity = self.r_def.opacity = 0
        self.q_lbl.text = txt
        for limit, size in STYLE["def_sizes"]:
            if len(txt) <= limit:
                self.q_lbl.font_size = size
                break

    def show_result(self, ok, term, definition, reveal):
        self.bg.set_art("g_card_ok" if ok else "g_card_bad",
                        fb_def_panel("correct" if ok else "wrong"))
        self.q_lbl.opacity = 0
        self.r_answer.opacity = self.r_def.opacity = 1
        self.r_answer.color = STYLE["correct_color"] if ok else STYLE["wrong_color"]
        if ok:
            self.r_answer.text = term
        else:
            self.r_answer.text = (TEXT["answer"] % term) if reveal else ""
        self.r_def.text = definition


class StreakRow(FloatLayout):
    """The streak image with "Streak: n" and the flame laid over its pill."""

    def __init__(self, **kwargs):
        super().__init__(size_hint_y=None, height=dp(70), **kwargs)
        self.add_widget(Art("g_streak", fb_streak, **_fill()))
        inner = BoxLayout(spacing=dp(6), **_frac(L["streak_text"]))
        inner.add_widget(Widget())
        self.label = Label(font_name=FONT, font_size="12sp", color=WHITE, size_hint_x=None,
                           halign="center", valign="middle")
        self.label.bind(texture_size=lambda i, v: setattr(i, "width", v[0] + dp(2)))
        inner.add_widget(self.label)
        fh = dp(L["flame_height"])
        self.flame = Art("g_flame_off", fb_flame(False), size_hint=(None, None),
                         size=(fh * ratio("g_flame_off"), fh), pos_hint={"center_y": .5})
        inner.add_widget(self.flame)
        inner.add_widget(Widget())
        self.add_widget(inner)

    def set_streak(self, n):
        self.label.text = TEXT["streak"] % n
        if n > 0:
            self.flame.set_art("g_flame_on", fb_flame(True))
        else:
            self.flame.set_art("g_flame_off", fb_flame(False))


# ----------------------------------------------------------------- the screen
class BingoGame(Screen):
    """Term-matching Bingo game based on the completed review set."""

    settings = {}

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.review_set_id = None
        self.terms = []
        self.question_order = []
        self.question_index = 0
        self.score = 0
        self.streak = 0
        self.grid_n = 3
        self.shuffle_on = True
        self.free_on = True
        self.show_answer = True
        self.locked = False                 # an answer was confirmed, waiting for the next question
        self.selected = None                # the cell tapped once
        self.missed = []                    # (term, definition) of every wrong answer
        self.cells = []
        self.term = ""
        self.definition = ""
        self._next_event = None

        with self.canvas.before:
            Color(0.047, 0, 0.129, 1)
            self._bg = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._upd_bg, size=self._upd_bg)

        outer = BoxLayout(orientation="vertical")
        outer.add_widget(Widget(size_hint_y=None, height=dp(L["top_space"])))

        # header: back arrow (with a bigger tap area) and the logo
        header = FloatLayout(size_hint_y=None, height=dp(L["header_height"]))
        bh = dp(L["back_height"])
        header.add_widget(Art("g_back", fb_back, size_hint=(None, None),
                              size=(bh * ratio("g_back"), bh),
                              pos_hint={"x": 0.07, "center_y": .5}))
        tap = TapArea(size_hint=(None, None), size=(dp(56), dp(48)),
                      pos_hint={"x": 0.02, "center_y": .5})
        tap.bind(on_release=lambda *a: self.go_back())
        header.add_widget(tap)
        th = dp(L["title_height"])
        header.add_widget(Art("g_title", fb_title, size_hint=(None, None),
                              size=(th * ratio("g_title"), th),
                              pos_hint={"center_x": .5, "center_y": .5}))
        outer.add_widget(header)

        body = FloatLayout()
        outer.add_widget(body)
        self.add_widget(outer)
        body.add_widget(Art("g_frame", fb_frame, size_hint=L["frame_size"],
                            pos_hint={"center_x": .5, "center_y": .5}))

        # the content, inside the frame
        fw, fh = L["frame_size"]
        il, it, ir, ib = L["content_inset"]
        self.col = BoxLayout(orientation="vertical", spacing=dp(L["gap"]),
                             size_hint=(fw * (1 - il - ir), fh * (1 - it - ib)),
                             pos_hint={"x": (1 - fw) / 2 + fw * il,
                                       "top": 1 - (1 - fh) / 2 - fh * it})
        body.add_widget(self.col)
        col = self.col

        # score and question number
        stats = BoxLayout(size_hint_y=None, height=dp(L["stats_height"]), spacing=dp(8))
        sh = dp(L["star_height"])
        stats.add_widget(Art("g_star", fb_star_score, size_hint=(None, None),
                             size=(sh * ratio("g_star"), sh), pos_hint={"center_y": .5}))
        self.score_lbl = line_label("", "12sp")
        stats.add_widget(self.score_lbl)
        self.question_lbl = line_label("", "12sp", halign="right")
        stats.add_widget(self.question_lbl)
        col.add_widget(stats)
        col.add_widget(Art("g_divider", fb_divider, size_hint_y=None,
                           height=dp(L["divider_height"])))

        # definition / result panel
        self.panel = DefPanel()
        col.add_widget(self.panel)
        col.add_widget(Widget())                                   # flexible space

        # the card: frame with the "3 X 3 SET" label on it and the terms inside
        self.card_holder = FloatLayout(size_hint_y=None, height=dp(300))
        self.frame_box = FloatLayout(size_hint=(None, None),
                                     pos_hint={"center_x": .5, "center_y": .5})
        self.frame_box.add_widget(Art("g_grid_frame", fb_grid_frame, **_fill()))
        bw, bh2 = L["banner_size"]
        bx, by = L["banner_pos"]
        self.set_lbl = Label(font_name=FONT_PX, font_size="9sp", color=STYLE["banner_color"],
                             halign="center", valign="middle", size_hint=(bw, bh2),
                             pos_hint={"center_x": bx, "center_y": by})
        self.set_lbl.bind(size=lambda i, v: setattr(i, "text_size", v))
        self.frame_box.add_widget(self.set_lbl)
        gl, gt, gr, gb = L["grid_inset"]
        self.inner = FloatLayout(size_hint=(1 - gl - gr, 1 - gt - gb),
                                 pos_hint={"x": gl, "y": gb})
        self.grid = GridLayout(cols=3, spacing=dp(L["grid_gap"]), size_hint=(None, None),
                               pos_hint={"center_x": .5, "center_y": .5})
        self.inner.add_widget(self.grid)
        self.frame_box.add_widget(self.inner)
        self.card_holder.add_widget(self.frame_box)
        col.add_widget(self.card_holder)
        col.add_widget(Widget())                                   # flexible space

        self.streak_row = StreakRow()
        col.add_widget(self.streak_row)

        col.bind(size=self._layout)
        self.inner.bind(size=self._fit_grid)
        self._update_stats()

    def _upd_bg(self, *args):
        self._bg.pos, self._bg.size = self.pos, self.size

    # ---------------------------------------------------------------- layout
    def _layout(self, *args):
        """Heights that follow the images' proportions. The card frame is as big as fits."""
        w, h = self.col.width, self.col.height
        if w <= 1 or h <= 1:
            return
        gap = dp(L["gap"])
        panel_h = w / ratio("g_def_card")
        streak_h = w / ratio("g_streak")
        fixed = dp(L["stats_height"]) + dp(L["divider_height"]) + panel_h + streak_h + 6 * gap
        frame_ratio = ratio("g_grid_frame")
        card_h = max(min(w / frame_ratio, h - fixed), dp(160))
        self.panel.height = panel_h
        self.streak_row.height = streak_h
        self.card_holder.height = card_h
        self.frame_box.size = (card_h * frame_ratio, card_h)

    def _fit_grid(self, *args):
        """Cells keep the shape of the cell image and are centred in the card frame."""
        iw, ih = self.inner.size
        if iw <= 1 or ih <= 1:
            return
        n, gap, cr = self.grid_n, dp(L["grid_gap"]), ratio("g_cell")
        cw = (iw - (n - 1) * gap) / n
        ch = cw / cr
        if n * ch + (n - 1) * gap > ih:
            ch = (ih - (n - 1) * gap) / n
            cw = ch * cr
        self.grid.size = (n * cw + (n - 1) * gap, n * ch + (n - 1) * gap)

    # ---------------------------------------------------------------- starting
    def start_game(self, review_set_id, name="", size=3, shuffle=True,
                   free_center=True, show_answer=True):
        self._cancel_next()
        app = App.get_running_app()
        self.settings = dict(name=name, size=size, shuffle=shuffle,
                             free_center=free_center, show_answer=show_answer)
        self.grid_n = size
        self.shuffle_on = shuffle
        self.free_on = bool(free_center) and size % 2 == 1
        self.show_answer = show_answer
        self.review_set_id = review_set_id
        self.terms = [(term, definition)
                      for _, term, definition in app.db.get_terms(review_set_id)
                      if term.strip() and definition.strip()]
        self.question_order = list(range(len(self.terms)))
        if shuffle:
            random.shuffle(self.question_order)
        self.question_index = 0
        self.score = 0
        self.streak = 0
        self.missed = []
        self.set_lbl.text = TEXT["set_banner"] % (size, size)
        if not self.terms:
            self.grid.clear_widgets()
            self.cells = []
            self.panel.show_text(TEXT["no_terms"])
            self._update_stats()
            return
        self._show_question()

    def go_back(self, *args):
        self._cancel_next()
        self.manager.transition.direction = "right"
        self.manager.current = "reviewsets"

    def _cancel_next(self):
        if self._next_event is not None:
            self._next_event.cancel()
            self._next_event = None

    # ---------------------------------------------------------------- one question
    def _update_stats(self):
        total = len(self.terms)
        self.score_lbl.text = TEXT["score"] % (self.score, total)
        self.question_lbl.text = TEXT["question"] % (min(self.question_index + 1, total), total)
        self.streak_row.set_streak(self.streak)

    def _show_question(self):
        if self.question_index >= len(self.question_order):
            self._finish()
            return
        self.locked = False
        self.selected = None
        correct_index = self.question_order[self.question_index]
        self.term, self.definition = self.terms[correct_index]
        self.panel.show_text(self.definition)
        self._update_stats()

        self.grid.cols = self.grid_n
        self.grid.clear_widgets()
        self.cells = []
        font = STYLE["cell_sizes"].get(self.grid_n, "10sp")
        for item in build_card(self.terms, correct_index, self.grid_n,
                               self.shuffle_on, self.free_on):
            if item is None:
                self.grid.add_widget(FreeCell())
                continue
            cell = Cell(item[0], item[1], self.on_cell, font)
            self.cells.append(cell)
            self.grid.add_widget(cell)
        self._fit_grid()

    def _finish(self):
        """Last question answered: show the Game Complete page."""
        self.locked = True
        result = self.manager.get_screen("gameresult")
        result.show(self.score, len(self.terms), self.missed)
        self.manager.transition.direction = "left"
        self.manager.current = "gameresult"

    # ---------------------------------------------------------------- tapping
    def on_cell(self, cell):
        """First tap selects a term, a second tap on the same term confirms it."""
        if self.locked:
            return
        if self.selected is cell:
            self._confirm(cell)
            return
        if self.selected is not None:
            self.selected.set_mode("normal")
        self.selected = cell
        cell.set_mode("selected")

    def _confirm(self, cell):
        self.locked = True
        if cell.is_correct:
            self.score += 1
            self.streak += 1
            cell.set_mode("correct")
        else:
            self.streak = 0
            self.missed.append((self.term, self.definition))
            cell.set_mode("wrong")
            if STYLE["highlight_correct_cell"] and self.show_answer:
                for other in self.cells:
                    if other.is_correct:
                        other.set_mode("correct")
        self.panel.show_result(cell.is_correct, self.term, self.definition,
                               reveal=self.show_answer)
        self._update_stats()
        self._next_event = Clock.schedule_once(self._next_question, STYLE["result_seconds"])

    def _next_question(self, dt):
        self._next_event = None
        self.question_index += 1
        self._show_question()
