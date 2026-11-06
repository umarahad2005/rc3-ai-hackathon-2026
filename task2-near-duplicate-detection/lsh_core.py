"""Task 2 core: shingles -> MinHash -> LSH banding -> exact Jaccard verification.

Only the standard library and NumPy are used.
"""
import time
import numpy as np

K_SHINGLE = 5
NUM_BANDS = 20      # b
ROWS = 5            # r   -> k = b * r MinHash values per document
SEED = 12345
MASK64 = (1 << 64) - 1


def _rotl(x, k):
    """64-bit rotate-left on a uint64 array."""
    if k == 0:
        return x
    return (x << np.uint64(k)) | (x >> np.uint64(64 - k))


def build_shingles(texts, seed=SEED):
    """Return (H, offsets): H is the concatenation of every document's sorted,
    unique 64-bit shingle hashes; document i owns H[offsets[i]:offsets[i+1]]."""
    rng = np.random.default_rng(seed)
    vocab = {}
    word_ids = []
    lengths = np.empty(len(texts), dtype=np.int64)
    for i, t in enumerate(texts):                       # word -> integer id
        ids = [vocab.setdefault(w, len(vocab)) for w in t.split()]
        word_ids.append(ids)
        lengths[i] = len(ids)
    # random 64-bit value per distinct word (tabulation hashing)
    table = rng.integers(0, 2**63, size=len(vocab) + 1, dtype=np.uint64) * np.uint64(2) + np.uint64(1)
    allw = np.fromiter((w for ids in word_ids for w in ids), dtype=np.int64, count=int(lengths.sum()))
    del word_ids
    tw = table[allw]
    del allw
    starts = np.zeros(len(texts) + 1, dtype=np.int64)
    np.cumsum(lengths, out=starts[1:])

    pieces, sizes = [], np.empty(len(texts), dtype=np.int64)
    # 5-gram hash = XOR of the word values rotated by their position in the gram
    n_all = len(tw)
    if n_all >= K_SHINGLE:
        g = tw[: n_all - K_SHINGLE + 1].copy()
        for j in range(1, K_SHINGLE):
            g ^= _rotl(tw[j: n_all - K_SHINGLE + 1 + j], 13 * j)
    else:
        g = np.empty(0, dtype=np.uint64)
    short_salt = np.uint64(0x9E3779B97F4A7C15)
    for i in range(len(texts)):
        s, L = starts[i], lengths[i]
        if L >= K_SHINGLE:
            h = np.unique(g[s: s + L - K_SHINGLE + 1])   # grams fully inside doc i
        else:
            # fewer than 5 words: one shingle = the whole word sequence
            v = np.uint64((int(L) * 0x9E3779B97F4A7C15) & MASK64)
            for j in range(L):
                v ^= _rotl(tw[s + j: s + j + 1], (7 * j + 3) % 64)[0]
            h = np.array([v ^ short_salt], dtype=np.uint64)
        pieces.append(h)
        sizes[i] = len(h)
    offsets = np.zeros(len(texts) + 1, dtype=np.int64)
    np.cumsum(sizes, out=offsets[1:])
    return np.concatenate(pieces), offsets


def minhash(H, offsets, k, seed=SEED):
    """k MinHash values per document using h(x) = a*x + b (mod 2^64)."""
    rng = np.random.default_rng(seed + 1)
    a = rng.integers(0, 2**63, size=k, dtype=np.uint64) * np.uint64(2) + np.uint64(1)
    b = rng.integers(0, 2**63, size=k, dtype=np.uint64)
    sig = np.empty((len(offsets) - 1, k), dtype=np.uint64)
    starts = offsets[:-1]
    for j in range(k):
        v = H * a[j]
        v += b[j]
        sig[:, j] = np.minimum.reduceat(v, starts)
    return sig


def lsh_candidates(sig, bands, rows, seed=SEED):
    """Pairs (i, j), i < j, that agree on all rows of at least one band."""
    n = sig.shape[0]
    rng = np.random.default_rng(seed + 2)
    mult = rng.integers(0, 2**63, size=rows, dtype=np.uint64) * np.uint64(2) + np.uint64(1)
    cand = []
    biggest = 0
    for bi in range(bands):
        block = sig[:, bi * rows:(bi + 1) * rows]
        key = (block * mult).sum(axis=1, dtype=np.uint64)  # band -> one bucket key
        order = np.argsort(key, kind="stable")
        ks = key[order]
        brk = np.flatnonzero(np.diff(ks)) + 1
        bstart = np.concatenate(([0], brk))
        bend = np.concatenate((brk, [n]))
        sz = bend - bstart
        biggest = max(biggest, int(sz.max()))
        for size in np.unique(sz[sz >= 2]):                 # vectorised per bucket size
            st = bstart[sz == size]
            members = order[st[:, None] + np.arange(size)]  # (#buckets, size)
            iu, ju = np.triu_indices(size, 1)
            a_ = members[:, iu].ravel()
            b_ = members[:, ju].ravel()
            cand.append(np.minimum(a_, b_) * n + np.maximum(a_, b_))
    if not cand:
        return np.empty((0, 2), dtype=np.int64), biggest
    codes = np.unique(np.concatenate(cand))
    return np.stack((codes // n, codes % n), axis=1), biggest


def verify(pairs, H, offsets, threshold):
    """Exact Jaccard on the candidate pairs. Returns (kept pairs, their J)."""
    sizes = np.diff(offsets)
    si, sj = sizes[pairs[:, 0]], sizes[pairs[:, 1]]
    # size filter: J <= min/max, so min/max < threshold means J < threshold
    ok = np.minimum(si, sj) >= threshold * np.maximum(si, sj)
    pairs = pairs[ok]
    keep, js = [], []
    for i, j in pairs:
        a = H[offsets[i]:offsets[i + 1]]
        b = H[offsets[j]:offsets[j + 1]]
        inter = len(np.intersect1d(a, b, assume_unique=True))
        jac = inter / (len(a) + len(b) - inter)
        if jac >= threshold:
            keep.append((i, j))
            js.append(jac)
    return keep, js


def find_similar_pairs(ids, texts, threshold=0.8, bands=NUM_BANDS, rows=ROWS,
                       timings=None, stats=None):
    t0 = time.perf_counter()
    H, offsets = build_shingles(texts)
    t1 = time.perf_counter()
    sig = minhash(H, offsets, bands * rows)
    t2 = time.perf_counter()
    cand, biggest = lsh_candidates(sig, bands, rows)
    t3 = time.perf_counter()
    keep, _ = verify(cand, H, offsets, threshold)
    t4 = time.perf_counter()
    out = set()
    for i, j in keep:
        a, b = ids[i], ids[j]
        out.add((a, b) if a < b else (b, a))
    if timings is not None:
        timings.update(shingle=t1 - t0, minhash=t2 - t1, lsh=t3 - t2, verify=t4 - t3, total=t4 - t0)
    if stats is not None:
        stats.update(n_shingles=len(H), n_candidates=len(cand), biggest_bucket=biggest, n_pairs=len(out))
    return out
