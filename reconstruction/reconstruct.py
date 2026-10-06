import math
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from . import config
from .damage import analyse
from .lm import NGramLM, load_corpus_sentences
from .ocr_engine import run_ocr
from .terms import extract_terms

CHANNEL_W = 4.0     # log-bonus for resembling what OCR saw
PAGE_BONUS = 0.8    # log-bonus for words already used on this page
KEEP, BEAM = 30, 4
MAX_SLOT_FRAC = 0.35


@dataclass
class Candidate:
    phrase: str
    ng_logp: float
    channel: float
    page_bonus: float
    total: float = 0.0
    prob: float = 0.0


@dataclass
class Slot:
    id: int
    kind: str            # "token" (replace a damaged word) or "gap" (insert words)
    position: int
    observed: str
    p_damage: float
    features: dict
    n_words: int = 1
    left: list = field(default_factory=list)
    right: list = field(default_factory=list)
    candidates: list = field(default_factory=list)
    chosen_words: list = field(default_factory=list)
    top_prob: float = 0.0
    margin: float = 0.0
    entropy: float = 0.0
    support: float = 0.0
    recon_conf: float = 0.0
    lm_note: str = ""
    n_cands: int = 0
    log_z: float = 0.0


@dataclass
class Result:
    words: list
    tokens: list
    gaps: list
    stats: dict
    slots: list
    annotated: str
    terms: list
    ocr_mean_conf: float
    has_conf: bool


_cache = {}


def corpus_sentences():
    if "sents" not in _cache:
        _cache["sents"] = load_corpus_sentences(config.CORPUS_DIR)
    return _cache["sents"]


def get_base_lm():
    if "base" not in _cache:
        lm = NGramLM()
        lm.train(corpus_sentences())
        lm.finalize()
        _cache["base"] = lm
    return _cache["base"]


def _softmax(vals):
    m = max(vals)
    ex = [math.exp(v - m) for v in vals]
    z = sum(ex)
    return [e / z for e in ex]


def _left(seq, k):
    out = []
    for x in seq[:k]:
        out += [x] if isinstance(x, str) else x.chosen_words
    return out[-2:]


def _right(seq, k):
    out = []
    for x in seq[k + 1:]:
        if not isinstance(x, str):
            break                      # next hole is unresolved: stop
        out.append(x)
        if len(out) == 2:
            break
    return out


def _solve(slot, lm, left, right, page_vocab):
    slot.left, slot.right = left, right
    slot.support = min(1.0, (len(left) + len(right)) / 4.0)
    n = max(1, slot.n_words)

    # ---- beam search; right-hand context only matters for the last word
    hyps = [([], 0.0)]
    for step in range(n):
        last = step == n - 1
        nxt = []
        for words, lp in hyps:
            scored = sorted(((lm.lm_score(w, left + words, right if last else []), w)
                             for w in lm.cand_words), reverse=True)
            for s, w in scored[:(KEEP if last else BEAM)]:
                nxt.append((words + [w], lp + s))
        nxt.sort(key=lambda h: -h[1])
        hyps = nxt[:(KEEP if last else BEAM)]

    if not hyps:
        slot.chosen_words = [re.sub(r"[^A-Za-z]", "", slot.observed) or "..."]
        return

    observed = re.sub(r"[^a-z]", "", slot.observed.lower())
    use_channel = slot.kind == "token" and n == 1 and len(observed) >= 2

    cands = []
    for phrase_words, lp in hyps:
        ch = 0.0
        if use_channel:
            ch = (CHANNEL_W * (1 - slot.features["shape"])
                  * SequenceMatcher(None, observed, phrase_words[0]).ratio())
        pb = PAGE_BONUS * sum(w in page_vocab for w in phrase_words)
        cands.append(Candidate(" ".join(phrase_words), lp, ch, pb, lp + ch + pb))

    totals = [c.total for c in cands]
    _m = max(totals)
    slot.log_z = _m + math.log(sum(math.exp(t - _m) for t in totals))
    slot.n_cands = len(cands)
    probs = _softmax([c.total for c in cands])
    for c, p in zip(cands, probs):
        c.prob = p
    cands.sort(key=lambda c: -c.prob)
    probs = [c.prob for c in cands]

    slot.candidates = cands[:6]
    slot.chosen_words = cands[0].phrase.split()
    slot.top_prob = cands[0].prob
    slot.margin = cands[0].prob - (cands[1].prob if len(cands) > 1 else 0.0)
    slot.entropy = -sum(p * math.log2(p) for p in probs if p > 0)
    slot.recon_conf = slot.top_prob * slot.support

    e = lm.explain(slot.chosen_words[0], left)
    slot.lm_note = (f"P('{slot.chosen_words[0]}' | '{' '.join(left[-2:])}') = {e['p_tri']:.4f} "
                    f"[trigram seen {e['c_tri']}x, bigram seen {e['c_bi']}x; "
                    f"uni {e['p_uni']:.5f} -> bi {e['p_bi']:.4f} -> tri {e['p_tri']:.4f}]")

