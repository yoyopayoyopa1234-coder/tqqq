"""한국 주식 일·주·월봉 → <이름>_data.json (SOXL·QLD·KORU·SCHD·QQQI·XLK)"""
import json, os, sys
from datetime import datetime, timezone
sys.path.insert(0, os.path.dirname(__file__))
from yahoo_data import yahoo

STOCKS = [("SOXL", "SOXL", "soxl_data.json"), ("QLD", "QLD", "qld_data.json"), ("KORU", "KORU", "koru_data.json"), ("SCHD", "SCHD", "schd_data.json"), ("QQQI", "QQQI", "qqqi_data.json"), ("XLK", "XLK", "xlk_data.json")]

def fix_bars(bars, daily):
    """야후 주·월봉의 튀는 값(예: QLD 2024-09 고가 94.33)을 같은 기간 일봉으로 다시 계산."""
    if not daily:
        return bars
    for i, b in enumerate(bars):
        c = b[4]
        if c and all(v is not None and 0.6 * c <= v <= 1.6 * c for v in b[1:4]):
            continue
        end = bars[i + 1][0] if i + 1 < len(bars) else float("inf")
        seg = [d for d in daily if b[0] <= d[0] < end]
        if seg:
            b[1], b[2], b[3] = seg[0][1], max(d[2] for d in seg), min(d[3] for d in seg)
            print("fixed", b[0], b[1:5])
    return bars

def main():
    for key, sym, fn in STOCKS:
        out = {"updated": datetime.now(timezone.utc).isoformat(timespec="minutes"), "ohlc": {}}
        for iv, rng in (("1d", None), ("1wk", None), ("1mo", "20y")):
            try:
                out["ohlc"][f"{key}_{iv}"] = yahoo(sym, iv, rng); print(key, iv, len(out["ohlc"][f"{key}_{iv}"]))
            except Exception as e:
                print("FAIL", key, iv, e)
        for iv in ("1wk", "1mo"):
            k = f"{key}_{iv}"
            if k in out["ohlc"]:
                out["ohlc"][k] = fix_bars(out["ohlc"][k], out["ohlc"].get(f"{key}_1d"))
        if len(out["ohlc"]) == 3:
            json.dump(out, open(fn, "w"), separators=(",", ":"))
        else:
            print(key, "일부 시세 실패 — 기존 파일 유지")

if __name__ == "__main__":
    main()
