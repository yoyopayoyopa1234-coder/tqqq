"""CNN 공포·탐욕 지수 일별 기록 → fg_hist.json (2011~ 과거값에 CNN 최근 1년치를 매번 덮어써 합침)."""
import json, urllib.request
from datetime import datetime, timezone

FN = "fg_hist.json"

def main():
    try:
        h = json.load(open(FN))
    except Exception:
        h = {"d": [], "v": []}
    data = dict(zip(h["d"], h["v"]))
    req = urllib.request.Request("https://production.dataviz.cnn.io/index/fearandgreed/graphdata",
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126 Safari/537.36",
                 "Referer": "https://edition.cnn.com/", "Origin": "https://edition.cnn.com", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        j = json.loads(r.read())
    n0 = len(data)
    for p in (j.get("fear_and_greed_historical") or {}).get("data", []):
        try:
            data[datetime.fromtimestamp(p["x"] / 1000, timezone.utc).date().isoformat()] = round(float(p["y"]), 1)
        except Exception:
            pass
    fg = j.get("fear_and_greed") or {}
    if fg.get("score") is not None and fg.get("timestamp"):
        try:
            data[datetime.fromisoformat(fg["timestamp"].replace("Z", "+00:00")).date().isoformat()] = round(float(fg["score"]), 1)
        except Exception:
            pass
    ks = sorted(data)
    h.update({"d": ks, "v": [data[k] for k in ks], "updated": datetime.now(timezone.utc).isoformat(timespec="minutes")})
    json.dump(h, open(FN, "w"), separators=(",", ":"), ensure_ascii=False)
    print("fg_hist", n0, "→", len(ks), ks[-1])

if __name__ == "__main__":
    main()
