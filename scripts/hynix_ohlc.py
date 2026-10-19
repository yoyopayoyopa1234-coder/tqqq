"""SK하이닉스(000660.KS) 일·주·월봉 → hynix_data.json"""
import json, os, sys
from datetime import datetime, timezone
sys.path.insert(0, os.path.dirname(__file__))
from yahoo_data import yahoo

def main():
    out = {"updated": datetime.now(timezone.utc).isoformat(timespec="minutes"), "ohlc": {}}
    for key, iv, rng in (("HYNIX_1d", "1d", "5y"), ("HYNIX_1wk", "1wk", "10y"), ("HYNIX_1mo", "1mo", "20y")):
        try:
            out["ohlc"][key] = yahoo("000660.KS", iv, rng); print(key, len(out["ohlc"][key]), out["ohlc"][key][-1])
        except Exception as e:
            print("FAIL", key, e)
    if len(out["ohlc"]) < 3:
        raise SystemExit("일부 시세를 받지 못함 — 기존 파일 유지")
    json.dump(out, open("hynix_data.json", "w"), separators=(",", ":"))

if __name__ == "__main__":
    main()
