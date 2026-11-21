"""State and logic for one term/definition card on the extracted-content screen.

Pure Python (no Kivy), so it can be tested on the desktop.
"""
import re
import threading
import traceback
from dataclasses import dataclass, field

from .damage import WEIGHTS, GAP_K, GAP_MID
from .reconstruct import detect, reconstruct_words
from .textedit import text_to_words, words_after_reconstruction

RED, YELLOW, MARK, GREEN, DIM = "ff5555", "ffd23f", "ffe14d", "3fc78c", "9a8fb5"
_LOCK = threading.Lock()        # one reconstruction at a time (shared ONNX session)


def esc(s):
    return str(s).replace("&", "&amp;").replace("[", "&bl;").replace("]", "&br;")


@dataclass
class Pair:
    term: str
    words: list                                   # current definition (Word objects)
    det: object = None                            # Detection of those words
    marked: set = field(default_factory=set)      # word indexes the user marked with <<>>
    history: list = field(default_factory=list)   # states before each reconstruction
    result: object = None                         # last reconstruction Result

    def definition_text(self):
        return " ".join(w.text for w in self.words)


# ------------------------------------------------------------ detection
def refresh_pair(p):
    """Re-run the damage check on the current words."""
    if not p.words:
        p.det, p.marked = None, set()
        return
    det = detect(p.words, True)
    for i, t in enumerate(det.tokens):
        if getattr(p.words[i], "src", "ocr") in ("filled", "typed"):
            t.flagged = False                    # reconstructed or typed by the user: trusted
        if i in p.marked and t.kind == "word":
            t.flagged = True                     # the user marked it: always reconstruct
            t.p_damage = max(t.p_damage, 0.99)
    p.marked = {i for i in p.marked
                if i < len(det.tokens) and det.tokens[i].kind == "word"}
    p.det = det


def ensure_det(p):
    if p.words and (p.det is None or len(p.det.tokens) != len(p.words)):
        refresh_pair(p)


def pair_is_incomplete(p):
    """True while anything is still flagged, marked, or has a gap."""
    ensure_det(p)
    if not p.words or p.det is None:
        return False
    return bool(p.marked) or bool(p.det.gaps) or any(t.flagged for t in p.det.tokens)


# ------------------------------------------------------------ <<markers>>
def parse_marks(text):
    """'a <<b c>> d' -> ('a b c d', {1, 2}): clean text + indexes of marked words."""
    clean, flags, inside, i = [], [], False, 0
    while i < len(text):
        if text.startswith("<<", i):
            inside, i = True, i + 2
            continue
        if text.startswith(">>", i):
            inside, i = False, i + 2
            continue
        clean.append(text[i])
        flags.append(inside)
        i += 1
    clean = "".join(clean)
    marked = set()
    for k, m in enumerate(re.finditer(r"\S+", clean)):
        if any(flags[j] for j in range(m.start(), m.end())):
            marked.add(k)
    return clean, marked


def text_with_marks(p):
    """Definition as editable text, marked words wrapped in << >> (one line per OCR line)."""
    lines = {}
    for i, w in enumerate(p.words):
        lines.setdefault(w.line, []).append(i)
    out = []
    for _, idxs in sorted(lines.items()):
        parts, run = [], []
        for i in idxs:
            if i in p.marked:
                run.append(p.words[i].text)
                continue
            if run:
                parts.append("<<" + " ".join(run) + ">>")
                run = []
            parts.append(p.words[i].text)
        if run:
            parts.append("<<" + " ".join(run) + ">>")
        out.append(" ".join(parts))
    return "\n".join(out)


def apply_edit(p, text):
    clean, marked = parse_marks(text)
    p.words = text_to_words(p.words, clean)
    p.marked = marked
    refresh_pair(p)


# ------------------------------------------------------------ reconstruct / undo
def _engine():
    try:
        from .roberta_engine import get_engine
        return get_engine()
    except Exception:
        traceback.print_exc()
        return None                                # reconstruct_words then uses the trigram solver


def reconstruct_pair(p):
    """Fill in everything currently flagged. -> number of spots filled (0 = nothing to do)."""
    ensure_det(p)
    det = p.det
    if det is None or not p.words:
        return 0
    if not any(t.flagged for t in det.tokens) and not det.gaps:
        return 0
    with _LOCK:
        result = reconstruct_words(p.words, det.has_conf, det, engine=_engine())
    if not result.slots:
        return 0
    p.history.append((p.words, p.det, set(p.marked), p.result))
    p.words = words_after_reconstruction(result)
    p.marked = set()
    p.result = result
    refresh_pair(p)
    return len(result.slots)


def undo_pair(p):
    if not p.history:
        return False
    p.words, p.det, p.marked, p.result = p.history.pop()
    return True


# ------------------------------------------------------------ display
def render_markup(p):
    """Definition as Kivy markup: flagged words yellow/red with %, marked words in a
    [ref=mkN] tag (the card draws the yellow highlight behind those), filled words green."""
    ensure_det(p)
    words = p.words
    if not words:
        return f"[color={DIM}](empty: tap here to type the definition)[/color]"
    det = p.det
    toks = det.tokens
    gap_at = {g.position: g for g in det.gaps}
    out, i, n, ref = [], 0, len(words), 0
    while i < n:
        g = gap_at.get(i)
        if g:
            out.append(f"[color={RED}][b]&bl;missing {g.est_words} "
                       f"@{round(g.p_gap * 100)}%&br;[/b][/color]")
        if i in p.marked:
            j, seg = i, []
            while j < n and j in p.marked and (j == i or j not in gap_at):
                seg.append(esc(words[j].text))
                j += 1
            out.append(f"[ref=mk{ref}][color={MARK}][b]{' '.join(seg)}[/b][/color][/ref]")
            ref += 1
            i = j
            continue
        w, t = words[i], toks[i]
        txt = esc(w.text)
        if t.flagged:
            col = RED if t.p_damage >= 0.8 else YELLOW
            out.append(f"[color={col}][b]{txt}[/b][/color][size=9sp][color={col}]"
                       f" @{round(t.p_damage * 100)}%[/color][/size]")
        elif getattr(w, "src", "ocr") == "filled":
            out.append(f"[color={GREEN}]{txt}[/color][size=9sp][color={GREEN}]"
                       f" {round(w.conf)}%[/color][/size]")
        else:
            out.append(txt)
        i += 1
    return " ".join(out)


