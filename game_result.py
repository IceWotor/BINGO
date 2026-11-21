"""Game Complete page: score, correct / incorrect, the terms you missed, PLAY AGAIN, BACK TO HOME.

Shown by BingoGame when the last question is answered.

The images are placed at their design size (the container image is the 383 px wide page they
were drawn for) and the transparent padding around each one is trimmed off, so they stack the
way they do in the mockup. Everything scales together to fit the phone. Text that belongs on
an image (the score number, the correct / incorrect counts, the missed term) is laid over it
at the positions set in LAYOUT.

EASY TO CHANGE
  * ASSETS   the image files. Keep the names, or edit them here. A missing image is drawn in
             code instead, so the page works without it.
  * TEXT     the words on the page.
  * STYLE    colours, font sizes, how much of a missed definition is shown.
  * LAYOUT   the space between the pieces and where text sits on each image (fractions of
             that image).
  Shared helpers (Art, register_assets...) are in ui_kit.py.
"""
from types import SimpleNamespace

from PIL import Image

from kivy.core.text import Label as CoreLabel
from kivy.graphics import Color, Line, Rectangle, RoundedRectangle, Triangle
from kivy.metrics import dp
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen
from kivy.uix.widget import Widget

from bingo_game import fb_title
from ui_kit import (AMBER, FONT, FONT_PX, Art, fb_frame, find_asset,
                    register_assets, star, texture)

# ----------------------------------------------------------------- assets
FOLDER = "./assets/pageAssets/gameresult/"
ASSETS = {
    "r_frame":      [FOLDER + "container.png"],        # the page: frame and night sky
    "r_complete":   [FOLDER + "gameComplete.png"],     # trophy and GAME COMPLETE!
    "r_logo":       [FOLDER + "bingoLogo.png"],
    "r_score":      [FOLDER + "score.png"],            # SCORE: pill (the number goes on it)
    "r_correct":    [FOLDER + "correct.png"],          # CORRECT box (the number goes on it)
    "r_incorrect":  [FOLDER + "incorrect.png"],        # INCORRECT box
    "r_div_mid":    [FOLDER + "middleDivider.png"],    # line with the star
    "r_missed":     [FOLDER + "missedTerms.png"],      # MISSED TERMS card
    "r_div_bottom": [FOLDER + "bottomDivider.png"],
    "r_again":      [FOLDER + "playAgain.png"],
    "r_home":       [FOLDER + "backToHome.png"],
    "r_arrow_left":  [FOLDER + "leftMissedTerm.png"],  # missed terms: previous
    "r_arrow_right": [FOLDER + "rightMissedTerm.png"], # missed terms: next
}
register_assets(ASSETS)

# size in pixels of each image once its transparent padding is trimmed (used when a file is
# missing, so the page keeps the same layout)
NATIVE = {
    "r_frame": (383, 771), "r_complete": (253, 98), "r_logo": (297, 111), "r_score": (310, 40),
    "r_correct": (135, 72), "r_incorrect": (135, 72), "r_div_mid": (308, 16),
    "r_missed": (304, 139), "r_div_bottom": (307, 2), "r_again": (218, 56), "r_home": (213, 45),
}

# ----------------------------------------------------------------- words
TEXT = dict(
    score_value="%d/%d",
    no_missed_term="No missed terms!",
    no_missed_def="Every answer was right.",
    # words drawn only when the matching image is missing
    complete="GAME COMPLETE!", score="SCORE:", correct="CORRECT", incorrect="INCORRECT",
    missed="MISSED TERMS", again="PLAY AGAIN", home="BACK TO HOME",
)

# ----------------------------------------------------------------- look
STYLE = dict(
    value_color=AMBER,
    term_color=(1, 0.75, 0.2, 1),
    detail_color=(0.65, 0.5, 1, 1),
    arrow_color=(0.38, 0.28, 0.7, 1),
    arrow_off=0.3,                  # opacity of an arrow that can't be used
    term_max_chars=24,
    def_max_chars=80,               # a longer definition is cut and ends with ...
    trim_alpha=20,                  # pixels fainter than this (0-255) count as empty when trimming
)

