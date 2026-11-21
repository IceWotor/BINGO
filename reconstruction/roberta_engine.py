"""RoBERTa masked-LM engine. Drop-in for reconstruct_words(..., engine=get_engine())."""
import math
import os
import re
import time
from difflib import SequenceMatcher

import numpy as np

from . import config
from .lm import norm_word
from .mlm import OnnxBackend, BackendUnavailable
from .roberta_tok import RobertaTokenizer

WINDOW = 30          # words of context on each side of a slot
MAX_SIDE = 200       # tokens of context on each side (model limit is 512)


class RobertaEngine:
    def __init__(self, model_dir=None):
        self.model_dir = model_dir or config.ROBERTA_DIR
        self.name = "roberta:" + os.path.basename(self.model_dir.rstrip("/\\"))
        self.stats = {}
        self._tok = None
        self._be = None
        self._pools = {}

    # ------------------------------------------------------------ setup
    def _load(self):
        if self._be is not None:
            return
        self._tok = RobertaTokenizer(self.model_dir)
        for fn in ("model.int8.onnx", "model.onnx"):
            p = os.path.join(self.model_dir, fn)
            if os.path.exists(p):
                self._be = OnnxBackend(p, pad_id=self._tok.pad_id)
                return
        raise BackendUnavailable("no ONNX model in " + self.model_dir)

    # ------------------------------------------------------------ helpers
    @staticmethod
    def _sequence(words, slots):
        gap_at, tok_at = {}, {}
        for s in slots:
            (gap_at if s.kind == "gap" else tok_at)[s.position] = s
        seq, skip_to = [], -1
        for i, w in enumerate(words):
            if i <= skip_to:
                continue
            if i in gap_at:
                seq.append(gap_at[i])
            if i in tok_at:
                seq.append(tok_at[i])
                if tok_at[i].span_end is not None:
                    skip_to = tok_at[i].span_end
            else:
                seq.append(w.text)
        return seq

    @staticmethod
    def _words(items):
        """Items -> raw words. Other slots show their current answer."""
        out = []
        for x in items:
            if isinstance(x, str):
                out.append(x)
            elif x.chosen_words:
                out += x.chosen_words
            elif x.kind == "token" and not (x.prefix or x.suffix):
                out.append(x.observed)
        return out

    def _pool(self, slot, lm, cap):
        """[(word, token id)] this slot may choose from (single-token words only)."""
        if slot.prefix or slot.suffix:
            words = (lm.match(slot.prefix, slot.suffix, slot.hidden)
                     or lm.match(slot.prefix, slot.suffix, -1) or lm.cand_words)
        else:
            words = lm.cand_words
        key = (id(words), cap, slot.prefix, slot.suffix, slot.hidden)
        if key in self._pools:
            return self._pools[key]
        out = []
        for w in words:
            i = self._tok.word_id(w.capitalize() if cap else w)
            if i is not None:
                out.append((w, i))
        self._pools[key] = out
        return out

    @staticmethod
    def _channel(s, w):
        """How much the candidate resembles what OCR saw."""
        from .reconstruct import CHANNEL_W, LEN_W
        if s.kind != "token":
            return 0.0
        if s.prefix or s.suffix:
            if s.hidden >= 0:
                return -LEN_W * abs(len(w) - (len(s.prefix) + len(s.suffix) + s.hidden))
            return 0.0
        obs = re.sub(r"[^a-z]", "", s.observed.lower())
        if len(obs) < 2:
            return 0.0
        return CHANNEL_W * (1 - s.features.get("shape", 0.0)) * SequenceMatcher(None, obs, w).ratio()

    # ------------------------------------------------------------ one slot
    def _solve(self, s, k, seq, lm):
        from .reconstruct import Candidate
        tok = self._tok
        left_items, right_items = seq[max(0, k - WINDOW):k], seq[k + 1:k + 1 + WINDOW]
        left_ids = tok.encode_words(self._words(left_items))[-MAX_SIDE:]
        right_ids = tok.encode_words(self._words(right_items))[:MAX_SIDE]

        prev = self._words(seq[max(0, k - 3):k])
        plain = s.kind == "token" and not (s.prefix or s.suffix)
        cap = (not prev) or prev[-1][-1:] in ".!?" or (plain and s.observed[:1].isupper())

        lw = [norm_word(w) for w in self._words(seq[max(0, k - 3):k])]
        rw = [norm_word(w) for w in self._words(seq[k + 1:k + 4])]
        s.left = [w for w in lw if w][-2:]
        s.right = [w for w in rw if w][:2]
        s.support = min(1.0, (len(s.left) + len(s.right)) / 4.0)

        n = max(1, s.n_words) if s.kind == "gap" else 1
        chosen = []
        for step in range(n):
            pool = self._pool(s, lm, cap and step == 0)
            if not pool:
                s.chosen_words = [re.sub(r"[^A-Za-z]", "", s.observed) or "..."]
                return
            pid = np.array([i for _, i in pool])
            done = tok.encode_words([w.capitalize() if (cap and j == 0) else w
                                     for j, w in enumerate(chosen)])
            ids = ([tok.cls_id] + left_ids + done + [tok.mask_id] * (n - step)
                   + right_ids + [tok.sep_id])
            pos = 1 + len(left_ids) + len(done)
            z = self._be.logits_at([(ids, [pos])])[0][0].astype(np.float64)
            self.passes += 1

            m = z.max()
            lse = m + math.log(float(np.exp(z - m).sum()))
            lp = z[pid] - lse
            ch = np.array([self._channel(s, w) for w, _ in pool]) if step == n - 1 else np.zeros(len(pool))
            total = lp + ch
            if step < n - 1:
                chosen.append(pool[int(total.argmax())][0])
                continue

            tm = total.max()
            ex = np.exp(total - tm)
            probs = ex / ex.sum()
            order = np.argsort(-probs)
            s.candidates = [Candidate(" ".join(chosen + [pool[j][0]]), float(lp[j]),
                                      float(ch[j]), 0.0, float(total[j]), float(probs[j]))
                            for j in order[:6]]
            s.chosen_words = chosen + [pool[int(order[0])][0]]
            s.top_prob = float(probs[order[0]])
            s.margin = s.top_prob - (float(probs[order[1]]) if len(order) > 1 else 0.0)
            s.entropy = float(-(probs[probs > 0] * np.log2(probs[probs > 0])).sum())
            s.log_z = float(tm + math.log(float(ex.sum())))
            s.n_cands = len(pool)
            s.recon_conf = s.top_prob * s.support
            s.lm_note = ""

    # ------------------------------------------------------------ public
    def fill(self, words, slots):
        from .reconstruct import get_base_lm
        t0 = time.perf_counter()
        self._load()
        lm = get_base_lm()
        seq = self._sequence(words, slots)
        self.passes = 0
        for _ in range(2):          # 2nd pass sees the neighbours' first answers
            for k, x in enumerate(seq):
                if not isinstance(x, str):
                    self._solve(x, k, seq, lm)
        ms = (time.perf_counter() - t0) * 1000.0
        self.stats = dict(rows=self.passes, ms=ms, total_ms=ms, slots=len(slots))

_engine = None

def get_engine():
    global _engine
    if _engine is None:
        _engine = RobertaEngine()
    return _engine