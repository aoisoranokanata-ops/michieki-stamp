"""道の駅一覧（国交省 Excel）→ data/michinoeki.json 変換スクリプト

使い方（michieki-stamp/ で実行）:
    python tools/convert.py            # キャッシュがあればそれを使う
    python tools/convert.py --refresh  # Excel・OSM・ジオコーディングを取り直す

データの出どころ:
  - 駅名・読み・所在地・登録回: 国土交通省「道の駅」一覧（公共データ利用規約1.0 / CC BY 4.0互換）
  - 座標（優先）: OpenStreetMap（ODbL）。名前と市町村で突き合わせる
  - 座標（代替）: 国土地理院 住所検索API による市町村の代表点（精度 'city'）

外部ライブラリ不要（標準ライブラリのみ）。
"""
import hashlib
import json
import math
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "tools" / "raw"
OUT = ROOT / "data" / "michinoeki.json"

EXCEL_URL = "https://www.mlit.go.jp/road/Michi-no-Eki/file/list.xlsx"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
GSI_URL = "https://msearch.gsi.go.jp/address-search/AddressSearch"
UA = "michieki-stamp-convert/1.0 (personal use)"

PREFS = ["北海道", "青森県", "岩手県", "宮城県", "秋田県", "山形県", "福島県", "茨城県", "栃木県", "群馬県",
         "埼玉県", "千葉県", "東京都", "神奈川県", "新潟県", "富山県", "石川県", "福井県", "山梨県", "長野県",
         "岐阜県", "静岡県", "愛知県", "三重県", "滋賀県", "京都府", "大阪府", "兵庫県", "奈良県", "和歌山県",
         "鳥取県", "島根県", "岡山県", "広島県", "山口県", "徳島県", "香川県", "愛媛県", "高知県", "福岡県",
         "佐賀県", "長崎県", "熊本県", "大分県", "宮崎県", "鹿児島県", "沖縄県"]

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REFRESH = "--refresh" in sys.argv


