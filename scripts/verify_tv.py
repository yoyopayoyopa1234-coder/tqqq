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

# ── 대조 요약 ──
def num(s): return float(s.replace(",", "").replace("−", "-"))
def tv_vals(price_txt, tech_txt):
    m1 = re.search(r"\n([\d,]+\.\d+)\s*(?:POINT|USD)", price_txt) or re.search(r"\|?\s*([\d,]+\.\d+)\s*\n?\s*(?:D|USD)", price_txt)
    m2 = re.search(r"Simple Moving Average \(200\)\s+([\d,]+\.\d+)", tech_txt)
    return (num(m1.group(1)) if m1 else None, num(m2.group(1)) if m2 else None)
summ = {"at": res["_at"], "items": {}}
try:
    tq = json.load(open("tq.json"))
except Exception:
    tq = {}
for key, pn, tn, band in (("spx", "tv_spx", "tv_spx_tech", 0.025), ("qqq", "tv_qqq", "tv_qqq_tech", 0.02)):
    px, ma = tv_vals(res.get(pn, {}).get("text", ""), res.get(tn, {}).get("text", ""))
    R = tq.get(key, {})
    it = {"tv_px": px, "tv_ma": ma, "my_px": R.get("idx"), "my_ma": R.get("ma200"), "my_date": R.get("date")}
    if px and ma:
        it["tv_up"], it["tv_lo"] = round(ma * (1 + band), 2), round(ma * (1 - band), 2)
        it["tv_zone"] = "above" if px > ma * (1 + band) else ("below" if px < ma * (1 - band) else "band")
        if R.get("ma200"):
            it["ma_diff_pct"] = round((R["ma200"] / ma - 1) * 100, 3)
            it["px_diff_pct"] = round((R["idx"] / px - 1) * 100, 3)
            it["zone_match"] = it["tv_zone"] == R.get("zone")
    summ["items"][key] = it
tqx = res.get("tv_tqqq", {}).get("text", "")
m = re.search(r"TQQQ\s*\|?\s*\n?([\d,]+\.\d+)", tqx)
summ["tqqq_tv"] = num(m.group(1)) if m else None
summ["tqqq_my"] = tq.get("spx", {}).get("tqqq")
ag = res.get("agitq", {}).get("text", "")
summ["agitq"] = [l.strip() for l in ag.split("\n") if l.strip() and "새로고침" not in l][:20]
json.dump(summ, open("verify_summary.json", "w"), ensure_ascii=False, indent=1)
print(json.dumps(summ, ensure_ascii=False)[:1500])