# distances are in design pixels (the page was drawn 383 px wide); the rest are fractions
LAYOUT = dict(
    top_space=40,
    frame_size=(0.94, 1),                         # the page frame: fraction of the page
    content_inset=(0.05, 0.04, 0.05, 0.09),       # left, top, right, bottom of the frame
    design_width=383,
    # space between: complete-logo, logo-score, score-stats, stats-divider, divider-missed,
    #                missed-divider, divider-play again, play again-back
    gaps=(8, 12, 14, 18, 14, 18, 14, 10),
    stat_gap=20,                                  # between CORRECT and INCORRECT
    score_value=(0.60, 0.05, 0.20, 0.90),         # x, y, w, h on the score image
    stat_value=(0.10, 0.06, 0.80, 0.46),          # on the correct / incorrect images
    missed_term=(0.415, 0.42, 0.49, 0.26),        # on the missed terms card (keep clear of the arrows)
    missed_def=(0.415, 0.08, 0.49, 0.34),
    arrow_x=(0.065, 0.935),                       # centre of the left / right arrow on the card
    arrow_y=0.43,
    arrow_size=(15, 17),                          # design pixels, for the drawn stand-in
    arrow_tap=(26, 30),                           # half the size of the area you can tap, in dp
)
L = LAYOUT


# ----------------------------------------------------------------- trimming
_trim = {}


def trimmed(path):
    """-> (texture, (x1, y1, x2, y2) box of the visible part, (width, height) of the whole
    image), all in pixels, or (None, None, None) if the file can't be read."""
    if path in _trim:
        return _trim[path]
    res = (None, None, None)
    try:
        im = Image.open(path).convert("RGBA")
        alpha = im.getchannel("A").point(lambda v: 255 if v > STYLE["trim_alpha"] else 0)
        bbox = alpha.getbbox() or (0, 0, im.width, im.height)
        tex = texture(path)
        if tex is not None:
            res = (tex, bbox, (im.width, im.height))
    except Exception as e:
        print("Result page: could not read %s (%s)" % (path, e))
    _trim[path] = res
    return res


def native(key):
    """Size in design pixels of the visible part of an image."""
    src = find_asset(key)
    box = trimmed(src)[1] if src else None
    w, h = (box[2] - box[0], box[3] - box[1]) if box else NATIVE[key]
    return w, max(h, 2)                       # a one pixel line still needs a little room


class TrimArt(Art):
    """Art whose size is the visible part of its image. The faint transparent padding (glow)
    is still drawn, around the edges, so it blends in without taking any room in the layout."""

    def redraw(self, *args):
        self.canvas.clear()
        src = find_asset(self.key)
        tex, box, full = trimmed(src) if src else (None, None, None)
        with self.canvas:
            if tex is not None:
                x1, y1, x2, y2 = box
                sx, sy = self.width / float(x2 - x1), self.height / float(y2 - y1)
                Color(1, 1, 1, 1)
                Rectangle(texture=tex,
                          pos=(self.x - x1 * sx, self.y - (full[1] - y2) * sy),
                          size=(full[0] * sx, full[1] * sy))
            elif self.fallback:
                self.fallback(self)


class TrimButton(ButtonBehavior, TrimArt):
    def __init__(self, key, fallback=None, **kwargs):
        super().__init__(**kwargs)
        self.key, self.fallback = key, fallback
        self.redraw()


# ----------------------------------------------------------------- drawn stand-ins
def _text_at(txt, font, size, color, cx, cy):
    lab = CoreLabel(text=txt, font_size=size, font_name=font)
    lab.refresh()
    t = lab.texture
    Color(*color)
    Rectangle(texture=t, size=t.size, pos=(cx - t.width / 2, cy - t.height / 2))


def _pill(wd, fill=(0.1, 0.06, 0.3, 1), edge=(0.5, 0.35, 1, 1), radius=6):
    Color(*fill)
    RoundedRectangle(pos=wd.pos, size=wd.size, radius=[dp(radius)])
    Color(*edge)
    Line(rounded_rectangle=(wd.x, wd.y, wd.width, wd.height, dp(radius)), width=1.8)


def fb_complete(wd):
    banner_h = wd.height * .4
    _pill(SimpleNamespace(pos=wd.pos, size=(wd.width, banner_h), x=wd.x, y=wd.y,
                          width=wd.width, height=banner_h))
    star(wd.center_x, wd.y + wd.height * .72, wd.height * .2, (1, 0.8, 0.2, 1))
    _text_at(TEXT["complete"], FONT_PX, dp(12), (0.7, 0.62, 1, 1),
             wd.center_x, wd.y + banner_h / 2)


