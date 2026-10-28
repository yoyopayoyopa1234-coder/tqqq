"""간단지표 매매법 2차 검증 (15분마다 update.yml 에서 실행) → simple_check.json

simple.html 의 자바스크립트와 별개로, 같은 데이터 파일(tq40.json · bt_data.json · tqqq_data.json · tq.json)을 파이썬으로
다시 읽어 각 매매법의 오늘 신호와 40년 성적을 계산한다. 페이지는 이 파일을 읽어 자기 계산과 대조해 일치/불일치를 표시한다.
더불어 데이터 자체의 이상(파일 간 날짜 불일치 · 장중 미확정 봉 · 나스닥100/QQQ 비율 이상 · S&P500 값 불일치)과
신호가 바뀌기 직전인 경계 근처 상태를 찾아 경고한다. 세 번째 패키지 없이 표준 라이브러리만 쓴다.
"""
import json, time, statistics
from datetime import datetime, timezone, timedelta, date

KST = timezone(timedelta(hours=9))
OUT = "simple_check.json"

def load():
    J = json.load(open("tq40.json")); B = json.load(open("bt_data.json"))["adj"]
    Q = json.load(open("tqqq_data.json")); TQ = json.load(open("tq.json"))
    return J, B, Q, TQ

def build_returns(J, B):
    d = J["d"]; N = len(d); nd = J["ndx"]; sp = J["spx"]; dff = J["dff"]; si = d.index(J["start"])
    T = [J["syn"][i] if i < si or J["real"][i] is None else J["real"][i] for i in range(N)]
    dt = [date.fromisoformat(x) for x in d]
    amap = lambda k: {datetime.fromtimestamp(r[0], timezone.utc).date().isoformat(): r[1] for r in B[k]}
    RQ, RL, RS = amap("QQQ"), amap("QLD"), amap("SPY")
    ret = {k: [0.0] for k in "TLQCS"}
    for i in range(1, N):
        k = (dt[i] - dt[i - 1]).days; r = dff[i - 1] / 100; x = nd[i] / nd[i - 1] - 1
        ret["T"].append(T[i] / T[i - 1] - 1)
        ret["L"].append(RL[d[i]] / RL[d[i - 1]] - 1 if i > si and d[i] in RL and d[i - 1] in RL
                        else 2 * x - r / 360 * k - (1.0095 ** (k / 365) - 1) - (1.01 ** (k / 365) - 1))
        ret["Q"].append(RQ[d[i]] / RQ[d[i - 1]] - 1 if i > si and d[i] in RQ and d[i - 1] in RQ else x)
        ret["C"].append(r / 360 * k)
        ret["S"].append(RS[d[i]] / RS[d[i - 1]] - 1 if d[i] in RS and d[i - 1] in RS else sp[i] / sp[i - 1] - 1)
    # 52주 고점(오늘 포함 252거래일), S&P500·나스닥100 200일선
    hi = []; dq = []
    for i in range(N):
        while dq and nd[dq[-1]] <= nd[i]: dq.pop()
        dq.append(i)
        if dq[0] <= i - 252: dq.pop(0)
        hi.append(nd[dq[0]])
    pre = [0.0]
    for v in nd: pre.append(pre[-1] + v)
    mav = lambda k, i: (pre[i + 1] - pre[i + 1 - k]) / k if i >= k - 1 else None
    ps = [0.0]
    for v in sp: ps.append(ps[-1] + v)
    sp200 = [None if i < 199 else (ps[i + 1] - ps[i - 199]) / 200 for i in range(N)]
    return dict(d=d, N=N, nd=nd, sp=sp, T=T, dt=dt, ret=ret, hi=hi, mav=mav, sp200=sp200, dff=dff)

