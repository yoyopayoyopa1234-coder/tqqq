"""TQQQ 200일선 밴드 전략 (SPX ±2.5% / QQQ ±2%) 신호 계산 → tq.json + GitHub 알림.

- 밴드 상단 돌파 → 매수(보유 사이클 시작), 밴드 안 → 기존 상태 유지, 하단 이탈 → 전량 탈출(SGOV)
- 사이클 TQQQ 최고점 대비 -25% → TS 발동 (SPX판은 발동 후 최고점 리셋, 반복 발동)
- 사이클 기준 TQQQ 수익률로 소익절(+10/25/50%)·대익절(+100/200/400/800%…) 도달 표시
"""
import json, os, sys, time, urllib.request
from datetime import datetime, timezone, timedelta
sys.path.insert(0, os.path.dirname(__file__))
from yahoo_data import yahoo, get
from indicators import sma

KST = timezone(timedelta(hours=9))
NOW = datetime.now(timezone.utc)
SMALL = [10, 25, 50]
BIG = [100 * 2 ** k for k in range(8)]          # 100, 200, 400, 800 ...

def daily(sym, rng="20y"):
    r = yahoo(sym, "1d", rng)
    return {datetime.fromtimestamp(x[0], timezone.utc).strftime("%Y-%m-%d"): x[4] for x in r}

def run_strategy(name, idx, tq, band, multi_ts):
    dates = sorted(d for d in idx if d in tq)
    c = [idx[d] for d in dates]; t = [tq[d] for d in dates]
    ma = sma(c, 200)
    state, cycles, cur = "OUT", [], None
    for i, d in enumerate(dates):
        if ma[i] is None: continue
        up, lo = ma[i] * (1 + band), ma[i] * (1 - band)
        if state == "OUT" and c[i] > up:
            state = "IN"
            cur = {"entry_date": d, "entry_tq": t[i], "entry_idx": c[i], "peak": t[i], "ts_peak": t[i], "ts": [], "hit": [], "max_ret": 0.0}
        elif state == "IN":
            if t[i] > cur["ts_peak"]:
                cur["ts_peak"] = t[i]
                if multi_ts: cur["hit"] = []                # V2만 새 고점에서 재설정 (V1은 사이클당 최초 1회)
            cur["peak"] = max(cur["peak"], t[i])
            cur["max_ret"] = max(cur["max_ret"], (t[i] / cur["entry_tq"] - 1) * 100)
            if multi_ts:
                # SPX V2: 고점 대비 −25%마다 발동, 발동 후 임시 최고점을 그 가격으로 리셋해 반복
                if t[i] <= cur["ts_peak"] * 0.75:
                    cur["ts"].append({"date": d, "price": t[i], "from_peak": cur["ts_peak"], "level": 25})
                    cur["ts_peak"] = t[i]; cur["hit"] = []
            else:
                # QQQ(V1): 사이클 최고점 대비 −25%에서 사이클당 최초 1회만 발동 (원문 "최초 1번 정도")
                for lv in (25,):
                    if lv not in cur.setdefault("hit", []) and t[i] <= cur["ts_peak"] * (1 - lv / 100):
                        cur["hit"].append(lv)
                        cur["ts"].append({"date": d, "price": t[i], "from_peak": cur["ts_peak"], "level": lv})
            if c[i] < lo:
                state = "OUT"
                cur.update(exit_date=d, exit_tq=t[i], exit_idx=c[i], ret=(t[i] / cur["entry_tq"] - 1) * 100)
                cycles.append(cur); cur = None
    i = len(dates) - 1
    up, lo = ma[i] * (1 + band), ma[i] * (1 - band)
    pos = (c[i] - lo) / (up - lo)                      # 0=하단, 1=상단
    zone = "above" if c[i] > up else ("below" if c[i] < lo else "band")
    out = {
        "name": name, "band": band, "multi_ts": multi_ts, "date": dates[i],
        "idx": round(c[i], 2), "ma200": round(ma[i], 2), "up": round(up, 2), "lo": round(lo, 2),
        "dist_ma": round((c[i] / ma[i] - 1) * 100, 2), "to_up": round((up / c[i] - 1) * 100, 2), "to_lo": round((lo / c[i] - 1) * 100, 2),
        "pos": round(pos, 3), "zone": zone, "state": state, "tqqq": round(t[i], 2),
        "cycles": [{k: (round(v, 2) if isinstance(v, float) else v) for k, v in cy.items() if k not in ("peak", "ts_peak", "hit")} | {"ts_n": len(cy["ts"])} for cy in cycles[-12:]],
    }
    if cur:
        ret = (t[i] / cur["entry_tq"] - 1) * 100
        if multi_ts:
            ts_level = 25; ts_line = cur["ts_peak"] * 0.75
        else:
            nxt = next((lv for lv in (25,) if lv not in cur.get("hit", [])), None)
            ts_level = nxt; ts_line = cur["ts_peak"] * (1 - nxt / 100) if nxt else None
        hit_small = [x for x in SMALL if cur["max_ret"] >= x]; hit_big = [x for x in BIG if cur["max_ret"] >= x]
        nxt_small = next((x for x in SMALL if x not in hit_small), None); nxt_big = next((x for x in BIG if x not in hit_big), None)
        out["cycle"] = {
            "entry_date": cur["entry_date"], "entry_tq": round(cur["entry_tq"], 2), "tdays": sum(1 for d in dates if d >= cur["entry_date"]), "days": (datetime.fromisoformat(dates[i]) - datetime.fromisoformat(cur["entry_date"])).days,
            "ret": round(ret, 2), "max_ret": round(cur["max_ret"], 2), "peak": round(cur["peak"], 2),
            "ts_peak": round(cur["ts_peak"], 2), "ts_line": round(ts_line, 2) if ts_line else None, "ts_level": ts_level,
            "ts_hit": cur.get("hit", []), "dd": round((t[i] / cur["ts_peak"] - 1) * 100, 2),
            "ts": [{k: round(v, 2) if isinstance(v, float) else v for k, v in x.items()} for x in cur["ts"]],
            "hit_small": hit_small, "hit_big": hit_big, "next_small": nxt_small, "next_big": nxt_big,
            "next_small_px": round(cur["entry_tq"] * (1 + nxt_small / 100), 2) if nxt_small else None,
            "next_big_px": round(cur["entry_tq"] * (1 + nxt_big / 100), 2) if nxt_big else None,
        }
    # 차트용 최근 2년
    k0 = max(0, len(dates) - 504)
    out["chart"] = {"d": dates[k0:], "idx": [round(x, 2) for x in c[k0:]], "ma": [round(x, 2) if x else None for x in ma[k0:]], "tq": [round(x, 2) for x in t[k0:]]}
    return out

