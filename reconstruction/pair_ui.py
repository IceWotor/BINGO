"""Kivy widget for one term/definition pair (the cards on the extracted-content screen)."""
import threading
import traceback

from kivy.clock import Clock, mainthread
from kivy.core.image import Image as CoreImage
from kivy.graphics import BorderImage, Color, Line, Rectangle
from kivy.metrics import dp
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget

from .pair_state import (apply_edit, computation_markup, reconstruct_pair,
                         render_markup, text_with_marks, undo_pair, ensure_det,
                         pair_is_incomplete)

FONT = "./assets/fonts/PixelifySans.ttf"
FONT_PX = "./assets/fonts/PressStart2P.ttf"
AMBER = (1, 0.749, 0.2, 1)
DEF_COLOR = (0.604, 0.4, 0.894, 1)
DIM = (0.6, 0.56, 0.71, 1)
WARN_COLOR = (0.85, 0.15, 0.15, 1)

# ---- card art: swap the files here only
EC = "./assets/pageAssets/extractedcontent/"
CARD_OK = EC + "definitionContainer.png"
CARD_BAD = EC + "incompleteContainer_notext.png"
CARD_SLICE = 12          # corner size inside the PNG, in image pixels (after trimming)
CARD_DISPLAY = 8         # how big the corners are DRAWN, in dp. Bigger = thicker border.
ALPHA_CUT = 100          # pixels fainter than this count as empty padding (glow/shadow)
CARD_PAD = (16, 14)      # space between the border and the text: (left/right, top/bottom) in dp
BTN_EDIT = EC + "edit.png"
BTN_DELETE = EC + "delete.png"
BTN_SIZE = 24            # edit / delete / undo button size, in dp

HINT = ("Wrap words in <<double angle brackets>> to mark them for reconstruction, "
        "e.g. plants and <<cyabateria>> use light")

_tex = {}


def _texture(path):
    """Load a PNG, trim its transparent padding so the border sits flush with the
    widget edges, and use crisp (nearest) scaling so pixel art stays sharp."""
    if path not in _tex:
        tex = CoreImage(path).texture
        try:
            from PIL import Image as PILImage
            alpha = PILImage.open(path).convert("RGBA").getchannel("A")
            bb = alpha.point(lambda v: 255 if v > ALPHA_CUT else 0).getbbox()
            if bb:
                left, top, right, bottom = bb
                tex = tex.get_region(left, tex.height - bottom, right - left, bottom - top)
        except Exception:
            traceback.print_exc()          # falls back to the untrimmed picture
        tex.mag_filter = "nearest"
        tex.min_filter = "nearest"
        _tex[path] = tex
    return _tex[path]


def _label(markup, size="12sp"):
    lbl = Label(text=markup, markup=True, font_name=FONT, font_size=size,
                color=(1, 1, 1, 1), size_hint_y=None, halign="left", valign="top")
    lbl.bind(width=lambda i, v: setattr(i, "text_size", (v, None)))
    lbl.bind(texture_size=lambda i, v: setattr(i, "height", v[1] + dp(8)))
    return lbl


class ImgButton(ButtonBehavior, Image):
    """Button that is just your PNG."""

    def __init__(self, source, **kwargs):
        super().__init__(source=source, size_hint=(None, None),
                         size=(dp(BTN_SIZE), dp(BTN_SIZE)),
                         allow_stretch=True, keep_ratio=False, **kwargs)
        self.bind(disabled=lambda i, v: setattr(i, "opacity", 0.4 if v else 1))
        if self.texture:
            self.texture.mag_filter = "nearest"      # keep pixel art crisp


