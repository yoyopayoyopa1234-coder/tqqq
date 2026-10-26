"""TQQQ 40년 환산 주가 → tq40.json (하루 한 번).
나스닥100(^NDX) 일봉 × 3 − 조달금리(DFF×2) − 운용보수(ER 0.95%) − 스왑 스프레드(SS 1%×2).
아기티큐 공개 수식과 같은 방식.

- d / syn / real / ndx / dff : 날짜별 환산 종가(배당 반영 실제가에 맞춤), 실제 수정종가, 나스닥100 종가, 기준금리
- ohlc.TQQQ_1d/1wk/1mo : 1985~2010-02-10은 환산 OHLC, 2010-02-11부터 야후 실제 OHLC (분석 페이지 차트용)
- ohlc.NDX_1mo : 나스닥100 월봉 (QQQ 상장 전 월봉 RSI 계산용)
"""
import csv, io, json, os, sys, time
from datetime import datetime, timezone, date, timedelta
sys.path.insert(0, os.path.dirname(__file__))
from yahoo_data import get

FN = "tq40.json"; ER = 0.0095; SS = 0.01

def day(t):
    return datetime.fromtimestamp(t, timezone.utc).date()

def aggregate(bars, keyf):
    out = []
    for b in bars:
        k = keyf(day(b[0]))
        if out and out[-1][0] == k:
            a = out[-1][1]; a[2] = max(a[2], b[2]); a[3] = min(a[3], b[3]); a[4] = b[4]
        else:
            out.append((k, list(b)))
    return out

