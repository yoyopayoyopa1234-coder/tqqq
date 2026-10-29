"""일·주·월봉 → <이름>_data.json (SOXL·KORU·S&P500)"""
import json, os, sys
from datetime import datetime, timezone
sys.path.insert(0, os.path.dirname(__file__))
from yahoo_data import yahoo

STOCKS = [("SOXL", "SOXL", "soxl_data.json"), ("KORU", "KORU", "koru_data.json"), ("SPX", "%5EGSPC", "spx_data.json")]
RANGES = {"SPX": {"1d": "p473385600", "1wk": "p473385600", "1mo": "p473385600"}}   # 1985-01-01부터   # S&P500은 길게 (5·10·15년 버튼용)

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
            rng = RANGES.get(key, {}).get(iv, rng)
            try:
                out["ohlc"][f"{key}_{iv}"] = yahoo(sym, iv, rng); print(key, iv, len(out["ohlc"][f"{key}_{iv}"]))
            except Exception as e:
                print("FAIL", key, iv, e); out.setdefault("err", []).append(f"{iv}: {str(e)[:200]}")
                if key == "SPX":   # ^GSPC 긴 기간이 막히면 기본 기간으로 한 번 더
                    try:
                        out["ohlc"][f"{key}_{iv}"] = yahoo(sym, iv, None if iv != "1mo" else "20y"); print(key, iv, "fallback", len(out["ohlc"][f"{key}_{iv}"]))
                    except Exception as e2:
                        out["err"].append(f"{iv} fallback: {str(e2)[:200]}")
        for iv in ("1wk", "1mo"):
            k = f"{key}_{iv}"
            if k in out["ohlc"]:
                out["ohlc"][k] = fix_bars(out["ohlc"][k], out["ohlc"].get(f"{key}_1d"))
        if len(out["ohlc"]) == 3:
            json.dump(out, open(fn, "w"), separators=(",", ":"))
        else:
            print(key, "일부 시세 실패 — 기존 파일 유지")
            if key == "SPX": json.dump({"updated": out["updated"], "err": out.get("err", []), "ohlc": out["ohlc"]}, open(fn, "w"), separators=(",", ":"))

if __name__ == "__main__":
    main()
