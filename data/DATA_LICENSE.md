# データの出典と利用条件（data/ 以下）

# data/michinoeki.json（道の駅一覧）

`data/michinoeki.json` は、以下のデータを `tools/convert.py` で加工・結合して作成したデータベースです。
アプリのコード（MIT License）とは別の条件に従います。

## ライセンス

このデータファイルは **Open Database License (ODbL) 1.0** で提供します。
https://opendatacommons.org/licenses/odbl/1-0/

OpenStreetMap 由来の位置情報を含む派生データベースのため、ODbL の条件（出典表示・同一条件での提供）に従います。
国土交通省由来の項目は、下記の公共データ利用規約の出典表示を併せて行います。

## 出典

### 駅名・よみ・所在地・登録回・登録年月・公式サイトURL
- 出典：国土交通省「道の駅」一覧（https://www.mlit.go.jp/road/Michi-no-Eki/list.html）
- 利用条件：国土交通省ウェブサイト利用規約（公共データ利用規約 第1.0版〔PDL1.0〕、CC BY 4.0 互換）
  https://www.mlit.go.jp/link.html
- **加工の内容**：Excel 一覧から駅名・ふりがな・所在地（都道府県＋市町村）・登録回・登録年月・URL を抽出し、
  ふりがなをひらがなの「よみ」に変換、識別子を付与して JSON に変換した。
- 本データおよびこのアプリは国土交通省が作成したものではありません。

### 位置（緯度・経度、`prec: "osm"` の駅）
- 出典：© OpenStreetMap contributors（https://www.openstreetmap.org/copyright）
- 利用条件：Open Database License (ODbL) 1.0
- **加工の内容**：Overpass API で名称に「道の駅」を含む地物を取得し、駅名と市町村で照合して代表点（ウェイは中心点）を採用した。

### 位置なし（`prec: "none"` の駅）
OpenStreetMap で照合できなかった駅には座標を含めていません。
利用者がアプリ内の「住所から座標を取得」（国土地理院の住所検索、操作1回につき1リクエスト）または
緯度経度の直接入力で、各自の端末に設定します。取得した座標はその端末内にのみ保存され、本データには含まれません。

## 作り直し

```
python tools/convert.py --refresh
```

---

# data/stations.json（駅名の入力補助）

- 出典：「国土数値情報（鉄道データ）」（国土交通省）
  https://nlftp.mlit.go.jp/ksj/gml/datalist/KsjTmplt-N02-2024.html
  （2025年度版・2024年12月31日時点、N02-24）
- 利用条件：**CC BY 4.0**（https://creativecommons.org/licenses/by/4.0/deed.ja）
- **加工の内容**：駅データ（GeoJSON）から駅名・運営会社・路線名・事業者種別を抜き出し、
  同じ駅名・事業者・路線の重複をまとめ、ホームを表す線の中間点を代表点とした。
  JR 各社などの運営会社名は「JR東日本」のような一般的な呼び方に置き換えた。
- 本データは国土交通省が作成したものではありません。
- 作り直し：`python tools/convert_stations.py --refresh`

アプリで駅を登録したときの内容（駅名・事業者・路線・位置・都道府県）は、利用者の端末内にだけ保存されます。
都道府県は、駅を選んだときに国土地理院の逆ジオコーダ（座標→市区町村コード）へ駅の座標を1回だけ送って調べます。