def computation_markup(p):
    """The calculation behind the flags, and behind the last reconstruction."""
    ensure_det(p)
    W = WEIGHTS
    L = ["[b][color=ffbf33]WHY THESE PARTS ARE FLAGGED[/color][/b]",
         "Each word gets three scores from 0 to 1:\n"
         "f_ocr = 1 - OCR confidence / 100\n"
         "f_lm = sigmoid(z-score of surprisal), surprisal = -log2 P(word | previous 2 words)\n"
         "f_shape = 1 for garbage (symbols, 5+ consonants...), 0.6 if not a known word\n"
         f"P(damaged) = sigmoid({W['bias']} + {W['ocr']}*f_ocr + {W['lm']}*f_lm + "
         f"{W['shape']}*f_shape), flagged at 50% or more.\n"
         "This detection step is statistics, not RoBERTa. RoBERTa only chooses the "
         "replacement words (see the last section)."]
    det = p.det
    if det is None:
        L.append("\nNo text.")
    else:
        n = 0
        for i, t in enumerate(det.tokens):
            if not t.flagged:
                continue
            n += 1
            head = f"\n[b]{esc(t.word.text)}[/b]"
            if i in p.marked:
                L.append(head + "\nmarked by you with <<>>, so it is always reconstructed.")
                continue
            lines = [head + f"  {t.p_damage * 100:.0f}% damaged",
                     f"OCR confidence {t.word.conf:.0f}%  ->  f_ocr = {t.f_ocr:.2f}"]
            if t.bits is not None:
                lines.append(f"surprisal {t.bits:.1f} bits (z {t.z_lm:+.2f})  ->  f_lm = {t.f_lm:.2f}")
            else:
                lines.append("no surprisal available  ->  f_lm = 0.50")
            lines.append(f"shape: {esc(t.why)}  ->  f_shape = {t.f_shape:.2f}")
            lines.append(f"z = {W['bias']} + {W['ocr']}*{t.f_ocr:.2f} + {W['lm']}*{t.f_lm:.2f} "
                         f"+ {W['shape']}*{t.f_shape:.2f} = {t.z:+.2f}")
            lines.append(f"P(damaged) = sigmoid({t.z:+.2f}) = {t.p_damage * 100:.0f}%")
            L.append("\n".join(lines))
        for g in det.gaps:
            n += 1
            nxt = esc(p.words[g.position].text) if g.position < len(p.words) else ""
            L.append(f"\n[b]~{g.est_words} missing word(s)[/b] before '{nxt}'\n"
                     f"gap {g.gap_px:.0f}px, median gap {det.stats['med_gap']:.0f}px, "
                     f"ratio {g.ratio:.2f}\n"
                     f"missing = round({g.gap_px:.0f} / ({det.stats['med_w']:.0f} + "
                     f"{det.stats['med_gap']:.0f})) = {g.est_words}\n"
                     f"P(gap) = sigmoid({GAP_K} * ({g.ratio:.2f} - {GAP_MID})) = "
                     f"{g.p_gap * 100:.0f}%")
        if n == 0:
            L.append("\nNothing is flagged: every word has good OCR confidence, fits the "
                     "words around it and looks like a real word.")

    r = p.result
    if r is not None:
        L.append("\n[b][color=ffbf33]WHAT THE LAST RECONSTRUCTION DID[/color][/b]")
        err = (r.engine_info or {}).get("error")
        if str(r.engine).startswith("roberta"):
            L.append(f"Engine: {esc(r.engine)}. For each spot RoBERTa reads the words before and "
                     "after it and scores candidate words.\n"
                     "score = RoBERTa log P + OCR similarity;  P = softmax of the scores over "
                     "the candidates;\nconfidence = P(top) x context support.")
        else:
            L.append("RoBERTa was not used (" + esc(err or "not available") +
                     "), so the word-sequence model filled the spots instead.")
        for s in r.slots:
            kind = "damaged word" if s.kind == "token" else f"gap ({s.n_words} word(s))"
            obs = f" '{esc(s.observed)}'" if s.kind == "token" and s.observed else ""
            rows = [f"\n[b]Spot {s.id}: {kind}{obs}[/b]",
                    f"context: ... {esc(' '.join(s.left) or '(start)')} [ ? ] "
                    f"{esc(' '.join(s.right) or '(end)')} ...".replace("[ ? ]", "&bl; ? &br;")]
            for k, c in enumerate(s.candidates[:5], 1):
                rows.append(f"{k}. {esc(c.phrase)}   log P {c.ng_logp:.2f}  "
                            f"OCR {c.channel:+.2f}  ->  P = {c.prob * 100:.0f}%")
            rows.append(f"chosen: [b]{esc(' '.join(s.chosen_words))}[/b]   confidence "
                        f"{s.top_prob * 100:.0f}% x {s.support:.2f} = {s.recon_conf * 100:.0f}%")
            L.append("\n".join(rows))
    return "\n".join(L)