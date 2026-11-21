"""Extracted Text page: the scan result, one collapsed row per term. Tap a row to open it.

Shows the source file name at the top, a row per term/definition pair (damaged words in
pills), a legend, CONTINUE, and the step bar. CONTINUE opens the Extracted Content page.

EASY TO CHANGE
  * ASSETS      every image on this page. Drop a PNG with the listed name into
                assets/pageAssets/extractedtext/ and it is used; with no file a plain
                drawing is shown. (The step bar images are listed in ui_kit.py.)
  * TEXT        the words on the page.
  * COLORS      pill and legend colours. SEVERE_AT (in reconstruction/entry_view.py) is the
                damage score from which a pill turns red.
  * COLLAPSED_LINES  how many lines of the definition show before the row is opened.
"""
from kivy.core.text import Label as CoreLabel
from kivy.graphics import Color, Line, Rectangle, RoundedRectangle
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.screenmanager import Screen
from kivy.uix.widget import Widget

from reconstruction import entry_view as view
from ui_kit import (AMBER, CYAN, DIM, FONT, Art, ArtButton, StepBar, add_border, fb_chevron, fb_continue, fb_file, fb_frame, fb_sparkle,
                    fb_swatch, line_label, notice, register_assets, text)

# ----------------------------------------------------------------- settings
FOLDER = "./assets/pageAssets/extractedtext/"
ASSETS = {
    "et_frame":      [FOLDER + "frame.png",
                      "./assets/pageAssets/extractedcontent/setContainer.png"],
    "et_continue":   [FOLDER + "continue.png",
                      "./assets/pageAssets/manual/continueButton.png"],
    "et_file":       [FOLDER + "file_icon.png"],        # icon in the source bar
    "et_sparkle":    [FOLDER + "sparkle.png"],          # icon next to "Extracted Text"
    "et_chev_right": [FOLDER + "chevron_right.png"],    # row closed
    "et_chev_down":  [FOLDER + "chevron_down.png"],     # row open
    "et_swatch_term": [FOLDER + "swatch_term.png"],     # legend squares
    "et_swatch_def": [FOLDER + "swatch_def.png"],
}
register_assets(ASSETS)

TEXT = dict(
    source="Source: ",
    heading="Extracted Text",
    legend_term="Masked Terms",
    legend_def="Masked Definitions",
    no_term="(no term found)",
    no_definition="(no definition found)",
    empty="No terms could be extracted from this photo.",
)

# fill, edge
TERM_COLORS = ((0.72, 0.45, 0.1, 0.55), (1, 0.75, 0.2, 1))
MASK_COLORS = ((0.45, 0.3, 0.95, 0.40), (0.6, 0.45, 1, 1))
SEVERE_COLORS = ((0.9, 0.1, 0.25, 0.55), (1, 0.3, 0.4, 1))

COLLAPSED_LINES = 2
DEF_SIZE = 11                  # definition font size in sp
DEF_COLOR = (0.7, 0.62, 0.95, 1)
PILL_TEXT_HEX = "ffffff"
MAX_TERM_CHARS = 34

CONTINUE_RATIO = 70 / 344      # button height / width of the continue image


def _measurer(font, size_px):
    core = CoreLabel(font_name=font, font_size=size_px)
    cache = {}

    def measure(txt):
        w = cache.get(txt)
        if w is None:
            w = core.get_extents(txt)[0]
            cache[txt] = w
        return w

    return measure


# ----------------------------------------------------------------- row
class TermPill(Label):
    """The term, in a pill when the term itself was flagged."""

    def __init__(self, term, masked, **kwargs):
        shown = term if len(term) <= MAX_TERM_CHARS else term[:MAX_TERM_CHARS - 3] + "..."
        super().__init__(text=shown or TEXT["no_term"], font_name=FONT, font_size="16sp",
                         color=AMBER if term else DIM, size_hint=(None, None),
                         pos_hint={"center_y": .5}, **kwargs)
        self.masked = masked
        self.bind(texture_size=self._fit, pos=self._paint, size=self._paint)

    def _fit(self, *args):
        self.size = (self.texture_size[0] + dp(16), max(dp(28), self.texture_size[1] + dp(8)))

    def _paint(self, *args):
        self.canvas.before.clear()
        if not self.masked:
            return
        fill, edge = TERM_COLORS
        with self.canvas.before:
            Color(*fill)
            RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(6)])
            Color(*edge)
            Line(rounded_rectangle=(self.x, self.y, self.width, self.height, dp(6)), width=1.2)


