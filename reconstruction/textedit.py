"""Turn edited or reconstructed text back into Word objects the damage check can score."""
import re
import statistics
from dataclasses import replace
from difflib import SequenceMatcher

from .ocr_engine import Word


def words_to_text(words):
    lines = {}
    for w in words:
        lines.setdefault(w.line, []).append(w.text)
    return "\n".join(" ".join(t) for _, t in sorted(lines.items()))


def _stats(words):
    widths = [w.w for w in words if w.w > 0]
    typ_w = statistics.median(widths) if widths else 40.0
    by_line = {}
    for w in words:
        by_line.setdefault(w.line, []).append(w)
    gaps = []
    for ws in by_line.values():
        ws = sorted(ws, key=lambda w: w.x)
        for a, b in zip(ws, ws[1:]):
            g = b.x - (a.x + a.w)
            if g > 0:
                gaps.append(g)
    med_gap = max(statistics.median(gaps), 1.0) if gaps else 5.0
    return typ_w, med_gap


def _spread(texts, left, right, y, h, lines, conf, src, med_gap):
    """Lay new words evenly between left and right, separated by a normal gap."""
    n = len(texts)
    slot = (right - left + med_gap) / n
    width = max(slot - med_gap, 1.0)
    return [Word(0, t, conf, int(left + j * slot), int(y), int(width), int(h),
                 lines[j], src)
            for j, t in enumerate(texts)]


def _reindex(words):
    for i, w in enumerate(words):
        w.idx = i
    return words


def text_to_words(old, text):
    """Words after the user edited the text. Unchanged words keep their position
    and OCR confidence; typed words are trusted (100%)."""
    lines = [ln.split() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]
    flat = [t for ln in lines for t in ln]
    line_of = [n for n, ln in enumerate(lines) for _ in ln]
    typ_w, med_gap = _stats(old)

    out = []
    sm = SequenceMatcher(None, [w.text for w in old], flat, autojunk=False)
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            for k in range(j2 - j1):
                out.append(replace(old[i1 + k], line=line_of[j1 + k]))
            continue
        if j2 == j1:                      # words were deleted
            continue
        texts, n = flat[j1:j2], j2 - j1
        if i2 > i1:                       # words were replaced
            ref = old[i1]
            left = old[i1].x
            right = old[i2 - 1].x + old[i2 - 1].w
            if right <= left:
                right = left + n * typ_w
        else:                             # words were inserted
            prev = old[i1 - 1] if i1 > 0 else None
            nxt = old[i1] if i1 < len(old) else None
            ref = prev or nxt
            if (prev is not None and nxt is not None and prev.line == nxt.line
                    and nxt.x > prev.x + prev.w):
                left, right = prev.x + prev.w, nxt.x
            elif nxt is not None:
                left, right = max(nxt.x - n * typ_w, 0), nxt.x
            else:
                left = prev.x + prev.w if prev else 0
                right = left + n * typ_w
        y = ref.y if ref else 0
        h = ref.h if ref else 30
        out += _spread(texts, left, right, y, h, line_of[j1:j2], 100.0, "typed", med_gap)
    return _reindex(out)


def _dress(orig, new):
    """Keep the original word's capital letter and trailing punctuation."""
    if orig[:1].isupper():
        new = new[:1].upper() + new[1:]
    tail = re.search(r"[.,;:!?)]+$", orig)
    return new + (tail.group(0) if tail else "")


def words_after_reconstruction(result):
    """Words of the reconstructed page. Filled-in words get the reconstruction
    confidence as their confidence."""
    old = result.words
    typ_w, med_gap = _stats(old)
    repl = {s.position: s for s in result.slots if s.kind == "token"}
    ins = {s.position: s for s in result.slots if s.kind == "gap"}

    out = []
    for i, w in enumerate(old):
        if i in ins:
            s = ins[i]
            texts = s.chosen_words
            n = len(texts)
            prev = out[-1] if out and out[-1].line == w.line else None
            left = prev.x + prev.w if prev else max(w.x - n * typ_w, 0)
            right = w.x
            if right <= left:
                right = left + n * typ_w
            out += _spread(texts, left, right, w.y, w.h, [w.line] * n,
                           round(s.recon_conf * 100, 1), "filled", med_gap)
        if i in repl:
            s = repl[i]
            out.append(Word(0, _dress(w.text, s.chosen_words[0]),
                            round(s.recon_conf * 100, 1),
                            w.x, w.y, w.w, w.h, w.line, "filled"))
        else:
            out.append(replace(w))
    return _reindex(out)