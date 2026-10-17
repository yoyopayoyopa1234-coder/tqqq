"""참고 사이트(AgiTQ)와 TradingView 공개 페이지를 열어 수치를 텍스트로 저장 (검증용)."""
import json, os, re, time
from playwright.sync_api import sync_playwright
OUT = "captures"; os.makedirs(OUT, exist_ok=True)
PAGES = [
    ("agitq", "https://0x7f-core.github.io/AgiTQ-Android/", 25),
    ("tv_spx_tech", "https://www.tradingview.com/symbols/SP-SPX/technicals/", 15),
    ("tv_qqq_tech", "https://www.tradingview.com/symbols/NASDAQ-QQQ/technicals/", 15),
    ("tv_tqqq_tech", "https://www.tradingview.com/symbols/NASDAQ-TQQQ/technicals/", 15),
    ("tv_spx", "https://www.tradingview.com/symbols/SP-SPX/", 10),
    ("tv_qqq", "https://www.tradingview.com/symbols/NASDAQ-QQQ/", 10),
    ("tv_tqqq", "https://www.tradingview.com/symbols/NASDAQ-TQQQ/", 10),
]
res = {}
with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": 1280, "height": 2200}, locale="en-US",
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36")
    pg = ctx.new_page()
    for name, url, wait in PAGES:
        try:
            pg.goto(url, wait_until="domcontentloaded", timeout=60000); time.sleep(wait)
            if "technicals" in url:
                for lab in ("1 day", "1D"):
                    try: pg.get_by_role("button", name=lab).first.click(timeout=2000); time.sleep(3); break
                    except Exception: pass
            txt = pg.evaluate("() => document.body.innerText")
            res[name] = {"url": url, "text": re.sub(r"[ \t]+", " ", txt)[:20000]}
            pg.screenshot(path=f"{OUT}/{name}.png", full_page=False)
        except Exception as e:
            res[name] = {"url": url, "error": str(e)[:300]}
    b.close()
res["_at"] = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
json.dump(res, open(f"{OUT}/verify.json", "w"), ensure_ascii=False, indent=1)
print({k: (len(v.get("text", "")) if isinstance(v, dict) else v) for k, v in res.items()})

# ── 대조 요약 + 검증 분석 ──
from datetime import datetime, timezone, timedelta
KST = timezone(timedelta(hours=9))
def num(x): return float(x.replace(",", "").replace("−", "-"))
def tv_vals(price_txt, tech_txt):
    m1 = re.search(r"\n([\d,]+\.\d+)\s*(?:POINT|USD)", price_txt)
    m2 = re.search(r"Simple Moving Average \(200\)\s+([\d,]+\.\d+)", tech_txt)
    return (num(m1.group(1)) if m1 else None, num(m2.group(1)) if m2 else None)
def mkt(price_txt):
    if re.search(r"Market open", price_txt): return "open"
    if re.search(r"Market closed|At close", price_txt): return "closed"
    if re.search(r"Pre-market|Post-market|After hours", price_txt, re.I): return "extended"
    return "unknown"
try: tq = json.load(open("tq.json"))
except Exception: tq = {}
ag_lines = [l.strip() for l in res.get("agitq", {}).get("text", "").split("\n") if l.strip() and "새로고침" not in l]
cut = next((i for i, l in enumerate(ag_lines) if "(QQQ)" in l), len(ag_lines))
ag_part = {"spx": " ".join(ag_lines[:cut]), "qqq": " ".join(ag_lines[cut:])}
def ag_state(t):
    if re.search(r"보유", t): return "IN"
    if re.search(r"대피|전량|매도|SGOV", t): return "OUT"
    return None
def g(t, rx):
    m = re.search(rx, t); return float(m.group(1)) if m else None

items, checks, notes = {}, [], []
market = mkt(res.get("tv_spx", {}).get("text", ""))
px_tol = 0.15 if market == "open" else 0.02     # 장중엔 시세 시점 차이 허용
for key, pn, tn, band, label in (("spx", "tv_spx", "tv_spx_tech", 0.025, "SPX"), ("qqq", "tv_qqq", "tv_qqq_tech", 0.02, "QQQ")):
    px, ma = tv_vals(res.get(pn, {}).get("text", ""), res.get(tn, {}).get("text", ""))
    R = tq.get(key, {}); cy = R.get("cycle") or {}
    it = {"tv_px": px, "tv_ma": ma, "my_px": R.get("idx"), "my_ma": R.get("ma200"), "my_zone": R.get("zone"), "my_state": R.get("state")}
    if px and ma:
        it["tv_up"], it["tv_lo"] = round(ma * (1 + band), 2), round(ma * (1 - band), 2)
        it["tv_zone"] = "above" if px > ma * (1 + band) else ("below" if px < ma * (1 - band) else "band")
        it["tv_dist_up"] = round((px / (ma * (1 + band)) - 1) * 100, 2); it["tv_dist_lo"] = round((px / (ma * (1 - band)) - 1) * 100, 2)
    if px and R.get("idx"):
        d = (R["idx"] / px - 1) * 100; it["px_diff_pct"] = round(d, 3)
        checks.append((f"{label} 가격", abs(d) <= px_tol, f"{d:+.3f}%"))
    if ma and R.get("ma200"):
        d = (R["ma200"] / ma - 1) * 100; it["ma_diff_pct"] = round(d, 3)
        checks.append((f"{label} 200일선", abs(d) <= 0.05, f"{d:+.3f}%"))
    if it.get("tv_zone"):
        it["zone_match"] = it["tv_zone"] == R.get("zone")
        checks.append((f"{label} 밴드 위치", it["zone_match"], f"TV {it['tv_zone']} / 사이트 {R.get('zone')}"))
    t = ag_part[key]; it["ag_state"] = ag_state(t); it["ag_days"] = g(t, r"상단 밴드 위 (\d+)일"); it["ag_dd"] = g(t, r"최고점 대비 (-?[\d.]+)%")
    it["my_days"] = cy.get("tdays"); it["my_dd"] = cy.get("dd") if cy.get("dd") is not None else (round((R["tqqq"] / cy["peak"] - 1) * 100, 2) if cy.get("peak") else None)
    if it["ag_state"]: checks.append((f"{label} 보유/대피 (AgiTQ)", it["ag_state"] == R.get("state"), f"AgiTQ {it['ag_state']} / 사이트 {R.get('state')}"))
    if it["ag_days"] is not None and it["my_days"] is not None:
        diff = int(it["ag_days"] - it["my_days"]); checks.append((f"{label} 상단 위 일수 (AgiTQ)", abs(diff) <= 1, f"{int(it['ag_days'])} / {it['my_days']}일"))
    if it["ag_dd"] is not None and it["my_dd"] is not None:
        checks.append((f"{label} TQQQ 고점 대비 (AgiTQ)", abs(it["ag_dd"] - it["my_dd"]) <= 0.3 if market != "open" else abs(it["ag_dd"] - it["my_dd"]) <= 1.5, f"{it['ag_dd']:.1f}% / {it['my_dd']:.1f}%"))
    items[key] = it