class IconButton(Button):
    """Drawn undo button (no PNG for it)."""

    def __init__(self, **kwargs):
        super().__init__(text="", size_hint=(None, None),
                         size=(dp(BTN_SIZE), dp(BTN_SIZE)),
                         background_normal="", background_down="",
                         background_color=(0, 0, 0, 0), **kwargs)
        self.bind(pos=self._draw, size=self._draw, disabled=self._draw, state=self._draw)
        self._draw()

    def _draw(self, *args):
        x, y = self.pos
        w, h = self.size
        col = (0.4, 0.4, 0.55, 1) if self.disabled else (0.35, 0.66, 1, 1)

        def p(fx, fy):
            return (x + fx * w, y + fy * h)

        c = self.canvas.after
        c.clear()
        with c:
            Color(0.3, 0.2, 0.7, 1) if self.state == "down" else Color(0.1, 0.07, 0.35, 1)
            Rectangle(pos=self.pos, size=self.size)
            Color(*col)
            Line(rectangle=(x, y, w, h), width=1.5)
            Line(points=[*p(.72, .3), *p(.72, .6), *p(.34, .6)], width=1.8)
            Line(points=[*p(.46, .72), *p(.34, .6), *p(.46, .48)], width=1.8)


class PairCard(BoxLayout):
    def __init__(self, pair, on_delete, **kwargs):
        super().__init__(orientation="vertical", size_hint_y=None,
                         padding=(dp(CARD_PAD[0]), dp(CARD_PAD[1])), spacing=dp(6), **kwargs)
        self.pair = pair
        self.on_delete = on_delete
        self.editing = False
        self.editor = None
        self.hint = None
        self.term_editor = None
        self.busy = False
        self.open_comp = False
        self.incomplete = False
        self.on_change = None           # the screen sets this
        ensure_det(pair)

        self.bind(minimum_height=self.setter("height"))
        with self.canvas.before:
            Color(1, 1, 1, 1)
            self._bg = BorderImage(texture=_texture(CARD_OK),
                                   border=(CARD_SLICE,) * 4,
                                   display_border=(dp(CARD_DISPLAY),) * 4)
        self.bind(pos=self._upd, size=self._upd)

        # ---- term row: term ... [undo][reconstruct][delete]
        self.head = BoxLayout(size_hint_y=None, height=dp(34), spacing=dp(6))
        self.term_lbl = Label(text="", font_name=FONT, font_size="17sp", halign="left",
                              valign="middle", size_hint_y=None, height=dp(34))
        self.term_lbl.bind(width=lambda i, v: setattr(i, "text_size", (v, None)))
        self.term_lbl.bind(texture_size=lambda i, v: self._term_height())
        self.head.add_widget(self.term_lbl)
        self.undo_btn = IconButton(pos_hint={"center_y": .5})
        self.fix_btn = ImgButton(BTN_EDIT, pos_hint={"center_y": .5})
        self.del_btn = ImgButton(BTN_DELETE, pos_hint={"center_y": .5})
        self.undo_btn.bind(on_release=self.on_undo)
        self.fix_btn.bind(on_release=self.on_fix)
        self.del_btn.bind(on_release=lambda *a: self.on_delete(self))
        for b in (self.undo_btn, self.fix_btn, self.del_btn):
            self.head.add_widget(b)
        self.add_widget(self.head)
        self.add_widget(Widget(size_hint_y=None, height=dp(6)))

        # ---- definition (tap to edit)
        self.def_box = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(4))
        self.def_box.bind(minimum_height=self.def_box.setter("height"))
        self.def_lbl = Label(markup=True, font_name=FONT, font_size="12sp", color=DEF_COLOR,
                             halign="left", valign="top", size_hint_y=None, height=dp(20))
        self.def_lbl.bind(width=lambda i, v: setattr(i, "text_size", (v, None)))
        self.def_lbl.bind(texture_size=self._def_size)
        self.def_lbl.bind(pos=self._draw_marks, refs=self._draw_marks)
        self.def_box.add_widget(self.def_lbl)
        self.add_widget(self.def_box)

        self.status = Label(text="", font_name=FONT, font_size="10sp", color=DIM,
                            halign="left", valign="middle", size_hint_y=None,
                            height=0, opacity=0)
        self.status.bind(width=lambda i, v: setattr(i, "text_size", (v, None)))
        self.add_widget(self.status)

        # ---- red message, only while incomplete
        self.warn = Label(text="Text is incomplete, please check.", font_name=FONT,
                          font_size="11sp", color=WARN_COLOR, halign="center",
                          valign="middle", size_hint_y=None, height=0, opacity=0)
        self.warn.bind(width=lambda i, v: setattr(i, "text_size", (v, None)))
        self.add_widget(self.warn)

        # ---- computation dropdown
        self.comp_btn = Button(text="+ SHOW COMPUTATION", font_name=FONT_PX, font_size="8sp",
                               color=DIM, size_hint_y=None, height=dp(28), halign="left",
                               background_normal="", background_down="",
                               background_color=(0, 0, 0, 0))
        self.comp_btn.bind(size=lambda i, v: setattr(i, "text_size", v))
        self.comp_btn.bind(on_release=self.toggle_comp)
        self.add_widget(self.comp_btn)
        self.comp_body = _label("", "10sp")

        self._show_term()
        self.refresh()

    # ------------------------------------------------------------ layout helpers
    def _upd(self, *args):
        self._bg.pos, self._bg.size = self.pos, self.size

    def _term_height(self):
        self.term_lbl.height = max(dp(34), self.term_lbl.texture_size[1] + dp(6))
        if self.term_editor is None:
            self.head.height = self.term_lbl.height

    def _def_size(self, inst, size):
        inst.height = size[1] + dp(6)
        self._draw_marks()

    def _draw_marks(self, *args):
        """Yellow highlight behind every [ref=mkN] zone (words marked with <<>>)."""
        lbl = self.def_lbl
        lbl.canvas.before.clear()
        with lbl.canvas.before:
            Color(1, 0.85, 0.2, 0.3)
            left = lbl.center_x - lbl.texture_size[0] / 2.0
            top = lbl.center_y + lbl.texture_size[1] / 2.0
            for name, boxes in lbl.refs.items():
                if not name.startswith("mk"):
                    continue
                for (x1, y1, x2, y2) in boxes:
                    Rectangle(pos=(left + x1 - dp(2), top - y2 - dp(1)),
                              size=(x2 - x1 + dp(4), y2 - y1 + dp(2)))

    def _show_term(self):
        t = self.pair.term.strip()
        self.term_lbl.text = t or "(no term found - tap to type one)"
        self.term_lbl.color = AMBER if t else DIM

    def _set_status(self, text):
        self.status.text = text
        self.status.height = dp(18) if text else 0
        self.status.opacity = 1 if text else 0

    def _sync_buttons(self):
        has = bool(self.pair.history)
        self.undo_btn.opacity = 1 if has else 0
        self.undo_btn.disabled = (not has) or self.busy
        self.undo_btn.width = dp(BTN_SIZE) if has else 0
        self.fix_btn.disabled = self.busy

    def _check(self):
        """Red border + message while anything is flagged, marked or has a gap."""
        bad = pair_is_incomplete(self.pair)
        self.incomplete = bad
        self._bg.texture = _texture(CARD_BAD if bad else CARD_OK)
        self.warn.height = dp(22) if bad else 0
        self.warn.opacity = 1 if bad else 0
        if self.on_change:
            self.on_change()

    def refresh(self):
        self.def_lbl.text = render_markup(self.pair)
        self.def_lbl.texture_update()
        self.def_lbl.height = self.def_lbl.texture_size[1] + dp(6)
        self._draw_marks()
        if self.open_comp:
            self.comp_body.text = computation_markup(self.pair)
        self._sync_buttons()
        self._check()

    # ------------------------------------------------------------ taps: edit term / definition
    def on_touch_up(self, touch):
        handled = super().on_touch_up(touch)
        if self.busy or self.editing or self.term_editor is not None:
            return handled
        moved = ((touch.x - touch.ox) ** 2 + (touch.y - touch.oy) ** 2) ** 0.5
        if moved >= dp(10):
            return handled
        if self.def_lbl.collide_point(*touch.pos) and self.def_lbl.collide_point(touch.ox, touch.oy):
            Clock.schedule_once(lambda dt: self.start_edit(), 0)
            return True
        if self.term_lbl.collide_point(*touch.pos) and self.term_lbl.collide_point(touch.ox, touch.oy):
            Clock.schedule_once(lambda dt: self.start_term_edit(), 0)
            return True
        return handled

    def start_term_edit(self):
        if self.term_editor is not None:
            return
        ed = TextInput(text=self.pair.term, multiline=False, font_name=FONT, font_size="16sp",
                       foreground_color=AMBER, cursor_color=AMBER,
                       background_normal="", background_active="",
                       background_color=(1, 1, 1, 0.08), padding=(dp(6), dp(6)),
                       size_hint_y=None, height=dp(34), pos_hint={"center_y": .5})
        ed.bind(focus=lambda i, f: None if f else self.commit_term())
        ed.bind(on_text_validate=lambda *a: self.commit_term())
        self.term_editor = ed
        self.head.remove_widget(self.term_lbl)
        self.head.add_widget(ed, index=len(self.head.children))
        self.head.height = dp(34)
        Clock.schedule_once(lambda dt: setattr(ed, "focus", True), 0.1)

    def commit_term(self):
        ed = self.term_editor
        if ed is None:
            return
        self.term_editor = None
        self.pair.term = ed.text.strip()
        self.head.remove_widget(ed)
        self.head.add_widget(self.term_lbl, index=len(self.head.children))
        self._show_term()
        self._term_height()

    def start_edit(self):
        if self.editing or self.busy:
            return
        self.editing = True
        self.def_box.remove_widget(self.def_lbl)
        self.editor = TextInput(text=text_with_marks(self.pair), font_name=FONT,
                                font_size="13sp", foreground_color=(1, 1, 1, 1),
                                cursor_color=AMBER, background_normal="",
                                background_active="", background_color=(1, 1, 1, 0.08),
                                padding=(dp(8), dp(8)), size_hint_y=None, height=dp(120))
        self.editor.bind(minimum_height=lambda i, v: setattr(i, "height", max(v, dp(120))))
        self.editor.bind(focus=lambda i, f: None if f else self.commit_edit())
        self.hint = _label(HINT, "9sp")
        self.def_box.add_widget(self.editor)
        self.def_box.add_widget(self.hint)
        Clock.schedule_once(lambda dt: setattr(self.editor, "focus", True), 0.1)

    def commit_edit(self):
        if not self.editing:
            return
        text = self.editor.text
        self.editing = False
        self.def_box.remove_widget(self.editor)
        self.def_box.remove_widget(self.hint)
        self.editor = self.hint = None
        try:
            apply_edit(self.pair, text)
        except Exception:
            traceback.print_exc()
            self._set_status("could not read that edit")
        self.def_box.add_widget(self.def_lbl)
        self.refresh()

    def commit_all(self):
        self.commit_term()
        self.commit_edit()

    # ------------------------------------------------------------ buttons
    def toggle_comp(self, *args):
        self.open_comp = not self.open_comp
        if self.open_comp:
            self.comp_btn.text = "- HIDE COMPUTATION"
            self.comp_body.text = computation_markup(self.pair)
            self.add_widget(self.comp_body)
        else:
            self.comp_btn.text = "+ SHOW COMPUTATION"
            self.remove_widget(self.comp_body)

    def on_fix(self, *args):
        if self.busy:
            return
        self.commit_all()
        self.busy = True
        self._sync_buttons()
        self._set_status("reconstructing...")
        threading.Thread(target=self._work, daemon=True).start()

    def _work(self):
        n, err = 0, None
        try:
            n = reconstruct_pair(self.pair)
        except Exception as e:
            traceback.print_exc()
            err = "%s: %s" % (type(e).__name__, e)
        self._done(n, err)

    @mainthread
    def _done(self, n, err):
        self.busy = False
        if err:
            self._set_status("failed: " + err[:90])
        elif n:
            engine = getattr(self.pair.result, "engine", "")
            self._set_status("filled %d spot(s) with %s" % (n, engine))
        else:
            self._set_status("nothing looks damaged. Mark words with <<>> to pick some.")
        self.refresh()

    def on_undo(self, *args):
        if self.busy or not self.pair.history:
            return
        self.commit_all()
        undo_pair(self.pair)
        self._set_status("")
        self.refresh()