def fb_score(wd):
    _pill(wd)
    star(wd.x + wd.width * .2, wd.center_y, wd.height * .3, (1, 0.8, 0.2, 1))
    _text_at(TEXT["score"], FONT_PX, dp(11), (0.7, 0.62, 1, 1),
             wd.x + wd.width * .4, wd.center_y)


def fb_stat(ok):
    edge = (0.3, 0.9, 0.55, 1) if ok else (1, 0.35, 0.45, 1)

    def draw(wd):
        _pill(wd, fill=(0.07, 0.04, 0.25, 1), edge=(0.38, 0.22, 0.85, 1), radius=8)
        Color(*edge)
        Line(circle=(wd.x + wd.width * .17, wd.y + wd.height * .8, wd.height * .11), width=1.6)
        _text_at(TEXT["correct"] if ok else TEXT["incorrect"], FONT_PX, dp(8),
                 (0.7, 0.62, 1, 1), wd.x + wd.width * .58, wd.y + wd.height * .8)
    return draw


def fb_div_mid(wd):
    Color(0.38, 0.2, 0.9, 1)
    Line(points=[wd.x, wd.center_y, wd.right, wd.center_y], width=1.2)
    star(wd.center_x, wd.center_y, wd.height * .45, (0.3, 0.75, 1, 1))


def fb_div_bottom(wd):
    Color(0.38, 0.2, 0.9, 1)
    Line(points=[wd.x, wd.center_y, wd.right, wd.center_y], width=1.2)


def fb_missed(wd):
    top = wd.y + wd.height * .86
    Color(0.05, 0.03, 0.18, 1)
    Rectangle(pos=wd.pos, size=(wd.width, wd.height * .86))
    Color(0.35, 0.2, 0.9, 1)
    Line(rectangle=(wd.x, wd.y, wd.width, wd.height * .86), width=1.8)
    Color(0.1, 0.06, 0.3, 1)
    RoundedRectangle(pos=(wd.x + wd.width * .3, top - wd.height * .1),
                     size=(wd.width * .4, wd.height * .2), radius=[dp(6)])
    _text_at(TEXT["missed"], FONT_PX, dp(8), (0.7, 0.62, 1, 1), wd.center_x, top)
    Color(0.3, 0.35, 0.9, 1)
    Rectangle(pos=(wd.x + wd.width * .2, wd.y + wd.height * .25),
              size=(wd.width * .11, wd.height * .3))
    Color(0.25, 0.15, 0.6, 1)
    Line(points=[wd.x + wd.width * .38, wd.y + wd.height * .2,
                 wd.x + wd.width * .38, wd.y + wd.height * .6], width=1)


def fb_again(wd):
    _pill(wd, fill=(0.95, 0.25, 0.5, 1), edge=(1, 0.6, 0.75, 1), radius=8)
    _text_at(TEXT["again"], FONT_PX, dp(12), (1, 1, 1, 1), wd.center_x + wd.width * .06,
             wd.center_y)


def fb_home(wd):
    _pill(wd, fill=(0.17, 0.07, 0.5, 1), edge=(0.5, 0.35, 1, 1), radius=8)
    _text_at(TEXT["home"], FONT_PX, dp(11), (0.6, 0.5, 0.95, 1), wd.center_x, wd.center_y)


# ----------------------------------------------------------------- widgets
def _frac(spec):
    """(x, y, w, h) fractions -> Kivy keyword arguments for a FloatLayout child."""
    x, y, w, h = spec
    return dict(size_hint=(w, h), pos_hint={"x": x, "y": y})


def _fill():
    """Keyword arguments that make a FloatLayout child cover its parent (a FloatLayout only
    moves children that have a pos_hint)."""
    return dict(size_hint=(1, 1), pos_hint={"x": 0, "y": 0})


def _value_label(spec, size, color, font=FONT_PX):
    lab = Label(font_name=font, font_size=size, color=color, halign="center",
                valign="middle", **_frac(spec))
    lab.bind(size=lambda i, v: setattr(i, "text_size", v))
    return lab


class Stat(FloatLayout):
    """CORRECT or INCORRECT box with the number laid over it."""

    def __init__(self, key, fallback, **kwargs):
        super().__init__(size_hint=(None, None), **kwargs)
        self.add_widget(TrimArt(key, fallback, **_fill()))
        self.value = _value_label(L["stat_value"], "16sp", STYLE["value_color"])
        self.add_widget(self.value)