tq_tv = None
m = re.search(r"\n([\d,]+\.\d+)\s*USD", res.get("tv_tqqq", {}).get("text", ""))
if m: tq_tv = num(m.group(1))
tq_my = tq.get("spx", {}).get("tqqq")
if tq_tv and tq_my: checks.append(("TQQQ 가격", abs(tq_my / tq_tv - 1) * 100 <= (0.3 if market == "open" else 0.05), f"{(tq_my / tq_tv - 1) * 100:+.3f}%"))
fg_ag = g(" ".join(ag_lines), r"현재 (\d+)"); fg_my = (tq.get("fg") or {}).get("score")
if fg_ag is not None and fg_my is not None: checks.append(("공포·탐욕 지수", abs(fg_ag - fg_my) <= 2, f"AgiTQ {fg_ag:.0f} / 사이트 {fg_my:.0f}"))

fails = [c for c in checks if not c[1]]
signal_keys = [c for c in checks if "밴드 위치" in c[0] or "보유/대피" in c[0]]
signal_ok = all(c[1] for c in signal_keys) and bool(signal_keys)
if not checks:
    verdict, level = "검증 실패 — TradingView·AgiTQ 페이지를 읽지 못했습니다. 다음 회차에 다시 확인합니다.", "warn"
elif not fails:
    verdict, level = f"전부 일치 ({len(checks)}/{len(checks)}) — 신호판 수치와 판단을 그대로 믿어도 됩니다.", "ok"
elif signal_ok:
    verdict, level = f"신호 판단은 일치, 수치 {len(fails)}건 차이 — 매수·탈출 판단에는 영향이 없습니다.", "minor"
else:
    verdict, level = f"신호 판단 불일치 {sum(1 for c in signal_keys if not c[1])}건 — 아래 차이를 확인하고, TradingView 화면을 직접 보세요.", "bad"
# 해설
for key, label in (("spx", "SPX"), ("qqq", "QQQ")):
    it = items.get(key, {})
    if it.get("tv_zone"):
        z = {"above": "상단 밴드 위", "band": "밴드 안", "below": "하단 밴드 아래"}[it["tv_zone"]]
        edge = it["tv_dist_up"] if it["tv_zone"] != "below" else it["tv_dist_lo"]
        near = (it["tv_zone"] == "above" and it["tv_dist_up"] < 1.0) or (it["tv_zone"] == "band" and min(abs(it["tv_dist_up"]), abs(it["tv_dist_lo"])) < 0.5) or (it["tv_zone"] == "below" and it["tv_dist_lo"] > -1.0)
        notes.append(f"{label}: TradingView 기준 {z} (상단 대비 {it['tv_dist_up']:+.2f}%, 하단 대비 {it['tv_dist_lo']:+.2f}%)." + (" 밴드 경계에 가까워 종가에 따라 신호가 바뀔 수 있습니다." if near else ""))
if market == "open": notes.append("미국 장중이라 TradingView 실시간가와 사이트 값 사이에 몇 분의 시차가 있을 수 있습니다. 신호는 종가 기준으로 확정됩니다.")
for c in fails: notes.append(f"차이: {c[0]} — {c[2]}")
if any(re.search(r"SPYM 추가 매수", l) for l in ag_lines): notes.append("AgiTQ의 'SPYM 추가 매수'는 보내주신 규칙에 없는 항목이라 대조하지 않았습니다.")

now = datetime.now(timezone.utc)
summ = {"at": now.isoformat(timespec="minutes"), "at_kst": now.astimezone(KST).strftime("%m/%d %H:%M"), "market": market,
        "verdict": verdict, "level": level, "checks": [{"name": a, "ok": b, "detail": c} for a, b, c in checks],
        "notes": notes, "items": items, "tqqq_tv": tq_tv, "tqqq_my": tq_my, "agitq": ag_lines[:20]}
try: prev = json.load(open("verify_summary.json")).get("history", [])
except Exception: prev = []
summ["history"] = (prev + [{"at": summ["at_kst"], "level": level, "ok": len(checks) - len(fails), "n": len(checks)}])[-48:]
json.dump(summ, open("verify_summary.json", "w"), ensure_ascii=False, indent=1)
print(verdict); [print(" ", n) for n in notes]