@dataclass
class Detection:
    words: list
    tokens: list
    gaps: list
    stats: dict
    has_conf: bool


def detect(words, has_conf=True):
    """OCR words -> which words and gaps look damaged. No reconstruction yet."""
    base = get_base_lm()
    tokens, gaps, stats = analyse(words, base)

    # safety cap: if OCR is hopeless, don't flag the entire page
    flagged = [t for t in tokens if t.flagged]
    limit = int(MAX_SLOT_FRAC * len(words)) + 1
    if len(flagged) > limit:
        for t in sorted(flagged, key=lambda t: -t.p_damage)[limit:]:
            t.flagged = False

    return Detection(words, tokens, gaps, stats, has_conf)

def reconstruct_words(words, has_conf=True, detection=None):
    det = detection or detect(words, has_conf)
    tokens, gaps, stats = det.tokens, det.gaps, det.stats
    base = get_base_lm()

    gap_at = {g.position: g for g in gaps}
    seq, slots = [], []
    for i, t in enumerate(tokens):
        if i in gap_at:
            g = gap_at[i]
            s = Slot(len(slots) + 1, "gap", i, "", g.p_gap,
                     dict(gap_px=g.gap_px, ratio=g.ratio), n_words=g.est_words)
            slots.append(s)
            seq.append(s)
        if t.kind == "skip":
            continue
        if t.flagged:
            s = Slot(len(slots) + 1, "token", i, t.word.text, t.p_damage,
                     dict(ocr=t.f_ocr, lm=t.f_lm, shape=t.f_shape, z=t.z,
                          conf=t.word.conf, bits=t.bits, zlm=t.z_lm, why=t.why))
            slots.append(s)
            seq.append(s)
        elif t.norm:
            seq.append(t.norm)

    page_vocab = {x for x in seq if isinstance(x, str)}

    runs, cur = [], []
    for x in seq:
        if isinstance(x, str):
            cur.append(x)
        elif cur:
            runs.append(cur)
            cur = []
    if cur:
        runs.append(cur)
    lm = base.clone()
    lm.train(runs)
    lm.finalize()

    for k, x in enumerate(seq):
        if isinstance(x, Slot):
            _solve(x, lm, _left(seq, k), _right(seq, k), page_vocab)

    def marker(s):
        return "{{%d|%s}}" % (s.id, " ".join(s.chosen_words))

    repl = {s.position: s for s in slots if s.kind == "token"}
    ins = {s.position: s for s in slots if s.kind == "gap"}
    lines = {}
    for i, w in enumerate(words):
        parts = lines.setdefault(w.line, [])
        if i in ins:
            parts.append(marker(ins[i]))
        parts.append(marker(repl[i]) if i in repl else w.text)
    annotated = "\n".join(" ".join(p) for _, p in sorted(lines.items()))

    confs = [w.conf for w in words if w.conf >= 0]
    mean_conf = sum(confs) / len(confs) if confs else 0.0
    terms = extract_terms(annotated, {s.id: s for s in slots}, mean_conf)
    return Result(words, tokens, gaps, stats, slots, annotated, terms,
                  mean_conf, det.has_conf)

def reconstruct_page(image_path):
    words, has_conf = run_ocr(image_path)
    return reconstruct_words(words, has_conf)