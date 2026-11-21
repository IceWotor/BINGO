import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORPUS_DIR = os.path.join(ROOT, "assets", "corpus")
ROBERTA_DIR = os.path.join(ROOT, "assets", "model", "roberta-base")