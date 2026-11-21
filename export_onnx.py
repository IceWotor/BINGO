"""Run once on the desktop: python export_onnx.py"""
import json
import os

import torch
from transformers import AutoModelForMaskedLM, AutoTokenizer

NAME = "roberta-base"
OUT = os.path.join("assets", "model", NAME)
os.makedirs(OUT, exist_ok=True)


class Wrapper(torch.nn.Module):
    """(input_ids, attention_mask, positions) -> logits only at `positions`."""
    def __init__(self, m):
        super().__init__()
        self.m = m

    def forward(self, input_ids, attention_mask, positions):
        enc = self.m.roberta(input_ids=input_ids,
                             attention_mask=attention_mask).last_hidden_state
        idx = positions.unsqueeze(-1).expand(-1, -1, enc.size(-1))
        return self.m.lm_head(torch.gather(enc, 1, idx))


# ---- tokenizer files the phone needs: vocab.json + merges.txt
tok = AutoTokenizer.from_pretrained(NAME)
tok.save_pretrained(OUT)
with open(os.path.join(OUT, "tokenizer.json"), encoding="utf-8") as f:
    tj = json.load(f)["model"]
with open(os.path.join(OUT, "vocab.json"), "w", encoding="utf-8") as f:
    json.dump(tj["vocab"], f, ensure_ascii=False)
with open(os.path.join(OUT, "merges.txt"), "w", encoding="utf-8") as f:
    f.write("#version: 0.2\n")
    for m in tj["merges"]:
        f.write((m if isinstance(m, str) else " ".join(m)) + "\n")
print("tokenizer files written")

# ---- model
model = AutoModelForMaskedLM.from_pretrained(NAME).eval()
ids = torch.tensor([[0, 100, 50264, 200, 2]])
att = torch.ones_like(ids)
pos = torch.tensor([[2]])
fp32 = os.path.join(OUT, "model.onnx")
torch.onnx.export(
    Wrapper(model), (ids, att, pos), fp32,
    input_names=["input_ids", "attention_mask", "positions"],
    output_names=["logits"],
    dynamic_axes={"input_ids": {0: "b", 1: "t"}, "attention_mask": {0: "b", 1: "t"},
                  "positions": {0: "b", 1: "m"}, "logits": {0: "b", 1: "m"}},
    opset_version=14, dynamo=False)

# ---- int8 copy (about 4x smaller) for the phone
from onnxruntime.quantization import quantize_dynamic, QuantType
quantize_dynamic(fp32, os.path.join(OUT, "model.int8.onnx"),
                 weight_type=QuantType.QInt8)
print("done ->", OUT)