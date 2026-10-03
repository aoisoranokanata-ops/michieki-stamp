"""国土数値情報「鉄道」(N02) の駅データ → data/stations.json 変換スクリプト

駅モードの「駅名から探す」入力補助に使う軽量データを作る。
使い方（michieki-stamp/ で実行）:
    python tools/convert_stations.py            # tools/raw/ の zip を使う（無ければ取得）
    python tools/convert_stations.py --refresh  # zip を取り直す

出典: 国土数値情報（鉄道データ）（国土交通省） https://nlftp.mlit.go.jp/ksj/gml/datalist/KsjTmplt-N02-2024.html
利用条件: CC BY 4.0（2020年以降のデータ）。加工して作成した旨と出典を表示する。
外部ライブラリ不要（標準ライブラリのみ）。
"""
import hashlib
import json
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "tools" / "raw"
OUT = ROOT / "data" / "stations.json"
EDITION = "N02-24"   # データ基準年度 2025年度（令和7年度）版・2024年12月31日時点
ZIP_URL = f"https://nlftp.mlit.go.jp/ksj/gml/data/N02/{EDITION}/{EDITION}_GML.zip"
PAGE_URL = "https://nlftp.mlit.go.jp/ksj/gml/datalist/KsjTmplt-N02-2024.html"

# 事業者名を一般的な呼び方にそろえる（元の名称は検索語にも残す）
OPERATOR_SHORT = {
    "北海道旅客鉄道": "JR北海道", "東日本旅客鉄道": "JR東日本", "東海旅客鉄道": "JR東海",
    "西日本旅客鉄道": "JR西日本", "四国旅客鉄道": "JR四国", "九州旅客鉄道": "JR九州",
    "東京地下鉄": "東京メトロ", "東京都": "都営", "大阪市高速電気軌道": "Osaka Metro",
}


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    zpath = RAW / f"{EDITION}_GML.zip"
    if "--refresh" in sys.argv or not zpath.exists():
        req = urllib.request.Request(ZIP_URL, headers={"User-Agent": "michieki-stamp-convert/1.0 (personal use)"})
        zpath.write_bytes(urllib.request.urlopen(req, timeout=300).read())
    feats = json.loads(zipfile.ZipFile(zpath).read(f"UTF-8/{EDITION}_Station.geojson"))["features"]

    operators, lines, seen, rows = [], [], set(), []
    def idx(lst, v):
        if v not in lst:
            lst.append(v)
        return lst.index(v)

    for f in feats:
        pr = f["properties"]
        name, op, line = pr["N02_005"], pr["N02_004"], pr["N02_003"]
        key = (name, op, line)
        if key in seen:          # 同じ駅・同じ路線の重複（ホームが分かれている等）は1つにまとめる
            continue
        seen.add(key)
        coords = f["geometry"]["coordinates"]   # ホームを表す線。中間の点を代表点にする
        lng, lat = coords[len(coords) // 2] if len(coords) > 2 else [(coords[0][i] + coords[-1][i]) / 2 for i in (0, 1)]
        rows.append([name, idx(operators, OPERATOR_SHORT.get(op, op)), idx(lines, line),
                     round(lat, 5), round(lng, 5), int(pr["N02_002"])])

    rows.sort(key=lambda r: (r[0], r[1], r[2]))
    digest = hashlib.sha1(json.dumps(rows, ensure_ascii=False).encode()).hexdigest()[:8]
    doc = {
        "version": f"{EDITION}-{digest}",
        "license": "CC-BY-4.0",
        "licenseUrl": "https://creativecommons.org/licenses/by/4.0/deed.ja",
        "attribution": "「国土数値情報（鉄道データ）」（国土交通省）を加工して作成",
        "source": PAGE_URL,
        "basis": "2024年12月31日時点（2025年度版）",
        "kinds": {"1": "新幹線", "2": "JR在来線", "3": "公営鉄道", "4": "民営鉄道", "5": "第三セクター"},
        "fields": ["name", "operator", "line", "lat", "lng", "kind"],
        "operators": operators,
        "lines": lines,
        "stations": rows,
        "generated": time.strftime("%Y-%m-%d"),
    }
    OUT.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{len(rows)} 駅・路線 → {OUT}（{OUT.stat().st_size // 1024} KB）事業者 {len(operators)}・路線 {len(lines)}")


if __name__ == "__main__":
    main()