class MissedCard(FloatLayout):
    """The missed terms card: one term at a time. The arrows are drawn straight onto the card
    and tapping near one moves to the previous / next term."""

    def __init__(self, **kwargs):
        super().__init__(size_hint=(None, None), **kwargs)
        self.missed, self.index = [], 0
        self.can = (False, False)                  # may we go to the previous / next term?
        self.add_widget(TrimArt("r_missed", fb_missed, **_fill()))

        self.term = Label(font_name=FONT, font_size="14sp", color=STYLE["term_color"],
                          halign="left", valign="bottom", **_frac(L["missed_term"]))
        self.term.bind(size=lambda i, v: setattr(i, "text_size", v))
        self.add_widget(self.term)
        self.detail = Label(font_name=FONT, font_size="9sp", color=STYLE["detail_color"],
                            halign="left", valign="top", **_frac(L["missed_def"]))
        self.detail.bind(size=lambda i, v: setattr(i, "text_size", v))
        self.add_widget(self.detail)
        self.bind(pos=self._paint, size=self._paint)

    def set_terms(self, missed):
        self.missed, self.index = list(missed), 0
        self._refresh()

    def step(self, delta):
        i = self.index + delta
        if 0 <= i < len(self.missed):
            self.index = i
            self._refresh()

    def _refresh(self):
        if not self.missed:
            self.term.text = TEXT["no_missed_term"]
            self.detail.text = TEXT["no_missed_def"]
        else:
            term, definition = self.missed[self.index]
            mt, md = STYLE["term_max_chars"], STYLE["def_max_chars"]
            self.term.text = term if len(term) <= mt else term[:mt - 3] + "..."
            self.detail.text = definition if len(definition) <= md else definition[:md - 3] + "..."
        self.can = (self.index > 0, self.index < len(self.missed) - 1)
        self._paint()

    # ---- the arrows
    def _scale(self):
        return self.width / float(native("r_missed")[0])

    def _centers(self):
        y = self.y + L["arrow_y"] * self.height
        return [(self.x + fx * self.width, y) for fx in L["arrow_x"]]

    def _paint(self, *args):
        """Draw the arrows on top of the card. An arrow that can't be used is faded."""
        self.canvas.after.clear()
        s = self._scale()
        with self.canvas.after:
            for side, (cx, cy), ok in zip(("left", "right"), self._centers(), self.can):
                alpha = 1 if ok else STYLE["arrow_off"]
                src = find_asset("r_arrow_" + side)
                tex = texture(src) if src else None
                if tex is not None:
                    w, h = tex.width * s, tex.height * s
                    Color(1, 1, 1, alpha)
                    Rectangle(texture=tex, pos=(cx - w / 2, cy - h / 2), size=(w, h))
                else:                                           # plain triangle
                    w, h = L["arrow_size"][0] * s, L["arrow_size"][1] * s
                    r, g, b, _ = STYLE["arrow_color"]
                    Color(r, g, b, alpha)
                    if side == "left":
                        pts = [cx + w / 2, cy - h / 2, cx - w / 2, cy, cx + w / 2, cy + h / 2]
                    else:
                        pts = [cx - w / 2, cy - h / 2, cx + w / 2, cy, cx - w / 2, cy + h / 2]
                    Triangle(points=pts)

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            hw, hh = dp(L["arrow_tap"][0]), dp(L["arrow_tap"][1])
            for delta, (cx, cy), ok in zip((-1, 1), self._centers(), self.can):
                if ok and abs(touch.x - cx) <= hw and abs(touch.y - cy) <= hh:
                    self.step(delta)
                    return True
        return super().on_touch_down(touch)


