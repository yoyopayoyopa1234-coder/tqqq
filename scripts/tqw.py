"""TQQQ 비중매매법(52주 고점 대비 하락 구간별 QQQ·QLD·TQQQ 비중) 분석 → tqw.json

규칙(원안): 나스닥100 종가가 52주(252거래일) 최고 종가보다 몇 % 아래인가로 비중을 정한다. 하락·회복 같은 기준.
   0~−5% QQQ 100 / −5% QQQ 90·QLD 10 / −10% 70·30 / −15% 40·60 / −20% QLD 100 / −25% QLD 50·TQQQ 50 / −30% TQQQ 100
매매: 그날 종가로 구간이 바뀌면 그 종가에 목표 비중으로 맞춤(구간이 그대로면 손대지 않음).
개선안: 같은 사다리 + S&P500 200일선 ±2.5% 띠(반반형·절충형과 같은 기준) 아래로 깨지면 SGOV(현금), 위로 회복하면 다시 사다리.
비교: QQQ·QLD·TQQQ 보유, 반반형·절충형(simple_check.py 와 같은 엔진).
"""
import json, os, sys, bisect, statistics
from datetime import date
sys.path.insert(0, os.path.dirname(__file__))
os.chdir(os.path.join(os.path.dirname(__file__), ".."))
from simple_check import load, build_returns, mk_levels, engine, STRATS

LAD = [(1, 0, 0), (.9, .1, 0), (.7, .3, 0), (.4, .6, 0), (0, 1, 0), (0, .5, .5), (0, 0, 1)]
LAB = ["QQQ 100%", "QQQ 90% / QLD 10%", "QQQ 70% / QLD 30%", "QQQ 40% / QLD 60%", "QLD 100%", "QLD 50% / TQQQ 50%", "TQQQ 100%"]
LEV = [1.0, 1.1, 1.3, 1.6, 2.0, 2.5, 3.0]
PERIODS = [("2000 닷컴", "2000-03-10", "2003-03-11"), ("2008 리먼", "2007-10-31", "2009-12-31"), ("2020 코로나", "2020-02-19", "2020-12-31"),
           ("2022 긴축", "2021-11-19", "2023-12-29"), ("2010~ (TQQQ 상장 뒤)", "2010-02-11", None)]


