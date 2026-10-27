"""대폭락 조짐 지수 → crash.json (매 실행마다 계산, 원자료는 crash_raw.json · tq40.json).

구조 (논리 순서)
  1. 연료 — 버블형: 시장이 이미 얼마나 비싸고 많이 올랐나 (밸류에이션 · 3년 상승 · 단기 과열 · 나스닥 쏠림)
  2. 균열 — 리먼형: 경제·신용이 깨지기 시작했나 (금리차 · 신용 스프레드 · 금융여건 · 고용 · 주택·가계 · 은행 대출 · 긴축)
  3. 불씨 — 진행 확인: 시장 자체가 이미 꺾였나 (200일선 · 고점 대비 낙폭 · 변동성 · 스프레드 급등)
각 지표는 0(정상)/1(주의)/2(경고). 기준선은 관례적 기준 또는 '그때까지 역사의 상위 20%/5%'(그날까지 알 수 있던 자료만 씀).
기둥 점수 = 켜진 단계 합 ÷ 최대치 × 100. 종합 등급은 아래 grade() 의 표대로.
월·분기 지표는 실제 발표 시차를 넣어 '그날 알 수 있었던 값'만 쓴다.
"""
import bisect, json, os, time
from datetime import date, timedelta, datetime, timezone

ROOT = os.path.join(os.path.dirname(__file__), "..")
LAG = {"T10Y3M": 1, "T10Y2Y": 1, "BAA10Y": 1, "BAMLH0A0HYM2": 1, "VIXCLS": 0, "VXOCLS": 0, "DFF": 1, "DGS2": 1, "NFCI": 5, "STLFSI4": 6,
       "ICSA": 5, "SAHMREALTIME": 38, "UNRATE": 38, "PERMIT": 48, "DRTSCILM": 40, "TDSP": 170, "DRSFRMACBS": 145, "NCBEILQ027S": 162, "GDP": 120}
GRADES = ["매우낮음", "낮음", "중간", "높음", "매우높음"]
MEMORY = 20   # 한 번 오른 등급은 20거래일(약 한 달) 유지 — 매일의 흔들림 제거
# 추가 지표 (공포·탐욕 · 풋콜 · RSI · 원달러 · 나스닥 200일선) — 검증 때 하나씩 끄고 켜 보려고 스위치로 둠
OPT = dict(sent=True, rsi=True, krw=True, qqq_trend=True)
T_CAP = 4     # 불씨는 '몇 개가 켜졌나': 켜진 단계 합 ÷ (2 × 4) — 지표가 늘어도 묽어지지 않게 (8점이면 100)


def load():
    J = json.load(open(os.path.join(ROOT, "tq40.json")))
    R = json.load(open(os.path.join(ROOT, "crash_raw.json")))
    try:
        R["fg"] = json.load(open(os.path.join(ROOT, "fg_hist.json")))
    except Exception:
        R["fg"] = {"d": [], "v": []}
    return J, R