# ── 단계 계산 (simple.html mkLevels 와 같은 규칙) ──
def mk_levels(D, cfg):
    d, N, nd, sp, hi, mav, sp200 = D["d"], D["N"], D["nd"], D["sp"], D["hi"], D["mav"], D["sp200"]
    lv = []; inm = False; top = False; ok = 0
    for i in range(N):
        m = sp200[i]; m2 = mav(200, i)
        if m is None or m2 is None: lv.append("C"); continue
        dv = nd[i] / hi[i] - 1
        cond = sp[i] > m * (1 + cfg.get("bIn", 0)) and dv >= -cfg["eIn"]; ok = ok + 1 if cond else 0
        if not inm:
            if ok >= cfg["confirm"]: inm = True; top = False
        elif sp[i] < m * (1 - cfg.get("bOut", 0)) or dv < -cfg["eOut"]: inm = False
        if not inm: lv.append("C"); continue
        if not top and dv >= -cfg["tIn"]: top = True
        elif top and dv < -cfg["tOut"]: top = False
        if nd[i] / m2 > cfg["oh"]: lv.append("X")
        elif top: lv.append("T")
        elif cfg.get("split"): lv.append("M1" if dv >= -cfg["split"] else "M2")
        else: lv.append("M")
    return lv

def engine(D, lv, W, a, b, ts=0.25):
    """비중 혼합 엔진 (simple.html engineH 와 같은 규칙): 단계 바뀔 때 비중 설정, 월초 재조정, TQQQ 몫 TS."""
    d, T, ret, dt = D["d"], D["T"], D["ret"], D["dt"]
    cur = lv[a]; h = dict(W[cur]); v = 1.0; pk = 1.0; mdd = 0.0; pkd = d[a]; w = ["", ""]; tpk = T[a]; cut = False
    vs = 1.0 if cur != "C" else 0.0; tr = []; sw = 0; cv = [1.0]
    def setw(tw):
        nonlocal h
        h = {k: v * x for k, x in tw.items() if x > 1e-12}
    for i in range(a + 1, b + 1):
        v = 0.0
        for k in h: h[k] *= 1 + ret[k][i]; v += h[k]
        t = lv[i]
        if t != cur:
            sw += 1
            if cur == "C" and t != "C": vs = v
            elif cur != "C" and t == "C" and vs: tr.append(v / vs - 1); vs = 0.0
            cur = t; cut = False; tpk = T[i]; setw(W[t])
        elif "T" in W[cur]:
            if not cut and ts is not None:
                tpk = max(tpk, T[i])
                if T[i] <= tpk * (1 - ts):
                    cut = True; sw += 1
                    setw({"S": h.get("S", 0) / v, "L": h.get("L", 0) / v, "Q": h.get("Q", 0) / v, "C": (h.get("T", 0) + h.get("C", 0)) / v})
            if not cut and d[i][5:7] != d[i - 1][5:7]: setw(W[cur])
        if v > pk: pk = v; pkd = d[i]
        if v / pk - 1 < mdd: mdd = v / pk - 1; w = [pkd, d[i]]
        cv.append(v)
    if vs: tr.append(v / vs - 1)
    y = (dt[b] - dt[a]).days / 365.25
    return dict(c=(v ** (1 / y) - 1) * 100, m=mdd * 100, v=v, w=w, cur=cur, cut=cut, tpk=tpk, tr=tr, sw=sw / y, cv=cv)

