import pandas as pd, time, tracemalloc
from lsh_core import find_similar_pairs
t=time.perf_counter()
docs = pd.read_csv("../lsh_task/docs.csv", dtype=str, keep_default_na=False)
print("load", round(time.perf_counter()-t,1))
tm, st = {}, {}
P = find_similar_pairs(docs.id.tolist(), docs.text.tolist(), 0.8, 20, 5, tm, st)
print(st); print({k: round(v,1) for k,v in tm.items()})
