"""TQQQ 신호판(SPX ±2.5% V2) 40년 백테스트 — tq40.json(나스닥100 3배 환산 TQQQ·S&P500) + bt_data.json(SPY·QQQ 수정종가).

규칙 (신호판과 동일, 신호일 종가 체결):
- SPX 종가 > 200일선×1.025 → SGOV로 TQQQ 3분할 매수 (3거래일)
- 사이클 TQQQ 최고 수익률 +10/25/50% → TQQQ 잔고 10% SPYM, +100/200/400/800%… → 50% SPYM (각 1회)
- TQQQ 사이클 고점 대비 −25% → TQQQ 50% SPYM, 고점을 그 가격으로 리셋 (반복)
- SPX 종가 < 200일선×0.975 → 전량 SGOV
SPYM = 2010년부터 SPY 수정종가(배당 포함), 그 전은 S&P500 지수(배당 제외). SGOV = 연방기금금리(DFF) 일할.
세후: 해외주식 양도세 22%를 해마다 실현손익(손익 통산, 기본공제 무시)에 매김.
"""
import json
from datetime import date, datetime, timezone

SMALL = [10, 25, 50]
BIG = [100 * 2 ** k for k in range(12)]


def load(tq40="tq40.json", bt="bt_data.json"):
    j = json.load(open(tq40)); B = json.load(open(bt))["adj"]
    d = j["d"]; N = len(d); si = d.index(j["start"])
    T = [j["syn"][i] if i < si or j["real"][i] is None else j["real"][i] for i in range(N)]
    m = lambda s: {datetime.fromtimestamp(r[0], timezone.utc).date().isoformat(): r[1] for r in B[s]}
    spy, qqq = m("SPY"), m("QQQ")
    spx, ndx = j["spx"], j["ndx"]
    SP, Q = [1.0], [1.0]
    for i in range(1, N):
        a, b = d[i - 1], d[i]
        SP.append(SP[-1] * (spy[b] / spy[a] if a in spy and b in spy else spx[i] / spx[i - 1]))
        Q.append(Q[-1] * (qqq[b] / qqq[a] if a in qqq and b in qqq else ndx[i] / ndx[i - 1]))
    ma, s = [None] * N, 0.0
    for i in range(N):
        s += spx[i]
        if i >= 200: s -= spx[i - 200]
        if i >= 199: ma[i] = s / 200
    return dict(d=d, dd=[date.fromisoformat(x) for x in d], T=T, SP=SP, Q=Q, spx=spx, ma=ma, dff=j["dff"], start=j["start"])


def sim(D, a, b, band=0.025, tax=False, lag=0):
    """lag=0: 신호일 종가 체결, lag=1: 다음 거래일 종가 체결."""
    d, dd, T, SP, spx, ma, dff = D["d"], D["dd"], D["T"], D["SP"], D["spx"], D["ma"], D["dff"]
    P = {"cash": 1.0, "tq": 0.0, "sp": 0.0, "btq": 0.0, "bsp": 0.0}
    state, left, ent, pk, mx, hs, hb = "OUT", 0, 0, 0, 0, set(), set()
    yr, yg, cur, n, q = d[a][:4], [0.0], [], 0, []

    def do(act):
        if act[0] == "sell":
            f = act[1]; x = P["tq"] * f; yg[0] += x - P["btq"] * f
            P["btq"] *= 1 - f; P["tq"] -= x; P["sp"] += x; P["bsp"] += x
        elif act[0] == "buy":
            x = P["cash"] / act[1]; P["cash"] -= x; P["tq"] += x; P["btq"] += x
        else:
            yg[0] += P["tq"] - P["btq"] + P["sp"] - P["bsp"]
            P["cash"] += P["tq"] + P["sp"]; P["tq"] = P["sp"] = P["btq"] = P["bsp"] = 0.0

    for i in range(a, b + 1):
        if i > a:
            k = (dd[i] - dd[i - 1]).days
            P["tq"] *= T[i] / T[i - 1]; P["sp"] *= SP[i] / SP[i - 1]; P["cash"] *= 1 + dff[i - 1] / 100 / 360 * k
            if d[i][:4] != yr:
                if tax and yg[0] > 0:
                    t = yg[0] * 0.22
                    if P["cash"] >= t: P["cash"] -= t
                    else:
                        r = 1 - (t - P["cash"]) / (P["tq"] + P["sp"]); P["cash"] = 0
                        for kk in ("tq", "sp", "btq", "bsp"): P[kk] *= r
                yr, yg[0] = d[i][:4], 0.0
        for act in q: do(act)
        q = []
        if ma[i] is not None:
            up, lo = ma[i] * (1 + band), ma[i] * (1 - band)
            if state == "OUT" and spx[i] > up:
                state, ent, pk, mx, hs, hb, left = "IN", T[i], T[i], 0, set(), set(), 3; n += 1
            elif state == "IN":
                pk = max(pk, T[i]); mx = max(mx, T[i] / ent - 1)
                for x in SMALL:
                    if x not in hs and mx * 100 >= x: hs.add(x); q.append(("sell", 0.10))
                for x in BIG:
                    if x not in hb and mx * 100 >= x: hb.add(x); q.append(("sell", 0.50))
                if T[i] <= pk * 0.75: q.append(("sell", 0.50)); pk = T[i]
                if spx[i] < lo: state, left, q = "OUT", 0, [("exit",)]
            if state == "IN" and left > 0: q.append(("buy", left)); left -= 1
        if not lag:
            for act in q: do(act)
            q = []
        cur.append(P["cash"] + P["tq"] + P["sp"])
    if tax and yg[0] > 0: cur[-1] -= yg[0] * 0.22
    return cur, n