def band(dd, step=0.05):
    return min(int((-dd + 1e-12) // step), 6)


def main():
    J, B, Q, TQ = load(); D = build_returns(J, B)
    d, N, nd, ret, hi, sp, sp200, dt = D["d"], D["N"], D["nd"], D["ret"], D["hi"], D["sp"], D["sp200"], D["dt"]
    ath = []; m = 0
    for v in nd: m = max(m, v); ath.append(m)
    a0 = next(i for i, x in enumerate(d) if x >= "1986-10-01"); b0 = N - 1

    def ladder(a, b, step=0.05, basis="52", filt=False, bnd=0.025, cap=6):
        H = hi if basis == "52" else ath
        inm = True

        def target(i):
            nonlocal inm
            if filt:
                if inm and sp[i] < sp200[i] * (1 - bnd): inm = False
                elif not inm and sp[i] > sp200[i] * (1 + bnd): inm = True
                if not inm: return -1
            return min(band(nd[i] / H[i] - 1, step), cap)

        def wts(t):
            if t < 0: return {"C": 1.0}
            q, l, x = LAD[t]; return {k: w for k, w in (("Q", q), ("L", l), ("T", x)) if w}
        cur = target(a); h = wts(cur); cv = [1.0]; st = [cur]; sw = 0
        for i in range(a + 1, b + 1):
            v = 0.0
            for k in h: h[k] *= 1 + ret[k][i]; v += h[k]
            t = target(i)
            if t != cur: sw += 1; cur = t; h = {k: v * w for k, w in wts(t).items()}
            cv.append(v); st.append(cur)
        return cv, st, sw

    def hold(k, a, b):
        cv = [1.0]
        for i in range(a + 1, b + 1): cv.append(cv[-1] * (1 + ret[k][i]))
        return cv

    def strat(nm, a, b):
        cfg, W, ts, _ = STRATS[nm]; lv = mk_levels(D, cfg); return engine(D, lv, W, a, b, ts)["cv"]

    def stats(cv, a, b):
        y = (dt[b] - dt[a]).days / 365.25; pk = cv[0]; pki = 0; mdd = 0; w = None; best = (0, None, None)
        for j, v in enumerate(cv):
            if v >= pk:
                du = (dt[a + j] - dt[a + pki]).days
                if du > best[0]: best = (du, d[a + pki], d[a + j])
                pk = v; pki = j
            elif v / pk - 1 < mdd: mdd = v / pk - 1; w = (d[a + pki], d[a + j])
        du = (dt[b] - dt[a + pki]).days
        if du > best[0]: best = (du, d[a + pki], None)
        return dict(c=round((cv[-1] ** (1 / y) - 1) * 100, 2), m=round(mdd * 100, 1), x=round(cv[-1], 2), mw=w, uw=round(best[0] / 365.25, 1), uww=best[1:])

    ROWS = [("원안", lambda a, b: ladder(a, b)[0]),
            ("개선안", lambda a, b: ladder(a, b, filt=True)[0]),
            ("원안 · 사상 최고가 기준", lambda a, b: ladder(a, b, basis="ath")[0]),
            ("원안 · 2배 상한(TQQQ 대신 QLD)", lambda a, b: ladder(a, b, cap=4)[0]),
            ("QQQ 보유", lambda a, b: hold("Q", a, b)),
            ("QLD 보유", lambda a, b: hold("L", a, b)),
            ("TQQQ 보유", lambda a, b: hold("T", a, b)),
            ("반반형", lambda a, b: strat("반반형", a, b)),
            ("절충형", lambda a, b: strat("절충형", a, b))]
    full = []; post = []
    a10 = bisect.bisect_left(d, "2010-02-11")
    for nm, f in ROWS:
        full.append(dict(n=nm, **stats(f(a0, b0), a0, b0)))
        post.append(dict(n=nm, **stats(f(a10, b0), a10, b0)))
    _, st0, sw0 = ladder(a0, b0); _, st1, sw1 = ladder(a0, b0, filt=True)
    yy = (dt[b0] - dt[a0]).days / 365.25
    full[0]["sw"] = round(sw0 / yy, 1); full[1]["sw"] = round(sw1 / yy, 1)
    share = [round(sum(1 for s in st0 if s == k) / len(st0) * 100, 1) for k in range(7)]
    share1 = [round(sum(1 for s in st1 if s == k) / len(st1) * 100, 1) for k in range(-1, 7)]

    # 위기별
    crises = []
    for nm, s, e in PERIODS:
        a = bisect.bisect_left(d, s); b = b0 if e is None else bisect.bisect_right(d, e) - 1
        row = dict(n=nm, a=d[a], b=d[b], r={})
        for rn, f in ROWS:
            if rn.startswith("원안 ·") or rn == "QLD 보유": continue
            cv = f(a, b); pk = 1; mdd = 0
            for v in cv: pk = max(pk, v); mdd = min(mdd, v / pk - 1)
            row["r"][rn] = [round((cv[-1] - 1) * 100, 1), round(mdd * 100, 1)]
        crises.append(row)

    # 2000년 따라가 보기: 원안이 구간을 바꾼 날들 (2000-03 ~ 2002-10)
    a = bisect.bisect_left(d, "2000-03-10"); b = bisect.bisect_left(d, "2002-10-10")
    cv, st, _ = ladder(a0, b0); walk = []
    for i in range(a, b + 1):
        j = i - a0
        if st[j] != st[j - 1]:
            walk.append([d[i], round(nd[i]), round((nd[i] / hi[i] - 1) * 100, 1), st[j], round(cv[j] / cv[a - a0] * 100, 1)])

    ib = bisect.bisect_left(d, "2002-10-09"); walk_end = [d[ib], round(nd[ib]), round(cv[ib - a0] / cv[a - a0] * 100, 2)]
    # 과최적화 점검: 단계 폭 × 기준(52주/사상최고) × (필터 띠)
    nb0 = []
    for step in (0.04, 0.05, 0.06):
        for basis in ("52", "ath"):
            for cap in (6, 5):
                c = stats(ladder(a0, b0, step=step, basis=basis, cap=cap)[0], a0, b0); nb0.append([step, basis, cap, c["c"], c["m"]])
    nb1 = []
    for step in (0.04, 0.05, 0.06):
        for bnd in (0.02, 0.025, 0.03):
            for basis in ("52", "ath"):
                cv = ladder(a0, b0, step=step, basis=basis, filt=True, bnd=bnd)[0]; c = stats(cv, a0, b0); c10 = stats(ladder(a10, b0, step=step, basis=basis, filt=True, bnd=bnd)[0], a10, b0)
                nb1.append([step, bnd, basis, c["c"], c["m"], c10["c"], c10["m"]])

    # 주간 곡선 (로그 차트용)
    cvs = {nm: f(a0, b0) for nm, f in ROWS if nm in ("원안", "개선안", "QQQ 보유", "반반형")}
    weekly = []
    for j in range(0, b0 - a0 + 1, 5):
        i = a0 + j; weekly.append([d[i], round(nd[i]), st0[j], st1[j]] + [round(cvs[k][j], 4) for k in ("원안", "개선안", "QQQ 보유", "반반형")])
    j = b0 - a0; i = b0
    if weekly[-1][0] != d[i]: weekly.append([d[i], round(nd[i]), st0[j], st1[j]] + [round(cvs[k][j], 4) for k in ("원안", "개선안", "QQQ 보유", "반반형")])

    # 오늘
    dd = nd[-1] / hi[-1] - 1; k = band(dd); spm = sp[-1] / sp200[-1] - 1
    hi_i = max(range(N - 252, N), key=lambda i: nd[i])
    lines = [round(hi[-1] * (1 - 0.05 * n)) for n in range(1, 7)]
    today = dict(d=d[-1], ndx=round(nd[-1], 2), hi=round(hi[-1], 2), hi_d=d[hi_i], dd=round(dd * 100, 2), band=k, lab=LAB[k], lev=LEV[k], lines=lines,
                 sp=round(sp[-1], 2), sp200=round(sp200[-1], 2), spm=round(spm * 100, 2), filt_in=st1[-1] >= 0, band1=st1[-1],
                 sp_out=round(sp200[-1] * 0.975, 2), sp_in=round(sp200[-1] * 1.025, 2))
    out = dict(ts=int(__import__("time").time()), lad=LAB, lev=LEV, today=today, full=full, post=post, sw=[full[0].get("sw"), full[1].get("sw")],
               share=share, share1=share1, crises=crises, walk=walk, walk_end=walk_end, nb0=nb0, nb1=nb1, weekly=weekly, cols=["원안", "개선안", "QQQ 보유", "반반형"])
    json.dump(out, open("tqw.json", "w"), ensure_ascii=False, separators=(",", ":"))
    print("TQQQ 비중매매", d[-1], f"52주 고점 대비 {dd*100:.2f}% → {LAB[k]}", "| 40년 원안", full[0]["c"], full[0]["m"], "개선안", full[1]["c"], full[1]["m"])


if __name__ == "__main__":
    main()