def fetch(url, data=None, timeout=200):
    req = urllib.request.Request(url, data=data, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


# ---------- Excel ----------

def kata_to_hira(s):
    return "".join(chr(ord(c) - 0x60) if "ァ" <= c <= "ヶ" else c for c in s)


def read_si(si):
    """共有文字列1件 → (表記, 読み)。読みは rPh（ふりがな）で漢字部分を置き換えて作る"""
    m = NS["m"]
    base = "".join(t.text or "" for t in si.findall(f"{{{m}}}t"))
    base += "".join(t.text or "" for r in si.findall(f"{{{m}}}r") for t in r.findall(f"{{{m}}}t"))
    kana, pos = "", 0
    for rph in si.findall(f"{{{m}}}rPh"):
        sb, eb = int(rph.get("sb")), int(rph.get("eb"))
        kana += base[pos:sb] + "".join(t.text or "" for t in rph.findall(f"{{{m}}}t"))
        pos = eb
    kana += base[pos:]
    return base, kata_to_hira(kana)


def read_excel(path):
    z = zipfile.ZipFile(path)
    strings = [read_si(si) for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", NS)]
    sheet = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
    rows = []
    for r in sheet.iter(f"{{{NS['m']}}}row"):
        d = {}
        for c in r.findall("m:c", NS):
            col = re.match(r"[A-Z]+", c.get("r")).group()
            v = c.find("m:v", NS)
            if v is None:
                continue
            d[col] = strings[int(v.text)] if c.get("t") == "s" else (v.text, v.text)
        rows.append(d)
    header = [rows[0].get(k, ("", ""))[0] for k in "ABCDEF"]
    assert header[0] == "県名" and header[1].replace(" ", "") == "駅名" and header[4] == "所在地", header
    out = []
    for d in rows[1:]:
        if "B" not in d or "A" not in d:
            continue
        name, kana = d["B"]
        out.append({
            "prefecture": d["A"][0].strip(),
            "name": clean(name),
            "nameKana": clean(kana).replace(" ", ""),
            "round": d.get("C", ("", ""))[0],
            "registered": d.get("D", ("", ""))[0],
            "city": d.get("E", ("", ""))[0].strip(),
            "url": d.get("F", ("", ""))[0].strip(),
        })
    return out


def clean(s):
    s = s.replace("　", " ")
    return re.sub(r"\s+", " ", s).strip()


# ---------- 照合用の名前正規化 ----------

def norm(s):
    s = unicodedata.normalize("NFKC", s or "")
    s = s.replace("道の駅", "")
    s = re.sub(r"[～〜~].*?[～〜~]", "", s)  # 「平泉 ～黄金花咲く理想郷～」の副題を落とす
    s = re.sub(r"(駐車場|トイレ|案内板|第\d駐車場)$", "", s)
    s = re.sub(r"[\s・･\-‐ー－〜~「」『』()（）]", "", s)
    return kata_to_hira(s).lower()


def dist_km(a, b):
    lat1, lng1, lat2, lng2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


# ---------- 外部データ（キャッシュ付き） ----------

def load_osm():
    # 道の駅は highway=rest_area/services のほか、建物・駐車場・観光案内などで登録されていることも多い。
    # 全国一括だと Overpass がタイムアウトするので、タグの種類 × 地域に分けて取る
    p = RAW / "osm_raw.json"
    if REFRESH or not p.exists():
        lats, lngs = [20, 33, 34.5, 35.5, 36.5, 38, 40, 46], [122, 133, 136, 138.5, 140, 154]
        boxes = [f"({a},{c},{b},{d})" for a, b in zip(lats, lats[1:]) for c, d in zip(lngs, lngs[1:])]
        seen, els = set(), []
        for k in ["name"]:
            for b in boxes:
                q = f'[out:json][timeout:180];nwr["name"~"道の駅"]{b};out center tags;'
                for attempt in range(4):
                    try:
                        res = json.loads(fetch(OVERPASS_URL, urllib.parse.urlencode({"data": q}).encode()))
                        break
                    except urllib.error.HTTPError as e:
                        if attempt == 3:
                            raise
                        print(f"  Overpass {e.code}、再試行します: {k} {b}")
                        time.sleep(20 * (attempt + 1))
                print(f"  OSM {k} {b}: {len(res['elements'])}")
                for e in res["elements"]:
                    if (e["type"], e["id"]) not in seen:
                        seen.add((e["type"], e["id"]))
                        els.append(e)
                time.sleep(2)
        p.write_text(json.dumps({"elements": els}, ensure_ascii=False), encoding="utf-8")
    els = json.loads(p.read_text(encoding="utf-8"))["elements"]
    pts = []
    for e in els:
        name = e["tags"].get("name", "")
        lat = e.get("lat") or e.get("center", {}).get("lat")
        lng = e.get("lon") or e.get("center", {}).get("lon")
        if lat is None or name.startswith("旧"):
            continue
        pts.append({"n": norm(name), "lat": lat, "lng": lng})
    return pts


def load_geocode_cache():
    p = RAW / "gsi_cache.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() and not REFRESH else {}


def geocode_city(cache, q):
    if q in cache:
        return cache[q]
    res = json.loads(fetch(GSI_URL + "?q=" + urllib.parse.quote(q)).decode("utf-8"))
    hit = None
    for f in res:
        if f["properties"]["title"].startswith(q):
            lng, lat = f["geometry"]["coordinates"]
            hit = [lat, lng]
            break
    cache[q] = hit
    time.sleep(0.3)
    return hit


# ---------- main ----------

def main():
    RAW.mkdir(parents=True, exist_ok=True)
    xlsx = RAW / "list.xlsx"
    if REFRESH or not xlsx.exists():
        xlsx.write_bytes(fetch(EXCEL_URL))
    stations = read_excel(xlsx)
    osm = load_osm()
    cache = load_geocode_cache()

    station_norms = {norm(x["name"]) for x in stations}
    places, used_ids, stats = [], set(), {"osm": 0, "city": 0, "none": 0}
    for s in stations:
        pref = s["prefecture"]
        assert pref in PREFS, pref
        city = s["city"][len(pref):] if s["city"].startswith(pref) else s["city"]
        addr = pref + city
        # 「静岡市・藤枝市」のように複数市町村にまたがる駅は最初の市町村を代表点にする
        center = geocode_city(cache, pref + re.split(r"[・、]", city)[0]) if city else None
        n = norm(s["name"])
        near = lambda o: center and dist_km(center, (o["lat"], o["lng"])) <= 40
        # 完全一致を優先。部分一致は短すぎる名前（空文字や1文字）を除き、候補が1か所に絞れる場合だけ使う
        best = None
        exact = sorted([o for o in osm if o["n"] == n and near(o)], key=lambda o: dist_km(center, (o["lat"], o["lng"])))
        if exact:
            best = exact[0]
        elif len(n) >= 2:
            part = [o for o in osm if len(o["n"]) >= 2 and (n in o["n"] or o["n"] in n) and near(o)
                    and o["n"] not in station_norms]  # 別の駅の名前そのものの点は横取りしない
            spots = {(round(o["lat"], 2), round(o["lng"], 2)) for o in part}
            if len(spots) == 1:
                best = part[0]
        if best:
            lat, lng, prec = best["lat"], best["lng"], "osm"
        elif center:
            lat, lng, prec = center[0], center[1], "city"
        else:
            lat = lng = None
            prec = "none"
        stats[prec] += 1

        pid = f"me:{pref}:{s['name']}"
        assert pid not in used_ids, pid
        used_ids.add(pid)
        p = {"id": pid, "name": s["name"], "kana": s["nameKana"], "pref": PREFS.index(pref) + 1,
             "addr": addr, "round": s["round"], "reg": s["registered"], "prec": prec}
        if lat is not None:
            p["lat"], p["lng"] = round(lat, 5), round(lng, 5)
        if s["url"]:
            p["url"] = s["url"]
        places.append(p)

    (RAW / "gsi_cache.json").write_text(json.dumps(cache, ensure_ascii=False, indent=0), encoding="utf-8")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    # 版は日付＋内容のハッシュ。同じ日に作り直しても、内容が変わればアプリ側で差分更新が走る
    digest = hashlib.sha1(json.dumps(places, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:8]
    doc = {
        "version": time.strftime("%Y-%m-%d") + "-" + digest,
        "count": len(places),
        "sources": [
            "国土交通省「道の駅」一覧 (https://www.mlit.go.jp/road/Michi-no-Eki/list.html) を加工して作成",
            "位置: © OpenStreetMap contributors (ODbL) / 国土地理院 住所検索API による市町村代表点",
        ],
        "prefs": PREFS,
        "places": places,
    }
    OUT.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{len(places)} 件 → {OUT}  位置精度: {stats}")


if __name__ == "__main__":
    main()