def stats(D, cur, a, b):
    v, pk, mdd, w = cur[-1], cur[0], 0.0, None
    for k, x in enumerate(cur):
        if x > pk: pk = x; p0 = k
        if x / pk - 1 < mdd: mdd = x / pk - 1
    y = (D["dd"][b] - D["dd"][a]).days / 365.25
    return round((v ** (1 / y) - 1) * 100, 1), round(mdd * 100, 1), round(v, 1)


def drawdowns(D, cur, a, top=3):
    """서로 겹치지 않는 낙폭 상위 구간 (고점일·저점일·낙폭)."""
    out, pk, w = [], 0, None
    for k, x in enumerate(cur):
        if x >= cur[pk]:
            if w: out.append(w)
            pk, w = k, None
        else:
            r = x / cur[pk] - 1
            if not w or r < w[0]: w = (r, D["d"][a + pk], D["d"][a + k])
    if w: out.append(w)
    return [{"dd": round(r * 100, 1), "peak": p, "low": l} for r, p, l in sorted(out)[:top]]


def run(tq40="tq40.json", bt="bt_data.json"):
    D = load(tq40, bt); d, N = D["d"], len(D["d"])
    idx = lambda s: next(i for i, x in enumerate(d) if x >= s)
    b = N - 1; last = D["dd"][b]
    ten = date(last.year - 10, last.month, last.day).isoformat()
    periods = [("40년", "1986-10-01"), ("2000년~ (닷컴 붕괴 포함)", "2000-01-03"), ("2010년~ (실제 TQQQ)", D["start"]), ("최근 10년", ten)]
    rows = []
    for name, s0 in periods:
        a = idx(s0)
        cur, n = sim(D, a, b); curt, _ = sim(D, a, b, tax=True)
        hold = lambda A: [A[i] / A[a] for i in range(a, b + 1)]
        c, m, x = stats(D, cur, a, b)
        rows.append({"name": name, "from": d[a], "cagr": c, "mdd": m, "x": x, "tax": stats(D, curt, a, b)[0],
                     "cyc": round(n / ((last - D["dd"][a]).days / 365.25), 2),
                     "tqqq": stats(D, hold(D["T"], ), a, b)[:2], "qqq": stats(D, hold(D["Q"]), a, b)[:2], "spx": stats(D, hold(D["SP"]), a, b)[:2]})
    a = idx("1986-10-01"); cur, _ = sim(D, a, b)
    nxt = stats(D, sim(D, a, b, lag=1)[0], a, b)[:2]
    # 월말 곡선 (차트용)
    ch = {"d": [], "v2": [], "tqqq": [], "qqq": [], "spx": []}
    for i in range(a, b + 1):
        if i == b or d[i + 1][:7] != d[i][:7]:
            ch["d"].append(d[i][:7]); ch["v2"].append(round(cur[i - a], 4))
            for k, A in (("tqqq", D["T"]), ("qqq", D["Q"]), ("spx", D["SP"])):
                ch[k].append(round(A[i] / A[a], 6))
    return {"asof": d[b], "rows": rows, "next_day": nxt, "dd": drawdowns(D, cur, a), "chart": ch}


if __name__ == "__main__":
    r = run()
    for x in r["rows"]: print(x)
    print(r["dd"], r["next_day"])