class ExtractedRow(BoxLayout):
    def __init__(self, entry, det, **kwargs):
        super().__init__(orientation="vertical", size_hint_y=None,
                         padding=(dp(12), dp(10)), spacing=dp(6), **kwargs)
        self.bind(minimum_height=self.setter("height"))
        add_border(self, radius=dp(10))
        self.expanded = False
        self.items = view.definition_items(entry)
        self.zones = {}
        self.measure = _measurer(FONT, sp(DEF_SIZE))

        head = BoxLayout(size_hint_y=None, height=dp(32), spacing=dp(6))
        head.add_widget(TermPill(entry.term, view.term_masked(entry, det)))
        head.add_widget(Widget())
        self.chev = Art("et_chev_right", fb_chevron("right"), size_hint=(None, None),
                        size=(dp(18), dp(18)), pos_hint={"center_y": .5})
        head.add_widget(self.chev)
        self.add_widget(head)

        self.def_lbl = Label(markup=True, font_name=FONT, font_size="%dsp" % DEF_SIZE,
                             color=DEF_COLOR, halign="left", valign="top",
                             size_hint_y=None, height=dp(20))
        self.def_lbl.bind(width=self._on_width, pos=self._paint)
        self.add_widget(self.def_lbl)

    # ---- opening and closing
    def toggle(self):
        self.expanded = not self.expanded
        if self.expanded:
            self.chev.set_art("et_chev_down", fb_chevron("down"))
        else:
            self.chev.set_art("et_chev_right", fb_chevron("right"))
        self._relayout()

    def on_touch_up(self, touch):
        handled = super().on_touch_up(touch)
        if self.collide_point(*touch.pos) and self.collide_point(touch.ox, touch.oy):
            moved = ((touch.x - touch.ox) ** 2 + (touch.y - touch.oy) ** 2) ** 0.5
            if moved < dp(10):
                self.toggle()
                return True
        return handled

    # ---- definition text
    def _on_width(self, lbl, width):
        lbl.text_size = (width, None)
        self._relayout()

    def _relayout(self):
        lbl = self.def_lbl
        if lbl.width <= 1:
            return
        if not self.items:
            lbl.text = "[color=9a8fb5]%s[/color]" % TEXT["no_definition"]
            self.zones = {}
        else:
            if self.expanded:
                shown, cut = self.items, False
            else:
                space = self.measure("a a") - 2 * self.measure("a")
                shown, cut = view.fit_items(self.items, lbl.width, self.measure, space, dp(5),
                                            COLLAPSED_LINES, self.measure("..."))
            lbl.text, self.zones = view.markup(shown, cut, PILL_TEXT_HEX)
        lbl.texture_update()
        lbl.height = lbl.texture_size[1] + dp(4)
        self._paint()

    def _paint(self, *args):
        """Pill behind every flagged word (the zones are [ref] tags in the markup)."""
        lbl = self.def_lbl
        lbl.canvas.before.clear()
        left = lbl.center_x - lbl.texture_size[0] / 2.0
        top = lbl.center_y + lbl.texture_size[1] / 2.0
        with lbl.canvas.before:
            for name, boxes in lbl.refs.items():
                kind = self.zones.get(name)
                if kind is None:
                    continue
                fill, edge = SEVERE_COLORS if kind == "severe" else MASK_COLORS
                for (x1, y1, x2, y2) in boxes:
                    rx, ry = left + x1 - dp(2), top - y2 - dp(1)
                    rw, rh = x2 - x1 + dp(4), y2 - y1 + dp(2)
                    Color(*fill)
                    RoundedRectangle(pos=(rx, ry), size=(rw, rh), radius=[dp(4)])
                    Color(*edge)
                    Line(rounded_rectangle=(rx, ry, rw, rh, dp(4)), width=1)