def build(J, R):
    d = J["d"]; N = len(d); D = [date.fromisoformat(x) for x in d]
    spx = J["spx"]; ndx = J["ndx"]

    def align(sid):
        rows = R["series"].get(sid, [])
        ks = [date.fromisoformat(r[0]) + timedelta(days=LAG[sid]) for r in rows]
        out = [None] * N; obs = [None] * N; j = -1
        for i in range(N):
            while j + 1 < len(ks) and ks[j + 1] <= D[i]: j += 1
            if j >= 0: out[i] = rows[j][1]; obs[i] = rows[j][0]
        return out, obs

    A, OBS = {}, {}
    for sid in LAG:
        A[sid], OBS[sid] = align(sid)

    def back(i, days):
        return max(0, bisect.bisect_left(D, D[i] - timedelta(days=days)))

    def sma(a, n):
        out = [None] * N; s = 0.0; q = []
        for i, v in enumerate(a):
            q.append(v); s += v
            if len(q) > n: s -= q.pop(0)
            if len(q) == n: out[i] = s / n
        return out

    ma_s = sma(spx, 200); ma_n = sma(ndx, 200)
    ath = []; m = 0
    for v in spx: m = max(m, v); ath.append(m)
    vix = [A["VIXCLS"][i] if A["VIXCLS"][i] is not None else A["VXOCLS"][i] for i in range(N)]

    # ── 추가 지표 ──
    # 공포·탐욕 (CNN, 2011~): 그날 값 (발표 당일 장 마감 뒤)
    fgm = dict(zip(R["fg"]["d"], R["fg"]["v"])); fg = [None] * N; fgd = [None] * N; last = None; lastd = None
    fgk = sorted(fgm); j = -1
    for i in range(N):
        while j + 1 < len(fgk) and fgk[j + 1] <= d[i]: j += 1
        if j >= 0 and (D[i] - date.fromisoformat(fgk[j])).days <= 7: fg[i] = fgm[fgk[j]]; fgd[i] = fgk[j]
    # 풋콜 5일 평균: CBOE 전체(2006-11~2019-10, 직접 5일 평균) + CNN(5일 평균, 2025-10~ 쌓이는 중) — 수준이 시기마다 달라 '최근 1년 안의 위치'로 판단
    pcm = {}
    tot = R["series"].get("PC_TOTAL", [])
    for k in range(4, len(tot)): pcm[tot[k][0]] = sum(x[1] for x in tot[k - 4:k + 1]) / 5
    for r in R["series"].get("CNN_put_call_options", []): pcm[r[0]] = r[1]
    pck = sorted(pcm); pc = [None] * N; pcd = [None] * N; j = -1
    for i in range(N):
        while j + 1 < len(pck) and pck[j + 1] <= d[i]: j += 1
        if j >= 0 and (D[i] - date.fromisoformat(pck[j])).days <= 7: pc[i] = pcm[pck[j]]; pcd[i] = pck[j]
    pc_pct = [None] * N
    for i in range(N):
        if pc[i] is None: continue
        k = back(i, 365); h = [pc[t] for t in range(k, i + 1) if pc[t] is not None]
        if len(h) >= 150: pc_pct[i] = sum(1 for x in h if x <= pc[i]) / len(h) * 100
    # 나스닥100 RSI(14, Wilder)
    rsi = [None] * N; g = l = 0.0
    for i in range(1, N):
        ch = ndx[i] - ndx[i - 1]; up = max(ch, 0); dn = max(-ch, 0)
        if i <= 14: g += up / 14; l += dn / 14
        else: g = (g * 13 + up) / 14; l = (l * 13 + dn) / 14
        if i >= 14: rsi[i] = 100.0 if l == 0 else 100 - 100 / (1 + g / l)
    # 원/달러 (FRED DEXKOUS, tq40.json에 이미 있음)
    krw = []; lf = None
    for v in J.get("krw", [None] * N):
        if v is not None: lf = v
        krw.append(lf)

    # 버핏 지수: 비금융기업 주식 시가총액 / 명목 GDP — 분기말 값을 S&P500 변화로 그날까지 늘림
    gdp = {r[0]: r[1] for r in R["series"]["GDP"]}
    qs = []
    for r in R["series"]["NCBEILQ027S"]:
        if r[0] not in gdp: continue
        q = date.fromisoformat(r[0])
        qend = date(q.year + (q.month + 2) // 12, (q.month + 2) % 12 + 1, 1) - timedelta(days=1)
        qs.append((qend, qend + timedelta(days=72), r[1] / 1e3 / gdp[r[0]], r[0]))
    buf = [None] * N; buf_hist = [[] for _ in range(N)]; j = -1
    for i in range(N):
        while j + 1 < len(qs) and qs[j + 1][1] <= D[i]: j += 1
        if j < 0: continue
        qend, _, val, _ = qs[j]; k = bisect.bisect_right(D, qend) - 1
        if k < 0: continue
        buf[i] = val * spx[i] / spx[k]
    buf_known = [None] * N; j = -1  # 그날까지 발표된 분기 값들 (백분위 기준)
    for i in range(N):
        while j + 1 < len(qs) and qs[j + 1][1] <= D[i]: j += 1
        buf_known[i] = j

    def r3(a, i):
        k = back(i, 1095)
        return a[i] / a[k] - 1 if D[i] - D[k] >= timedelta(days=1090) else None

    s3 = [r3(spx, i) for i in range(N)]; n3 = [r3(ndx, i) for i in range(N)]
    dev = [ndx[i] / ma_n[i] - 1 if ma_n[i] else None for i in range(N)]
    rel = [(1 + n3[i]) / (1 + s3[i]) - 1 if n3[i] is not None and s3[i] is not None else None for i in range(N)]

    # 확장 백분위: 그날까지(5년 이상 쌓인 뒤) 값들 가운데 몇 %가 오늘 이하인가
    def expanding_pct(a, min_years=5):
        out = [None] * N; srt = []; first = None
        for i in range(N):
            v = a[i]
            if v is None: continue
            if first is None: first = D[i]
            bisect.insort(srt, v)
            if (D[i] - first).days >= min_years * 365:
                out[i] = bisect.bisect_right(srt, v) / len(srt) * 100
        return out

    p_s3 = expanding_pct(s3); p_dev = expanding_pct(dev); p_rel = expanding_pct(rel)
    p_buf = [None] * N
    for i in range(N):
        if buf[i] is None or buf_known[i] < 20: continue
        hist = sorted(x[2] for x in qs[:buf_known[i] + 1])
        p_buf[i] = bisect.bisect_right(hist, buf[i]) / len(hist) * 100

    # 금리차: 월평균이 음수였던 마지막 달 (24개월 안이면 주의, 지금 달이 음수면 경고)
    mon = {}
    for r in R["series"]["T10Y3M"]: mon.setdefault(r[0][:7], []).append(r[1])
    mavg = {k: sum(v) / len(v) for k, v in mon.items()}
    months = sorted(mavg)

    def curve_state(i):
        cur = D[i].strftime("%Y-%m")
        done = [m_ for m_ in months if m_ < cur]  # 끝난 달만 (이번 달은 진행 중)
        if not done: return None, None, None
        last = done[-1]; neg = [m_ for m_ in done if mavg[m_] < 0]
        last_neg = neg[-1] if neg else None
        return mavg[last], last_neg, last

    claims4 = [None] * N
    for i in range(N):
        k = back(i, 28); vals = [A["ICSA"][t] for t in range(k, i + 1) if A["ICSA"][t] is not None]
        if vals: claims4[i] = sum(vals) / len(vals)

    def lv(x, warn, alert, up=True):
        if x is None: return None
        return (2 if x >= alert else 1 if x >= warn else 0) if up else (2 if x <= alert else 1 if x <= warn else 0)

    def worst(*xs):
        xs = [x for x in xs if x is not None]
        return max(xs) if xs else None

    def ind(i):
        """i번째 거래일의 지표들: (키, 기둥, 단계, 값 문자열, 기준 문자열, 원자료 날짜)"""
        o = []
        # ── 연료 (버블형) ──
        o.append(("buf", "F", lv(p_buf[i], 80, 95), buf[i], p_buf[i]))
        o.append(("s3", "F", lv(p_s3[i], 80, 95), s3[i], p_s3[i]))
        o.append(("dev", "F", lv(p_dev[i], 80, 95), dev[i], p_dev[i]))
        o.append(("rel", "F", lv(p_rel[i], 80, 95), rel[i], p_rel[i]))
        if OPT["sent"]:   # 참고(R, 등급에 안 넣음): 극단적 탐욕 · 풋콜 쏠림 — 검증에서 폭락 예측력이 없었음
            o.append(("greed", "R", None if fg[i] is None else (2 if fg[i] >= 85 else 1 if fg[i] >= 75 else 0), fg[i], None))
            o.append(("pc", "R", None if pc_pct[i] is None else (1 if pc_pct[i] <= 10 or pc_pct[i] >= 90 else 0), pc[i], pc_pct[i], pcd[i]))
        # ── 균열 (리먼형) ──
        cur, last_neg, last_m = curve_state(i)
        if cur is None: c_lv = None
        else:
            months_since = None
            if last_neg:
                y, mo = map(int, last_neg.split("-")); y2, mo2 = map(int, last_m.split("-")); months_since = (y2 - y) * 12 + mo2 - mo
            c_lv = 2 if cur < 0 else 1 if (months_since is not None and months_since <= 24) else 0
        o.append(("curve", "C", c_lv, cur, last_neg))
        k6 = back(i, 182)
        b6 = A["BAA10Y"][i] - A["BAA10Y"][k6] if A["BAA10Y"][i] is not None and A["BAA10Y"][k6] is not None else None
        o.append(("baa6", "C", lv(b6, 0.3, 0.75), b6, A["BAA10Y"][i]))
        o.append(("nfci", "C", lv(A["NFCI"][i], -0.25, 0.0), A["NFCI"][i], None))
        k12 = back(i, 365)
        lo = [claims4[t] for t in range(k12, i + 1) if claims4[t] is not None]
        cl = claims4[i] / min(lo) - 1 if lo and claims4[i] else None
        o.append(("jobs", "C", worst(lv(A["SAHMREALTIME"][i], 0.3, 0.5), lv(cl, 0.15, 0.30)), A["SAHMREALTIME"][i], cl))
        py = A["PERMIT"][i] / A["PERMIT"][k12] - 1 if A["PERMIT"][i] and A["PERMIT"][k12] else None
        dq = A["DRSFRMACBS"][i] - A["DRSFRMACBS"][k12] if A["DRSFRMACBS"][i] is not None and A["DRSFRMACBS"][k12] is not None else None
        o.append(("house", "C", worst(lv(py, -0.15, -0.25, up=False), lv(dq, 0.3, 0.6)), py, dq))
        o.append(("sloos", "C", lv(A["DRTSCILM"][i], 10, 25), A["DRTSCILM"][i], None))
        f12 = A["DFF"][i] - A["DFF"][k12] if A["DFF"][i] is not None and A["DFF"][k12] is not None else None
        o.append(("fed", "C", lv(f12, 1.0, 2.0), f12, A["DFF"][i]))
        # ── 불씨 (진행 확인) ──
        t1 = None if ma_s[i] is None else (2 if spx[i] < ma_s[i] * 0.975 else 1 if spx[i] < ma_s[i] else 0)
        if OPT["qqq_trend"] and ma_n[i] is not None:   # 나스닥100(QQQ) 200일선도 같은 기준 — 둘 중 나쁜 쪽
            t1 = worst(t1, 2 if ndx[i] < ma_n[i] * 0.975 else 1 if ndx[i] < ma_n[i] else 0)
        o.append(("trend", "T", t1, spx[i] / ma_s[i] - 1 if ma_s[i] else None, ndx[i] / ma_n[i] - 1 if ma_n[i] else None))
        ddv = spx[i] / ath[i] - 1
        o.append(("dd", "T", lv(ddv, -0.10, -0.20, up=False), ddv, None))
        o.append(("vix", "T", lv(vix[i], 25, 35), vix[i], None))
        k3 = back(i, 91)
        b3 = A["BAA10Y"][i] - A["BAA10Y"][k3] if A["BAA10Y"][i] is not None and A["BAA10Y"][k3] is not None else None
        o.append(("baa3", "T", lv(b3, 0.3, 0.6), b3, None))
        if OPT["sent"]:   # 공포 확산: CNN 공포·탐욕 25 이하(극단적 공포) 주의 · 10 이하 경고
            o.append(("fear", "T", None if fg[i] is None else (2 if fg[i] <= 10 else 1 if fg[i] <= 25 else 0), fg[i], fgd[i]))
        if OPT["rsi"]:    # 단기 매도세: 나스닥100 RSI 40 이하(약세 구간) 주의 · 30 이하(과매도 투매) 경고
            o.append(("rsi", "T", lv(rsi[i], 40, 30, up=False), rsi[i], None))
        if OPT["krw"]:    # 달러 쏠림: 원/달러 3개월 +5% 주의 · +10% 경고 (위기 때 달러로 돈이 몰림)
            k3 = back(i, 91); kc = krw[i] / krw[k3] - 1 if krw[i] and krw[k3] else None
            o.append(("krw", "T", lv(kc, 0.05, 0.10), kc, krw[i]))
        return o

    return dict(d=d, D=D, N=N, spx=spx, ndx=ndx, ind=ind, A=A, OBS=OBS, buf=buf, qs=qs, ath=ath, vix=vix, mavg=mavg, fgd=fgd, pcd=pcd, krw=krw, rsi=rsi, back=back)


def pillar(o, p):
    xs = [x[2] for x in o if x[1] == p and x[2] is not None]
    if len(xs) < 2: return None
    if p == "T": return min(100.0, sum(xs) / (2 * T_CAP) * 100)
    return sum(xs) / (2 * len(xs)) * 100


def band(s):
    return None if s is None else 0 if s < 25 else 1 if s < 50 else 2   # 낮음 / 중간 / 높음


def grade(F, C, T):
    """연료(F)·균열(C)·불씨(T) 점수 → 0~4 (매우낮음~매우높음)"""
    f, c, t = band(F), band(C), band(T)
    if f is None or c is None or t is None: return None
    if t == 2 and max(f, c) >= 1: return 4                  # 이미 꺾이는 중 + 연료나 균열
    if c == 2 or (f == 2 and c >= 1) or (t >= 1 and max(f, c) == 2): return 3
    if f == 2 or c == 1 or t >= 1: return 2
    if f == 1: return 1
    return 0


def main():
    J, R = load(); B = build(J, R); N = B["N"]; d = B["d"]
    start = bisect.bisect_left(d, "1990-01-01")
    hist = []; raw = []; first = {}
    for i in range(start, N):
        o = B["ind"](i); F, C, T = pillar(o, "F"), pillar(o, "C"), pillar(o, "T")
        g = grade(F, C, T); raw.append(g)
        w = [x for x in raw[-(MEMORY):] if x is not None]
        hist.append((i, F, C, T, max(w) if w else None, g))
    gm = {h[0]: h[4] for h in hist}; graw = {h[0]: h[5] for h in hist}
    # 사후 검증: 각 날짜에서 앞으로 12개월 S&P500 최대 낙폭 (그날 종가 대비 최저)
    spx = B["spx"]; D = B["D"]
    fwd = []
    for i, *_ in hist:
        k = bisect.bisect_right(D, D[i] + timedelta(days=365)) - 1
        fwd.append(min(spx[i:k + 1]) / spx[i] - 1 if D[-1] - D[i] >= timedelta(days=365) else None)
    stats = []
    for g in range(5):
        xs = [f for (_, _, _, _, gg, _), f in zip(hist, fwd) if gg == g and f is not None]
        days = sum(1 for h in hist if h[4] == g)
        stats.append(dict(g=g, days=days, share=days / len(hist) * 100, n=len(xs),
                          p20=sum(1 for x in xs if x <= -0.20) / len(xs) * 100 if xs else None,
                          p30=sum(1 for x in xs if x <= -0.30) / len(xs) * 100 if xs else None,
                          avg=sum(xs) / len(xs) * 100 if xs else None))
    allx = [f for f in fwd if f is not None]
    base = dict(n=len(allx), p20=sum(1 for x in allx if x <= -0.2) / len(allx) * 100, p30=sum(1 for x in allx if x <= -0.3) / len(allx) * 100, avg=sum(allx) / len(allx) * 100)
    # 오늘
    i = N - 1; o = B["ind"](i); F, C, T = pillar(o, "F"), pillar(o, "C"), pillar(o, "T")
    since = i
    while since - 1 in gm and gm[since - 1] == gm[i]: since -= 1
    today = dict(date=d[i], F=F, C=C, T=T, g=gm[i], g_raw=graw[i], since=d[since],
                 ind=[dict(k=x[0], p=x[1], lv=x[2], v=x[3], x=x[4], y=x[5] if len(x) > 5 else None) for x in o],
                 obs={k: B["OBS"][k][i] for k in B["OBS"]}, spx=spx[i], ath=B["ath"][i], vix=B["vix"][i],
                 ctx={k: B["A"][k][i] for k in ("T10Y3M", "BAA10Y", "NFCI", "STLFSI4", "SAHMREALTIME", "UNRATE", "ICSA", "PERMIT", "DRSFRMACBS", "DRTSCILM", "DFF", "BAMLH0A0HYM2")})
    # 최근 60거래일 매일 기록
    recent = []
    for j in range(max(0, N - 60), N):
        o2 = B["ind"](j); F2, C2, T2 = pillar(o2, "F"), pillar(o2, "C"), pillar(o2, "T")
        recent.append([d[j], round(F2, 1), round(C2, 1), round(T2, 1), gm.get(j), graw.get(j), [x[2] for x in o2], [None if x[3] is None or isinstance(x[3], str) else round(x[3], 4) for x in o2]])
    # 차트용 주간 기록 (금요일 또는 마지막 날)
    weekly = []
    for (i2, F2, C2, T2, g2, _) in hist:
        if i2 == N - 1 or D[i2].isocalendar()[1] != D[min(i2 + 1, N - 1)].isocalendar()[1]:
            weekly.append([d[i2], round(spx[i2], 2), None if F2 is None else round(F2), None if C2 is None else round(C2), None if T2 is None else round(T2), g2])
    # 과거 위기 직전 등급
    episodes = []
    for pk, nm in (("1998-07-17", "1998 LTCM"), ("2000-03-24", "2000 닷컴"), ("2007-10-09", "2008 리먼"), ("2018-09-20", "2018 긴축"), ("2020-02-19", "2020 코로나"), ("2022-01-03", "2022 긴축")):
        ip = bisect.bisect_left(d, pk); row = dict(peak=pk, name=nm, at={})
        # 고점 뒤 바닥 (고점 회복 전 최저)
        j = ip; mn = ip
        while j < N and spx[j] < spx[ip] * 1.0001 or j == ip:
            if spx[j] < spx[mn]: mn = j
            j += 1
            if j >= N: break
        row["depth"] = spx[mn] / spx[ip] - 1; row["trough"] = d[mn]
        for mback in (24, 18, 12, 6, 3, 0):
            jj = max(0, bisect.bisect_left(D, D[ip] - timedelta(days=int(mback * 30.44))))
            o3 = B["ind"](jj); F3, C3, T3 = pillar(o3, "F"), pillar(o3, "C"), pillar(o3, "T")
            row["at"][str(mback)] = [d[jj], None if F3 is None else round(F3), None if C3 is None else round(C3), None if T3 is None else round(T3), gm.get(jj)]
        # 고점 뒤 처음 '높음' 이상이 된 날과 그때 S&P (그 뒤 바닥까지 남은 하락)
        k = ip
        while k <= mn and (gm.get(k) is None or gm[k] < 3): k += 1
        row["first_high"] = [d[k], spx[k], spx[mn] / spx[k] - 1] if k <= mn else None
        episodes.append(row)
    # 단일 지표 검증: 조건이 켜진 날 다음 1년 안 S&P500 −10%/−20% 확률 (2006-11~ , 1년 뒤가 있는 날만)
    fwd_by = {h[0]: f for h, f in zip(hist, fwd)}
    A = B["A"]
    def fs(i):
        return A["DGS2"][i] - A["DFF"][i]
    def single(cond, a="2006-11-01"):
        ia = bisect.bisect_left(d, a); xs = []; al = []
        for i2 in range(ia, N):
            f = fwd_by.get(i2)
            if f is None: continue
            o2 = B["ind"](i2); m = {x[0]: x for x in o2}
            al.append(f)
            try:
                if (cond(m) if cond.__code__.co_argcount == 1 else cond(m, i2)): xs.append(f)
            except Exception: pass
        r = lambda arr, t: round(sum(1 for x in arr if x <= t) / len(arr) * 100, 1) if arr else None
        return dict(n=len(xs), share=round(len(xs) / len(al) * 100, 1) if al else None, p10=r(xs, -0.1), p20=r(xs, -0.2), b10=r(al, -0.1), b20=r(al, -0.2))
    single_tests = dict(
        greed=single(lambda m: m["greed"][3] >= 75, "2011-01-03"),
        fear=single(lambda m: m["fear"][3] <= 25, "2011-01-03"),
        pc_low=single(lambda m: m["pc"][4] <= 10),
        pc_high=single(lambda m: m["pc"][4] >= 90),
        rsi40=single(lambda m: m["rsi"][3] <= 40),
        rsi70=single(lambda m: m["rsi"][3] >= 70),
        krw_up=single(lambda m: m["krw"][3] >= 0.05),
        krw_dn=single(lambda m: m["krw"][3] <= -0.05),
        vix25=single(lambda m: m["vix"][3] >= 25),
        qqq_dn=single(lambda m: m["trend"][4] <= -0.025),
        qqq_hot=single(lambda m: m["dev"][4] >= 80),
        # 금리 기대 (FedWatch 대체 검증): 2년 국채 - 기준금리. 음수 = 시장이 인하를 예상, 양수 = 인상 예상
        fw_cut=single(lambda m, i: fs(i) <= -0.5, "1991-01-02"),
        fw_hike=single(lambda m, i: fs(i) >= 0.5, "1991-01-02"),
        fw_swing=single(lambda m, i: fs(i) - fs(B["back"](i, 91)) <= -0.5, "1991-01-02"),
        fw_mid=single(lambda m, i: -0.5 < fs(i) < 0.5, "1991-01-02"))
    fsw = []
    for i2 in range(max(0, N - 800), N, 5):
        try: fsw.append([d[i2], round(fs(i2), 3), A["DFF"][i2], A["DGS2"][i2]])
        except Exception: pass
    out = dict(ts=int(time.time()), raw_ts=R.get("ts"), memory=MEMORY, t_cap=T_CAP, single=single_tests, fedspread=fsw, today=today, recent=recent, weekly=weekly, stats=stats, base=base, episodes=episodes,
               buf_q=[[x[3], round(x[2], 3)] for x in B["qs"]][-12:], mavg_last=[[m_, round(B["mavg"][m_], 2)] for m_ in sorted(B["mavg"])[-30:]])
    json.dump(out, open(os.path.join(ROOT, "crash.json"), "w"), ensure_ascii=False, separators=(",", ":"))
    g = today["g"]
    print("대폭락 조짐", d[i], "연료 %.0f 균열 %.0f 불씨 %.0f →" % (F, C, T), GRADES[g] if g is not None else "—", "(오늘 하루 기준", GRADES[today["g_raw"]] if today["g_raw"] is not None else "—", ")")


if __name__ == "__main__":
    main()