INF = float("inf")
STRATS = {
    "복합형": (dict(eIn=0.10, eOut=0.15, tIn=0.05, tOut=0.10, oh=1.15, confirm=1), {"T": {"T": 0.5, "S": 0.5}, "M": {"L": 1}, "X": {"Q": 1}, "C": {"C": 1}}, 0.25,
              {"T": ["TQQQ 50% + SPYM 50%", "SPYM 50% + SGOV 50%"], "M": "QLD", "X": "QQQ", "C": "SGOV"}),
    "고급형": (dict(eIn=0.10, eOut=0.15, tIn=0.05, tOut=0.12, oh=1.15, confirm=3), {"T": {"T": 0.7, "S": 0.3}, "M": {"L": 1}, "X": {"Q": 1}, "C": {"C": 1}}, 0.25,
              {"T": ["TQQQ 70% + SPYM 30%", "SPYM 30% + SGOV 70%"], "M": "QLD", "X": "QQQ", "C": "SGOV"}),
    "절충형": (dict(eIn=INF, eOut=INF, tIn=0.10, tOut=0.10, oh=INF, confirm=1, bIn=0.025, bOut=0.025), {"T": {"T": 0.6, "S": 0.4}, "M": {"Q": 1}, "X": {"Q": 1}, "C": {"C": 1}}, 0.25,
              {"T": ["TQQQ 60% + SPYM 40%", "SPYM 40% + SGOV 60%"], "M": "QQQ", "C": "SGOV"}),
    "반반형": (dict(eIn=INF, eOut=INF, tIn=0.10, tOut=0.10, oh=INF, confirm=1, bIn=0.025, bOut=0.025), {"T": {"T": 0.5, "S": 0.5}, "M": {"Q": 1}, "X": {"Q": 1}, "C": {"C": 1}}, 0.25,
              {"T": ["TQQQ 50% + SPYM 50%", "SPYM 50% + SGOV 50%"], "M": "QQQ", "C": "SGOV"}),
    "과열형": (dict(eIn=INF, eOut=INF, tIn=0.07, tOut=0.07, oh=1.15, confirm=1, bIn=0.03, bOut=0.03), {"T": {"T": 0.8, "S": 0.2}, "M": {"Q": 1}, "X": {"Q": 1}, "C": {"C": 1}}, None,
              {"T": "TQQQ 80% + SPYM 20%", "M": "QQQ", "X": "QQQ (과열)", "C": "SGOV"}),
    "상시형": (dict(eIn=INF, eOut=INF, tIn=0.10, tOut=0.10, oh=INF, confirm=1, bIn=0.03, bOut=0.03), {"T": {"T": 0.8, "S": 0.2}, "M": {"T": 0.5, "S": 0.5}, "X": {"Q": 1}, "C": {"C": 1}}, 0.25,
              {"T": ["TQQQ 80% + SPYM 20%", "SPYM 20% + SGOV 80%"], "M": ["TQQQ 50% + SPYM 50%", "SPYM 50% + SGOV 50%"], "C": "SGOV"}),
    "삼단형": (dict(eIn=INF, eOut=INF, tIn=0.10, tOut=0.10, oh=INF, confirm=1, bIn=0.025, bOut=0.025, split=0.15), {"T": {"T": 1}, "M1": {"L": 1}, "M2": {"Q": 1}, "X": {"Q": 1}, "C": {"C": 1}}, 0.25,
              {"T": ["TQQQ", "SGOV (TS)"], "M1": "QLD", "M2": "QQQ", "C": "SGOV"}),
    "고점형": (dict(eIn=INF, eOut=INF, tIn=0.10, tOut=0.10, oh=INF, confirm=1, bIn=0.03, bOut=0.03), {"T": {"T": 0.5, "S": 0.5}, "M": {"T": 0.5, "S": 0.5}, "X": {"Q": 1}, "C": {"C": 1}}, 0.25,
              {"T": ["TQQQ 50% + SPYM 50%", "SPYM 50% + SGOV 50%"], "M": ["TQQQ 50% + SPYM 50%", "SPYM 50% + SGOV 50%"], "C": "SGOV"}),
    # 최고점형: 고점형 뼈대 + 밴드 ±3.5% + TS −15%
    "최고점형": (dict(eIn=INF, eOut=INF, tIn=0.10, tOut=0.10, oh=INF, confirm=1, bIn=0.035, bOut=0.035), {"T": {"T": 0.5, "S": 0.5}, "M": {"T": 0.5, "S": 0.5}, "X": {"Q": 1}, "C": {"C": 1}}, 0.15,
              {"T": ["TQQQ 50% + SPYM 50%", "SPYM 50% + SGOV 50%"], "M": ["TQQQ 50% + SPYM 50%", "SPYM 50% + SGOV 50%"], "C": "SGOV"}),
}

