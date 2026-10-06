import math
import re
import statistics
from dataclasses import dataclass

from .lm import BOS, norm_word

WEIGHTS = dict(bias=-3.2, ocr=2.6, lm=1.8, shape=2.2)   # hand-set
GAP_K, GAP_MID = 2.0, 2.5
THRESH = 0.5

_SYMBOLS = set("|_~^`\\/<>{}[]=*#@")
_MARKER = re.compile(r"^[a-eA-E1-9]\d?[\.,\)]$")


def sigmoid(z):
    return 1.0 / (1.0 + math.exp(-z))


@dataclass
class TokenReport:
    word: object
    kind: str            # "word" or "skip" (punctuation, numbers, list markers)
    norm: str
    f_ocr: float
    f_lm: float
    f_shape: float
    z: float
    p_damage: float
    bits: float          # surprisal in bits (None if unavailable)
    z_lm: float
    why: str
    flagged: bool


@dataclass
class GapReport:
    position: int        # word index the gap sits in front of
    gap_px: float
    ratio: float
    est_words: int
    p_gap: float


def shape_score(text, lm):
    """-> (kind, f_shape, reason)"""
    if _MARKER.match(text):
        return "skip", 0.0, "list marker"
    t = text.strip(".,;:!?()\"'")
    letters = sum(c.isalpha() for c in t)
    if letters == 0:
        if t and all(c in _SYMBOLS for c in t):
            return "word", 1.0, "symbol noise"
        return "skip", 0.0, "punctuation/number"
    n = norm_word(text)
    s, why = 0.0, []
    if letters / len(t) < 0.6:
        s = 1.0
        why.append("mostly non-letters")
    if re.search(r"[bcdfghjklmnpqrstvwxz]{5,}", n):
        s = 1.0
        why.append("5+ consonants in a row")
    if re.search(r"(.)\1\1", n):
        s = 1.0
        why.append("3+ repeated letters")
    if len(n) == 1 and n not in ("a", "i"):
        s = 1.0
        why.append("single stray letter")
    if lm.ready and n and n not in lm.vocab:
        if s < 0.6:
            s = 0.6
        why.append("not in vocabulary")
    return "word", s, ", ".join(why) or "looks fine"


def analyse(words, lm):
    kinds = [shape_score(w.text, lm) for w in words]
    norms = [norm_word(w.text) for w in words]

    # ---- surprisal of each word given its 2 previous words
    seq_idx = [i for i, k in enumerate(kinds) if k[0] == "word" and norms[i]]
    bits = {}
    if lm.ready:
        for j, i in enumerate(seq_idx):
            ctx = ([BOS, BOS] + [norms[k] for k in seq_idx[max(0, j - 2):j]])[-2:]
            bits[i] = -math.log2(lm.prob(norms[i], ctx[0], ctx[1]))
    if len(bits) > 2:
        mu = statistics.mean(bits.values())
        sd = statistics.pstdev(bits.values()) or 1.0
    else:
        mu, sd = 0.0, 1.0

    # ---- per-word damage
    toks = []
    for i, w in enumerate(words):
        kind, f_shape, why = kinds[i]
        f_ocr = 1.0 - max(w.conf, 0.0) / 100.0
        if i in bits:
            z_lm = (bits[i] - mu) / sd
            f_lm, b = sigmoid(z_lm), bits[i]
        else:
            z_lm, f_lm, b = None, 0.5, None
        if kind == "skip":
            z, p = 0.0, 0.0
        else:
            z = (WEIGHTS["bias"] + WEIGHTS["ocr"] * f_ocr
                 + WEIGHTS["lm"] * f_lm + WEIGHTS["shape"] * f_shape)
            p = sigmoid(z)
        toks.append(TokenReport(w, kind, norms[i], f_ocr, f_lm, f_shape,
                                z, p, b, z_lm, why,
                                kind == "word" and p >= THRESH))

    # ---- gaps between neighbouring words on the same line
    by_line = {}
    for w in words:
        by_line.setdefault(w.line, []).append(w)
    raw = []
    for ws in by_line.values():
        ws.sort(key=lambda w: w.x)
        for a, b in zip(ws, ws[1:]):
            g = b.x - (a.x + a.w)
            if g > 0:
                raw.append((b.idx, g))
    med_gap = max(statistics.median([g for _, g in raw]), 1.0) if raw else 1.0
    wid = [w.w for w, k in zip(words, kinds) if k[0] == "word"]
    med_w = statistics.median(wid) if wid else 1.0

    gaps = []
    for idx, g in raw:
        ratio = g / med_gap
        est = int(round(g / (med_w + med_gap)))
        p = sigmoid(GAP_K * (ratio - GAP_MID))
        if est >= 1 and p >= THRESH:
            gaps.append(GapReport(idx, g, ratio, min(est, 3), p))

    return toks, gaps, dict(med_gap=med_gap, med_w=med_w)