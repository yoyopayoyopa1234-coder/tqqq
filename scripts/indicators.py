"""TradingView와 같은 방식의 지표 계산 (pandas 없이)."""
import math

def sma(a, n):
    out = [None] * len(a)
    for i in range(n - 1, len(a)):
        out[i] = sum(a[i - n + 1:i + 1]) / n
    return out

def stdev(a, n):  # TradingView ta.stdev = 모표준편차
    out = [None] * len(a)
    for i in range(n - 1, len(a)):
        w = a[i - n + 1:i + 1]; m = sum(w) / n
        out[i] = math.sqrt(sum((x - m) ** 2 for x in w) / n)
    return out

def highest(a, n):
    return [max(a[max(0, i - n + 1):i + 1]) for i in range(len(a))]

def bb(c, n=20, k=2):
    m, s = sma(c, n), stdev(c, n)
    up = [None if v is None else v + k * s[i] for i, v in enumerate(m)]
    lo = [None if v is None else v - k * s[i] for i, v in enumerate(m)]
    return m, up, lo

def rsi(c, n=14):
    out = [None] * len(c); g = l = 0.0
    for i in range(1, len(c)):
        d = c[i] - c[i - 1]; u, w = max(d, 0), max(-d, 0)
        if i <= n:
            g += u; l += w
            if i < n: continue
            g /= n; l /= n
        else:
            g = (g * (n - 1) + u) / n; l = (l * (n - 1) + w) / n
        out[i] = 100.0 if l == 0 else 100 - 100 / (1 + g / l)
    return out

def vixfix(h, l, c, pd=22, bbl=20, mult=2, lb=50, ph=0.85):
    hc = highest(c, pd)
    w = [(hc[i] - l[i]) / hc[i] * 100 for i in range(len(c))]
    m, s = sma(w, bbl), stdev(w, bbl)
    up = [None if v is None else v + mult * s[i] for i, v in enumerate(m)]
    rh = [v * ph for v in highest(w, lb)]
    sig = [w[i] >= rh[i] or (up[i] is not None and w[i] >= up[i]) for i in range(len(w))]
    return w, up, rh, sig