# ----------------------------------------------------------------- the screen
class GameResult(Screen):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        with self.canvas.before:
            Color(0.047, 0, 0.129, 1)
            self._bg = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._upd_bg, size=self._upd_bg)

        outer = BoxLayout(orientation="vertical")
        outer.add_widget(Widget(size_hint_y=None, height=dp(L["top_space"])))
        body = FloatLayout()
        outer.add_widget(body)
        self.add_widget(outer)
        body.add_widget(Art("r_frame", fb_frame, size_hint=L["frame_size"],
                            pos_hint={"center_x": .5, "center_y": .5}))

        fw, fh = L["frame_size"]
        il, it, ir, ib = L["content_inset"]
        self.inset_w = 1 - il - ir
        self.col = BoxLayout(orientation="vertical",
                             size_hint=(fw * self.inset_w, fh * (1 - it - ib)),
                             pos_hint={"x": (1 - fw) / 2 + fw * il,
                                       "top": 1 - (1 - fh) / 2 - fh * it})
        body.add_widget(self.col)

        def item(widget):
            widget.size_hint = (None, None)
            widget.pos_hint = {"center_x": .5}
            self.col.add_widget(widget)
            return widget

        def gap():
            g = Widget(size_hint_y=None, height=dp(8))
            self.col.add_widget(g)
            return g

        self.col.add_widget(Widget())                                  # flexible space
        self.complete = item(TrimArt("r_complete", fb_complete))
        g1 = gap()
        self.logo = item(TrimArt("r_logo", fb_title))
        g2 = gap()
        self.score_box = item(FloatLayout())
        self.score_box.add_widget(TrimArt("r_score", fb_score, **_fill()))
        self.score_value = _value_label(L["score_value"], "11sp", STYLE["value_color"])
        self.score_box.add_widget(self.score_value)
        g3 = gap()
        self.stats = item(BoxLayout())
        self.correct = Stat("r_correct", fb_stat(True))
        self.incorrect = Stat("r_incorrect", fb_stat(False))
        self.stats.add_widget(self.correct)
        self.stats.add_widget(self.incorrect)
        g4 = gap()
        self.div_mid = item(TrimArt("r_div_mid", fb_div_mid))
        g5 = gap()
        self.missed = item(MissedCard())
        g6 = gap()
        self.div_bottom = item(TrimArt("r_div_bottom", fb_div_bottom))
        g7 = gap()
        self.again = item(TrimButton("r_again", fb_again))
        self.again.bind(on_release=lambda *a: self.play_again())
        g8 = gap()
        self.home = item(TrimButton("r_home", fb_home))
        self.home.bind(on_release=lambda *a: self.go_home())
        self.col.add_widget(Widget())                                  # flexible space

        self.gap_widgets = [g1, g2, g3, g4, g5, g6, g7, g8]
        self.col.bind(size=self._layout)

    def _upd_bg(self, *args):
        self._bg.pos, self._bg.size = self.pos, self.size

    # ---------------------------------------------------------------- layout
    def _layout(self, *args):
        """Everything is drawn at design size times one factor, so the pieces keep their
        proportions. The factor shrinks if the page would not fit."""
        w, h = self.col.width, self.col.height
        if w <= 1 or h <= 1:
            return
        sizes = {k: native(k) for k in NATIVE}
        stat_w = sizes["r_correct"][0] + L["stat_gap"] + sizes["r_incorrect"][0]
        stat_h = max(sizes["r_correct"][1], sizes["r_incorrect"][1])
        heights = [sizes["r_complete"][1], sizes["r_logo"][1], sizes["r_score"][1], stat_h,
                   sizes["r_div_mid"][1], sizes["r_missed"][1], sizes["r_div_bottom"][1],
                   sizes["r_again"][1], sizes["r_home"][1]]
        total = sum(heights) + sum(L["gaps"])
        widest = max([sizes[k][0] for k in sizes if k != "r_frame"] + [stat_w])
        frame_w = w / self.inset_w
        unit = min(frame_w / L["design_width"], h / float(total), w / float(widest))

        def put(widget, key):
            cw, ch = sizes[key]
            widget.size = (cw * unit, ch * unit)

        put(self.complete, "r_complete")
        put(self.logo, "r_logo")
        put(self.score_box, "r_score")
        put(self.div_mid, "r_div_mid")
        put(self.missed, "r_missed")
        put(self.div_bottom, "r_div_bottom")
        put(self.again, "r_again")
        put(self.home, "r_home")
        put(self.correct, "r_correct")
        put(self.incorrect, "r_incorrect")
        self.stats.spacing = L["stat_gap"] * unit
        self.stats.size = (stat_w * unit, stat_h * unit)
        for g, gap_px in zip(self.gap_widgets, L["gaps"]):
            g.height = gap_px * unit

    # ---------------------------------------------------------------- showing
    def show(self, correct, total, missed):
        """correct and total are counts, missed is a list of (term, definition)."""
        self.score_value.text = TEXT["score_value"] % (correct, total)
        self.correct.value.text = str(correct)
        self.incorrect.value.text = str(total - correct)
        self.missed.set_terms(missed)

    def play_again(self):
        game = self.manager.get_screen("bingogame")
        game.start_game(game.review_set_id, **game.settings)
        self.manager.transition.direction = "right"
        self.manager.current = "bingogame"

    def go_home(self):
        self.manager.transition.direction = "right"
        self.manager.current = "home"