def fear_greed():
    try:
        req = urllib.request.Request("https://production.dataviz.cnn.io/index/fearandgreed/graphdata",
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126 Safari/537.36",
                     "Referer": "https://edition.cnn.com/", "Origin": "https://edition.cnn.com", "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as r:
            j = json.loads(r.read())
        fg = j["fear_and_greed"]
        return {"score": round(fg["score"], 1), "rating": fg["rating"], "prev_week": round(fg.get("previous_1_week", 0), 1), "prev_month": round(fg.get("previous_1_month", 0), 1)}
    except Exception as e:
        return {"error": str(e)[:100]}

def issue(title, body):
    tok, repo = os.environ.get("GH_TOKEN"), os.environ.get("GITHUB_REPOSITORY")
    if not tok or not repo: print("알림 생략:", title); return
    req = urllib.request.Request(f"https://api.github.com/repos/{repo}/issues", method="POST",
        data=json.dumps({"title": title, "body": body + "\n\n[TQQQ 신호판 보기](https://yoyopayoyopa1234-coder.github.io/tqqq/)\n\n@yoyopayoyopa1234-coder\n\n_규칙 기반 신호 알림이며 투자 자문이 아닙니다._"}).encode(),
        headers={"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json", "User-Agent": "tq-alerts"})
    with urllib.request.urlopen(req, timeout=30) as r: print("이슈:", json.loads(r.read())["html_url"])

def main():
    tq = daily("TQQQ"); spx = daily("%5EGSPC")
    extra = {}
    for s in ("SPYM", "SGOV"):
        try:
            r = yahoo(s, "1d", "1mo"); extra[s] = {"px": round(r[-1][4], 2), "chg": round((r[-1][4] / r[-2][4] - 1) * 100, 2)}
        except Exception as e: extra[s] = {"error": str(e)[:60]}
    S = run_strategy("SPX", spx, tq, 0.025, True)
    out = {"updated": NOW.isoformat(timespec="minutes"), "spx": S, "fg": fear_greed(), "extra": extra}
    try:
        out["qqq"] = run_strategy("QQQ", daily("QQQ"), tq, 0.02, False)     # 200큐큐단 β (qqq200.html)
    except Exception as e:
        print("QQQ 신호 실패", e)
    try:
        from tq_bt40 import run as bt40, run_qqq
        out["bt40"] = bt40()
        out["bt40q"] = run_qqq()
    except Exception as e:
        print("40년 백테스트 실패", e)
    json.dump(out, open("tq.json", "w"), ensure_ascii=False, separators=(",", ":"))
    print("SPX", S["state"], S["zone"], S["idx"], S["up"], S["lo"])

    # ── 알림: 상태 변화 감지 ──
    sp = "tq_state.json"
    prev = json.load(open(sp)) if os.path.exists(sp) else None
    snap = {}
    for k, R, label in (("spx", S, "SPX ±2.5%"),):
        cy = R.get("cycle") or {}
        snap[k] = {"state": R["state"], "entry": cy.get("entry_date"), "ts_n": len(cy.get("ts", [])),
                   "small": cy.get("hit_small", []), "big": cy.get("hit_big", [])}
        if prev is None or k not in prev: continue
        p = prev[k]; line = f"{label} · {R['name']} {R['idx']:,} (200일선 {R['ma200']:,}, 밴드 {R['lo']:,}~{R['up']:,}) · TQQQ {R['tqqq']}"
        if R["state"] == "IN" and p["state"] == "OUT":
            issue(f"🟢 [{label}] 매수 신호 — 상단 밴드 돌파", f"**{R['name']}가 200일선 +{R['band']*100:g}% 상단 밴드를 돌파했습니다.**\n\n{line}\n\n규칙: SGOV 현금으로 TQQQ 3분할 매수.")
        elif R["state"] == "OUT" and p["state"] == "IN":
            issue(f"🔴 [{label}] 전량 탈출 — 하단 밴드 이탈", f"**{R['name']}가 200일선 −{R['band']*100:g}% 하단 밴드를 깨고 내려갔습니다.**\n\n{line}\n\n규칙: TQQQ·SPYM 전량 매도 후 SGOV 대피.")
        elif R["state"] == "IN" and p["entry"] == snap[k]["entry"]:
            if snap[k]["ts_n"] > p["ts_n"]:
                t_ = cy["ts"][-1]
                issue(f"⚠️ [{label}] TS 발동 — TQQQ 고점 대비 −25%", f"**TQQQ {t_['price']}가 사이클 고점 {t_['from_peak']} 대비 −25%에 닿았습니다.** ({t_['date']})\n\n{line}\n\n규칙: 보유 TQQQ 수량의 50%를 SPYM으로 전환.")
            for x in set(snap[k]["big"]) - set(p["big"]):
                issue(f"💰 [{label}] 대익절 +{x}% 도달", f"**사이클 TQQQ 수익률이 +{x}%를 넘었습니다.** (진입 {cy['entry_date']} @ {cy['entry_tq']})\n\n{line}\n\n규칙: 현재 잔고의 50%를 덜어 SPYM으로 전환.")
            for x in set(snap[k]["small"]) - set(p["small"]):
                issue(f"💰 [{label}] 소익절 +{x}% 도달", f"**사이클 TQQQ 수익률이 +{x}%에 도달했습니다.** (진입 {cy['entry_date']} @ {cy['entry_tq']})\n\n{line}\n\n규칙: 현재 잔고의 10%를 덜어 SPYM으로 전환.")
    if prev is None:
        s_ = lambda R: f"{R['name']} {'보유(IN)' if R['state']=='IN' else '대피(OUT)'} · {('상단 위' if R['zone']=='above' else '밴드 안' if R['zone']=='band' else '하단 아래')}"
        issue(f"[TQQQ 신호판] 알림 설정 완료 · SPX {S['state']}",
              f"매수·전량탈출·TS·익절 신호가 새로 나오면 이렇게 알림이 옵니다.\n\n- {s_(S)}")
    json.dump(snap, open(sp, "w"), ensure_ascii=False, indent=1)

if __name__ == "__main__":
    main()