def jonghap_today(Q, TQ):
    """종합형 오늘 신호: 페이지와 같이 QQQ 실제 종가(tqqq_data.json)와 tq.json 의 S&P500 상태로 계산."""
    c = [r[4] for r in Q["ohlc"]["QQQ_1d"]]; i = len(c) - 1
    hi = max(c[-252:]); ma = sum(c[-200:]) / 200; S = TQ["spx"]
    sp_up = S["idx"] > S["ma200"]; dd = c[i] / hi - 1; dis = c[i] / ma
    sig = "SGOV" if (not sp_up or dd < -0.15) else "QQQ" if dis > 1.15 else "TQQQ 50%" if dd >= -0.05 else "QQQ"
    return dict(text=sig, dd=round(dd * 100, 2), dis=round((dis - 1) * 100, 2), qqq=c[i], hi=hi,
                date=datetime.fromtimestamp(Q["ohlc"]["QQQ_1d"][i][0], timezone.utc).date().isoformat())

def main():
    now = time.time(); J, B, Q, TQ = load(); D = build_returns(J, B)
    d, N, nd, sp, T, hi, sp200, mav = D["d"], D["N"], D["nd"], D["sp"], D["T"], D["hi"], D["sp200"], D["mav"]
    a0 = next(i for i, x in enumerate(d) if x >= "1986-10-01")
    checks, notes, signals, bt = [], [], {}, {}
    def chk(name, ok, detail): checks.append(dict(name=name, ok=bool(ok), detail=detail))

    # ── 데이터 점검 ──
    qlast = Q["ohlc"]["QQQ_1d"][-1]; tlast = Q["ohlc"]["TQQQ_1d"][-1]
    qdate = datetime.fromtimestamp(qlast[0], timezone.utc).date().isoformat()
    chk("데이터 날짜 일치", d[-1] == qdate == TQ["spx"]["date"], f"40년 {d[-1]} / QQQ {qdate} / S&P500 {TQ['spx']['date']}")
    final = J.get("bar_final"); age_min = (now - J.get("ts", 0)) / 60
    chk("40년 데이터 봉 확정", final is not False, ("종가 확정" if final else "확정 여부 미기록(갱신 전 형식)" if final is None else "장중 실시간가 — 종가 확정 전엔 신호가 바뀔 수 있음") + f" · {age_min:.0f}분 전 갱신")
    if final is False: notes.append("지금 보이는 40년 기준 신호는 장중 실시간가 기준입니다. 미국 장 마감(한국 아침 5~6시) 뒤 15분 안에 확정됩니다.")
    qmap = {datetime.fromtimestamp(r[0], timezone.utc).date().isoformat(): r[4] for r in Q["ohlc"]["QQQ_1d"]}
    rs = [nd[i] / qmap[d[i]] for i in range(N - 25, N) if d[i] in qmap]
    if len(rs) >= 10:
        med = statistics.median(rs[:-1]); dev = (rs[-1] / med - 1) * 100
        chk("나스닥100 ↔ QQQ 종가 비율", abs(dev) < 0.12, f"최근 20일 중앙값 대비 {dev:+.2f}% (평소 ±0.05% 안 — 장중 스냅샷이나 데이터 오류면 벌어짐)")
    chk("S&P500 종가 (40년 파일 ↔ 신호판)", abs(sp[-1] / TQ["spx"]["idx"] - 1) < 0.001, f"{sp[-1]:,.2f} / {TQ['spx']['idx']:,.2f}")
    chk("S&P500 200일선 (40년 파일 ↔ 신호판)", abs(sp200[-1] / TQ["spx"]["ma200"] - 1) < 0.001, f"{sp200[-1]:,.2f} / {TQ['spx']['ma200']:,.2f}")
    chk("TQQQ 종가 (40년 파일 ↔ 실시간 파일)", abs(T[-1] / tlast[4] - 1) < 0.003, f"{T[-1]:.2f} / {tlast[4]:.2f}")

    # ── 오늘 신호 ──
    dv = nd[-1] / hi[-1] - 1; m2 = mav(200, N - 1); dis = nd[-1] / m2 - 1; spm = sp[-1] / sp200[-1] - 1
    signals["종합형"] = jonghap_today(Q, TQ)
    for nm, (cfg, W, ts, lab) in STRATS.items():
        lv = mk_levels(D, cfg); e = engine(D, lv, W, a0, N - 1, ts); st = lv[-1]; L = lab.get(st, "SGOV")
        cutnow = isinstance(L, list) and e["cut"] and e["cur"] == st
        text = (L[1] if cutnow else L[0]) if isinstance(L, list) else L
        signals[nm] = dict(text=text, level=st, cut=bool(cutnow), ts_line=round(e["tpk"] * (1 - ts), 2) if (ts and isinstance(L, list) and not cutnow) else None)
        trs = e["tr"]; win = sum(1 for x in trs if x > 0) / len(trs) * 100 if trs else 0
        bt[nm] = dict(c=round(e["c"], 2), m=round(e["m"], 2), n=len(trs), win=round(win, 1), mdd_from=e["w"][0], mdd_to=e["w"][1])
    # 분산형: 세 구좌(구간 −8/−10/−12% · TS −20/−25/−30%) 독립 운용 후 합산
    WD = {"T": {"T": 0.9, "S": 0.1}, "M": {"T": 0.7, "S": 0.3}, "X": {"Q": 1}, "C": {"C": 1}}; subs = []
    for top, ts in ((0.08, 0.20), (0.10, 0.25), (0.12, 0.30)):
        lv = mk_levels(D, dict(eIn=INF, eOut=INF, tIn=top, tOut=top, oh=INF, confirm=1, bIn=0.03, bOut=0.03)); subs.append((lv, engine(D, lv, WD, a0, N - 1, ts)))
    wT = wS = wC = 0.0
    for lv, e in subs:
        st = lv[-1]; zone = st == "T"; inm = st != "C"; cut = inm and e["cut"] and e["cur"] == st
        t = 0 if not inm or cut else (0.9 if zone else 0.7); spw = (0.1 if zone else 0.3) if inm else 0; wT += t / 3; wS += spw / 3; wC += (1 - t - spw) / 3
    pw = lambda x: int(round(x * 100))
    signals["분산형"] = dict(text=(f"TQQQ {pw(wT)}% + SPYM {pw(wS)}% + SGOV {pw(wC)}%" if wC > 0.005 else f"TQQQ {pw(wT)}% + SPYM {pw(wS)}%"), level="/".join(lv[-1] + ("c" if (e["cut"] and e["cur"] == lv[-1]) else "") for lv, e in subs), cut=None, ts_line=None)
    # 분산형 40년: 세 곡선 평균 → 연복리·최대낙폭, 왕복 거래는 공통 밴드(②) 기준
    n = len(subs[0][1]["cv"]); cv = [(subs[0][1]["cv"][i] + subs[1][1]["cv"][i] + subs[2][1]["cv"][i]) / 3 for i in range(n)]
    pk = 1.0; mdd = 0.0; pkd = d[a0]; w = ["", ""]
    for i in range(1, n):
        if cv[i] > pk: pk = cv[i]; pkd = d[a0 + i]
        if cv[i] / pk - 1 < mdd: mdd = cv[i] / pk - 1; w = [pkd, d[a0 + i]]
    lvc = subs[1][0]; tr = []; vs = 1.0 if lvc[a0] != "C" else 0.0
    for i in range(a0 + 1, N):
        if lvc[i - 1] == "C" and lvc[i] != "C": vs = cv[i - a0]
        elif lvc[i - 1] != "C" and lvc[i] == "C" and vs: tr.append(cv[i - a0] / vs - 1); vs = 0.0
    if vs: tr.append(cv[-1] / vs - 1)
    y = (D["dt"][N - 1] - D["dt"][a0]).days / 365.25
    bt["분산형"] = dict(c=round((cv[-1] ** (1 / y) - 1) * 100, 2), m=round(mdd * 100, 2), n=len(tr), win=round(sum(1 for x in tr if x > 0) / len(tr) * 100, 1) if tr else 0, mdd_from=w[0], mdd_to=w[1])
    S = TQ["spx"]; signals["TQQQ 신호판"] = dict(text="TQQQ" if S["state"] == "IN" else "SGOV", level=S["state"], ts_line=(S.get("cycle") or {}).get("ts_line"))

    # ── 경계 근처 (오늘 밤 작은 움직임으로 신호가 바뀔 수 있는 것) ──
    near = []
    for th, who in ((-0.05, "복합형·고급형 신고가 구간 진입선"), (-0.07, "과열형 구간선"), (-0.10, "절충형·반반형·상시형·삼단형 구간선 / 고점형·최고점형 TS 해제선 / 복합형 구간 해제선 / 복합형·고급형 진입선"),
                    (-0.12, "고급형 구간 해제선"), (-0.15, "복합형·고급형 탈출선 / 삼단형 QLD→QQQ 선")):
        gap = (dv - th) * 100
        if abs(gap) < 1.0: near.append(f"QQQ 52주 고점 대비 {dv*100:.1f}% — {who}({th*100:.0f}%)까지 {gap:+.1f}%p")
    for th, who in ((0.025, "절충형·반반형·삼단형·신호판 진입선(+2.5%)"), (-0.025, "절충형·반반형·삼단형·신호판 탈출선(−2.5%)"), (0.03, "과열형·상시형·고점형 진입선(+3%)"), (-0.03, "과열형·상시형·고점형 탈출선(−3%)"), (0.035, "최고점형 진입선(+3.5%)"), (-0.035, "최고점형 탈출선(−3.5%)"), (0.0, "종합형·복합형·고급형 200일선")):
        gap = (spm - th) * 100
        if abs(gap) < 0.7: near.append(f"S&P500이 200일선 대비 {spm*100:+.2f}% — {who}까지 {gap:+.2f}%p")
    if abs(dis - 0.15) * 100 < 1.0: near.append(f"QQQ가 200일선 대비 {dis*100:+.1f}% — 과열선(+15%)까지 {(dis-0.15)*100:+.1f}%p")
    for nm, sg in signals.items():
        if sg.get("ts_line") and T[-1] / sg["ts_line"] - 1 < 0.03: near.append(f"{nm} TS선 {sg['ts_line']} — TQQQ {T[-1]:.2f}, {(T[-1]/sg['ts_line']-1)*100:+.1f}% 위")
    chk("경계 근처 지표", not near, " / ".join(near) if near else "모든 지표가 기준선에서 1%p 이상 떨어져 있음")

    bad = [c for c in checks if not c["ok"]]
    level = "ok" if not bad else ("warn" if all(c["name"] in ("경계 근처 지표", "40년 데이터 봉 확정") for c in bad) else "err")
    verdict = ("데이터 이상 없음" if level == "ok" else ("주의: " if level == "warn" else "데이터 경고: ") + " · ".join(c["name"] for c in bad))
    out = dict(at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M+00:00"), at_kst=datetime.now(KST).strftime("%m/%d %H:%M"),
               data=dict(date=d[-1], bar_final=final, age_min=round(age_min), ndx=nd[-1], qqq=qlast[4], spx=sp[-1], sp200=round(sp200[-1], 2), tqqq=T[-1],
                         dd52=round(dv * 100, 2), dis=round(dis * 100, 2), spm=round(spm * 100, 2)),
               checks=checks, notes=notes, near=near, signals=signals, bt=bt, level=level, verdict=verdict)
    json.dump(out, open(OUT, "w"), ensure_ascii=False, indent=1)
    print(verdict); print({k: v["text"] for k, v in signals.items()}); print({k: (v["c"], v["m"]) for k, v in bt.items()})

if __name__ == "__main__":
    main()
