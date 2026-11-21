"""Pure-Python RoBERTa (GPT-2 style byte-level BPE) tokenizer."""
import json
import os
import re

_SPLIT = re.compile(r"'(?:s|t|re|ve|m|ll|d)|[A-Za-z0-9\u00C0-\uFFFF]+|[^\sA-Za-z0-9]")


def _byte_map():
    bs = list(range(33, 127)) + list(range(161, 173)) + list(range(174, 256))
    cs, n = bs[:], 0
    for b in range(256):
        if b not in bs:
            bs.append(b)
            cs.append(256 + n)
            n += 1
    return {b: chr(c) for b, c in zip(bs, cs)}


class RobertaTokenizer:
    def __init__(self, folder):
        with open(os.path.join(folder, "vocab.json"), encoding="utf-8") as f:
            self.vocab = json.load(f)
        with open(os.path.join(folder, "merges.txt"), encoding="utf-8") as f:
            merges = [tuple(l.split()) for l in f.read().split("\n")
                      if l and not l.startswith("#version") and len(l.split()) == 2]
        self.rank = {m: i for i, m in enumerate(merges)}
        self.b2u = _byte_map()
        self.cache = {}
        self.cls_id = self.vocab["<s>"]
        self.sep_id = self.vocab["</s>"]
        self.pad_id = self.vocab["<pad>"]
        self.unk_id = self.vocab["<unk>"]
        self.mask_id = self.vocab["<mask>"]

    def _bpe(self, tok):
        if tok in self.cache:
            return self.cache[tok]
        parts = list(tok)
        while len(parts) > 1:
            pairs = set(zip(parts, parts[1:]))
            best = min(pairs, key=lambda p: self.rank.get(p, 1e9))
            if best not in self.rank:
                break
            out, i = [], 0
            while i < len(parts):
                if i < len(parts) - 1 and (parts[i], parts[i + 1]) == best:
                    out.append(parts[i] + parts[i + 1])
                    i += 2
                else:
                    out.append(parts[i])
                    i += 1
            parts = out
        self.cache[tok] = parts
        return parts

    def encode_word(self, word):
        """One whitespace-separated word, preceded by a space (so 'Ġword')."""
        ids = []
        for j, chunk in enumerate(_SPLIT.findall(word)):
            s = (" " if j == 0 else "") + chunk
            mapped = "".join(self.b2u[b] for b in s.encode("utf-8"))
            ids += [self.vocab.get(p, self.unk_id) for p in self._bpe(mapped)]
        return ids

    def encode_words(self, words):
        out = []
        for w in words:
            out += self.encode_word(w)
        return out

    def word_id(self, word):
        """Id of ' word' if it is ONE token, else None."""
        return self.vocab.get("\u0120" + word)