# ----------------------------------------------------------------- screen
class ExtractedText(Screen):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.entries = []
        self.filename = "photo"

        with self.canvas.before:
            Color(0.047, 0, 0.129, 1)
            self._bg = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._upd_bg, size=self._upd_bg)

        outer = BoxLayout(orientation="vertical")
        outer.add_widget(Widget(size_hint_y=None, height=dp(40)))      # status bar space
        body = FloatLayout()
        outer.add_widget(body)
        outer.add_widget(StepBar("recover"))
        self.add_widget(outer)

        body.add_widget(Art("et_frame", fb_frame, size_hint=(0.94, 1),
                            pos_hint={"center_x": .5, "center_y": .5}))
        col = BoxLayout(orientation="vertical", size_hint=(0.84, 0.92), spacing=dp(10),
                        pos_hint={"center_x": .5, "center_y": .5})
        body.add_widget(col)

        # source file
        src = BoxLayout(size_hint_y=None, height=dp(56), padding=(dp(14), dp(8)),
                        spacing=dp(10))
        add_border(src, radius=dp(10))
        src.add_widget(Art("et_file", fb_file, size_hint=(None, None), size=(dp(28), dp(32)),
                           pos_hint={"center_y": .5}))
        self.source = line_label("", "11sp", DIM, halign="center",
                                 shorten=True, shorten_from="center")
        src.add_widget(self.source)
        col.add_widget(src)

        # heading
        head = BoxLayout(size_hint_y=None, height=dp(30), spacing=dp(8))
        head.add_widget(Art("et_sparkle", fb_sparkle, size_hint=(None, None),
                            size=(dp(24), dp(24)), pos_hint={"center_y": .5}))
        head.add_widget(line_label(TEXT["heading"], "15sp", CYAN))
        col.add_widget(head)

        # rows
        box = BoxLayout(padding=dp(6))
        add_border(box, radius=dp(12))
        scroll = ScrollView(bar_width=dp(4), bar_color=(0.6, 0.4, 1, 0.9),
                            bar_inactive_color=(0.6, 0.4, 1, 0.4))
        self.rows = GridLayout(cols=1, size_hint_y=None, spacing=dp(8),
                               padding=(dp(4), dp(4)))
        self.rows.bind(minimum_height=self.rows.setter("height"))
        scroll.add_widget(self.rows)
        box.add_widget(scroll)
        col.add_widget(box)

        # legend
        legend = BoxLayout(size_hint_y=None, height=dp(44), padding=(dp(14), dp(8)),
                           spacing=dp(8))
        add_border(legend, radius=dp(10))
        legend.add_widget(Art("et_swatch_term", fb_swatch(*TERM_COLORS), size_hint=(None, None),
                              size=(dp(20), dp(20)), pos_hint={"center_y": .5}))
        legend.add_widget(line_label(TEXT["legend_term"], "11sp", AMBER))
        legend.add_widget(Art("et_swatch_def", fb_swatch(*MASK_COLORS), size_hint=(None, None),
                              size=(dp(20), dp(20)), pos_hint={"center_y": .5}))
        legend.add_widget(line_label(TEXT["legend_def"], "11sp", (0.6, 0.45, 1, 1)))
        col.add_widget(legend)

        # continue
        go = ArtButton("et_continue", fb_continue, size_hint=(1, None))
        go.bind(width=lambda i, v: setattr(i, "height", v * CONTINUE_RATIO))
        go.bind(on_release=lambda *a: self.go_continue())
        col.add_widget(go)

    def _upd_bg(self, *args):
        self._bg.pos, self._bg.size = self.pos, self.size

    # ---------------------------------------------------------------- public
    def load(self, entries, det, filename):
        """Fill the page. entries: from reconstruction.pairs.split_entries(det)."""
        self.entries = entries
        self.filename = filename or "photo"
        self.source.text = TEXT["source"] + self.filename
        self.rows.clear_widgets()
        shown = [e for e in entries if e.term or e.def_words]
        if not shown:
            self.rows.add_widget(text(TEXT["empty"], "12sp", DIM, halign="center"))
            return
        for e in shown:
            self.rows.add_widget(ExtractedRow(e, det))

    def go_continue(self):
        if not any(e.term or e.def_words for e in self.entries):
            notice("No terms were found in this photo. Go back and try another picture.")
            return
        content = self.manager.get_screen("extractedcontent")
        if getattr(content, "loaded_entries", None) is not self.entries:
            content.load_pairs(self.entries, self.filename)   # keep the user's edits when coming back
            content.loaded_entries = self.entries
        self.manager.transition.direction = "left"
        self.manager.current = "extractedcontent"

    def go_back(self):
        self.manager.transition.direction = "right"
        self.manager.current = "scan"