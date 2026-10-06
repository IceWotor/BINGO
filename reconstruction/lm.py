import glob
import math
import os
import re
from collections import Counter

BOS, EOS = "<s>", "</s>"


def norm_word(s):
    return re.sub(r"[^a-z']", "", s.lower()).strip("'")


def sentences(text):
    for sent in re.split(r"[.!?;]+", text):
        toks = [norm_word(t) for t in sent.split()]
        toks = [t for t in toks if t]
        if toks:
            yield toks


def load_corpus_sentences(folder):
    out = []
    for path in glob.glob(os.path.join(folder, "*.txt")):
        with open(path, encoding="utf-8", errors="ignore") as f:
            out.extend(sentences(f.read()))
    return out


class NGramLM:
    """
    Trigram LM, interpolated absolute discounting (Kneser-Ney style):
      P_uni(w)     = (N1+(. w) + 1) / (#bigram types + V + 2)    continuation prob
      P_bi(w|b)    = [max(c(b,w)-d,0) + d*N1+(b .)*P_uni(w)] / c(b)
      P_tri(w|a,b) = [max(c(a,b,w)-d,0) + d*N1+(a b .)*P_bi(w|b)] / c(a,b)
    Unseen contexts back off to the lower order.
    """

    def __init__(self, discount=0.75):
        self.d = discount
        self.uni, self.bi, self.tri = Counter(), Counter(), Counter()
        self.bi_ctx, self.bi_types, self.cont = Counter(), Counter(), Counter()
        self.tri_ctx, self.tri_types = Counter(), Counter()
        self.vocab, self.cand_words, self.n_bi_types = set(), [], 0

    @property
    def ready(self):
        return len(self.vocab) > 50

    def clone(self):
        n = NGramLM(self.d)
        n.uni, n.bi, n.tri = Counter(self.uni), Counter(self.bi), Counter(self.tri)
        return n

    def train(self, sents):
        for toks in sents:
            pad = [BOS, BOS] + toks + [EOS]
            for i in range(2, len(pad)):
                self.uni[pad[i]] += 1
                self.bi[(pad[i - 1], pad[i])] += 1
                self.tri[(pad[i - 2], pad[i - 1], pad[i])] += 1

    def finalize(self):
        self.bi_ctx, self.bi_types, self.cont = Counter(), Counter(), Counter()
        self.tri_ctx, self.tri_types = Counter(), Counter()
        for (a, b), c in self.bi.items():
            self.bi_ctx[a] += c
            self.bi_types[a] += 1
            self.cont[b] += 1
        for (a, b, _), c in self.tri.items():
            self.tri_ctx[(a, b)] += c
            self.tri_types[(a, b)] += 1
        self.n_bi_types = len(self.bi)
        self.vocab = {w for w in self.uni if w not in (BOS, EOS)}
        ranked = [w for w, _ in self.uni.most_common()
                  if w in self.vocab and (len(w) > 1 or w in ("a", "i"))]
        self.cand_words = ranked[:5000]

    def _p(self, w, w1, w2):
        d = self.d
        p_uni = (self.cont[w] + 1) / (self.n_bi_types + len(self.vocab) + 2)
        c1 = self.bi_ctx[w2]
        p_bi = ((max(self.bi[(w2, w)] - d, 0) + d * self.bi_types[w2] * p_uni) / c1
                if c1 else p_uni)
        c2 = self.tri_ctx[(w1, w2)]
        p_tri = ((max(self.tri[(w1, w2, w)] - d, 0) + d * self.tri_types[(w1, w2)] * p_bi) / c2
                 if c2 else p_bi)
        return p_uni, p_bi, p_tri

    def prob(self, w, w1, w2):
        return self._p(w, w1, w2)[2]

    def lm_score(self, w, left, right):
        """log P(w|left) + log P(r1|left,w) + log P(r2|w,r1)"""
        ctx = ([BOS, BOS] + list(left))[-2:]
        s = math.log(self.prob(w, ctx[0], ctx[1]))
        ctx = [ctx[1], w]
        for r in right[:2]:
            s += math.log(self.prob(r, ctx[0], ctx[1]))
            ctx = [ctx[1], r]
        return s

    def explain(self, w, left):
        ctx = ([BOS, BOS] + list(left))[-2:]
        u, b, t = self._p(w, ctx[0], ctx[1])
        return dict(p_uni=u, p_bi=b, p_tri=t,
                    c_tri=self.tri[(ctx[0], ctx[1], w)],
                    c_bi=self.bi[(ctx[1], w)])