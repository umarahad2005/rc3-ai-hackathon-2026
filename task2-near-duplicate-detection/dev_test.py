import sys, pandas as pd, time
from lsh_core import find_similar_pairs
dev = pd.read_csv("../lsh_task/dev_docs.csv", dtype=str, keep_default_na=False)
truth = pd.read_csv("../lsh_task/dev_ground_truth.csv", dtype=str)
T = set(zip(truth.id1, truth.id2))
for b, r in [(20,5),(25,4),(16,6)]:
    tm, st = {}, {}
    P = find_similar_pairs(dev.id.tolist(), dev.text.tolist(), 0.8, b, r, tm, st)
    tp = len(P & T); prec = tp/len(P); rec = tp/len(T)
    print(f"b={b} r={r} P={prec:.4f} R={rec:.4f} found={len(P)} miss={len(T-P)} wrong={len(P-T)} {st} " + " ".join(f"{k}={v:.2f}" for k,v in tm.items()))
