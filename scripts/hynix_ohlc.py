"""한국 주식 일·주·월봉 → <이름>_data.json (SK하이닉스·SOXL)"""
import json, os, sys
from datetime import datetime, timezone
sys.path.insert(0, os.path.dirname(__file__))
from yahoo_data import yahoo

STOCKS = [("HYNIX", "000660.KS", "hynix_data.json"), ("SOXL", "SOXL", "soxl_data.json")]

def main():
    for key, sym, fn in STOCKS:
        out = {"updated": datetime.now(timezone.utc).isoformat(timespec="minutes"), "ohlc": {}}
        for iv, rng in (("1d", None), ("1wk", None), ("1mo", "20y")):
            try:
                out["ohlc"][f"{key}_{iv}"] = yahoo(sym, iv, rng); print(key, iv, len(out["ohlc"][f"{key}_{iv}"]))
            except Exception as e:
                print("FAIL", key, iv, e)
        if len(out["ohlc"]) == 3:
            json.dump(out, open(fn, "w"), separators=(",", ":"))
        else:
            print(key, "일부 시세 실패 — 기존 파일 유지")

if __name__ == "__main__":
    main()