def ohlc_since(sym, iv, p1=1262304000):
    """야후 range=max는 일·주봉을 듬성듬성 보내므로 기간을 직접 지정해서 받음."""
    j = json.loads(get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?period1={p1}&period2={int(time.time())}&interval={iv}"))
    r = j["chart"]["result"][0]; q = r["indicators"]["quote"][0]; out = []
    for i, t in enumerate(r["timestamp"]):
        c = q["close"][i]
        if c is None: continue
        o, h, l = q["open"][i] or c, q["high"][i] or c, q["low"][i] or c
        out.append([t, round(o, 4), round(max(h, o, c), 4), round(min(l, o, c), 4), round(c, 4)])
    return out

def spx_series(days):
    """S&P 500(^GSPC) 종가를 나스닥100 거래일에 맞춤 (TQQQ 신호판 40년 백테스트용)."""
    try:
        j = json.loads(get(f"https://query1.finance.yahoo.com/v8/finance/chart/%5EGSPC?period1=489024000&period2={int(time.time())}&interval=1d"))
        r = j["chart"]["result"][0]
        m = {day(t): c for t, c in zip(r["timestamp"], r["indicators"]["quote"][0]["close"]) if c}
    except Exception as e:
        print("GSPC 실패", e); return None
    return fx_series(days, m)

def fx_series(days, fx):
    """원/달러 환율(FRED DEXKOUS)을 거래일에 맞춤 — 빈 날은 직전 값, 시작 전은 None."""
    out, last, ks, k = [], None, sorted(fx), 0
    for dd in days:
        while k < len(ks) and ks[k] <= dd:
            last = fx[ks[k]]; k += 1
        out.append(last)
    return out

def main():
    try:
        old = json.load(open(FN))
        if time.time() - old.get("ts", 0) < 20 * 3600 and len(old.get("ohlc", {}).get("TQQQ_1d", [])) > 9000 and old.get("krw") and old.get("spx"):
            print("tq40 최신 — 건너뜀"); return
    except Exception:
        pass
    j = json.loads(get(f"https://query1.finance.yahoo.com/v8/finance/chart/%5ENDX?period1=489024000&period2={int(time.time())}&interval=1d"))
    r = j["chart"]["result"][0]; q = r["indicators"]["quote"][0]
    ndx = []
    for i, t in enumerate(r["timestamp"]):
        c = q["close"][i]
        if not c: continue
        o, h, l = q["open"][i] or c, q["high"][i] or c, q["low"][i] or c
        ndx.append((t, o, max(h, o, c), min(l, o, c), c))
    dff = {}
    for row in csv.reader(io.StringIO(get("https://fred.stlouisfed.org/graph/fredgraph.csv?id=DFF"))):
        try: dff[date.fromisoformat(row[0])] = float(row[1])
        except Exception: pass
    dk = sorted(dff)
    krw = {}
    try:
        for row in csv.reader(io.StringIO(get("https://fred.stlouisfed.org/graph/fredgraph.csv?id=DEXKOUS"))):
            try: krw[date.fromisoformat(row[0])] = float(row[1])
            except Exception: pass
    except Exception as e:
        print("DEXKOUS 실패", e)
    j = json.loads(get(f"https://query1.finance.yahoo.com/v8/finance/chart/TQQQ?period1=1262304000&period2={int(time.time())}&interval=1d&events=div,split"))
    r = j["chart"]["result"][0]
    adj = {day(t): a for t, a in zip(r["timestamp"], r["indicators"]["adjclose"][0]["adjclose"]) if a}
    real = {k: ohlc_since("TQQQ", k) for k in ("1d", "1wk", "1mo")}
    start = day(real["1d"][0][0])

    # 환산: 하루 수익률과 장중 비율(시가·고가·저가)을 3배로
    k = 0; rates = []; syn = [1.0]; bars = [[ndx[0][0], 1.0, 1.0, 1.0, 1.0]]
    for i in range(len(ndx)):
        d0 = day(ndx[i][0])
        while k + 1 < len(dk) and dk[k + 1] <= d0: k += 1
        rates.append(dff.get(d0, dff[dk[k]]))
        if i == 0: continue
        n = (d0 - day(ndx[i - 1][0])).days; rate = rates[i - 1] / 100
        cost = rate / 360 * n * 2 + ((1 + ER) ** (n / 365) - 1) + ((1 + SS) ** (n / 365) - 1) * 2
        pc, p = ndx[i - 1][4], syn[-1]
        lev = lambda x: p * max(0.01, 1 + (x / pc - 1) * 3 - cost)
        c = lev(ndx[i][4]); o = lev(ndx[i][1])
        h = max(lev(ndx[i][2]), o, c); l = min(lev(ndx[i][3]), o, c)
        syn.append(c); bars.append([ndx[i][0], o, h, l, c])
    si = next(i for i, b in enumerate(ndx) if day(b[0]) >= start)
    s_adj = adj[day(ndx[si][0])] / syn[si] if day(ndx[si][0]) in adj else adj[min(adj)] / syn[si]
    s_raw = real["1d"][0][4] / syn[si]
    sb = [[b[0]] + [round(v * s_raw, 6) for v in b[1:]] for b in bars[:si]]

    wk = lambda d: d - timedelta(days=d.weekday())
    mo = lambda d: (d.year, d.month)
    first_w, first_m = wk(day(real["1wk"][0][0])), mo(day(real["1mo"][0][0]))
    ohlc = {
        "TQQQ_1d": sb + real["1d"],
        "TQQQ_1wk": [b for kk, b in aggregate(sb, wk) if kk < first_w] + real["1wk"],
        "TQQQ_1mo": [b for kk, b in aggregate(sb, mo) if kk < first_m] + real["1mo"],
        "NDX_1mo": [[b[0], round(b[4], 2)] for kk, b in aggregate([list(x) for x in ndx], mo)],
    }
    out = {"ts": int(time.time()), "start": start.isoformat(), "er": ER, "ss": SS,
           "d": [day(x[0]).isoformat() for x in ndx],
           "syn": [round(v * s_adj, 6) for v in syn],
           "real": [round(adj[day(x[0])], 4) if day(x[0]) in adj else None for x in ndx],
           "ndx": [round(x[4], 2) for x in ndx],
           "dff": rates,
           "krw": fx_series([day(x[0]) for x in ndx], krw),
           "spx": spx_series([day(x[0]) for x in ndx]),
           "ohlc": ohlc}
    json.dump(out, open(FN, "w"), separators=(",", ":"))
    print("tq40", len(ndx), out["d"][0], out["d"][-1], {k: len(v) for k, v in ohlc.items()})

if __name__ == "__main__":
    main()
