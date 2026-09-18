# Jve Driven / Jev Drive Lab

**v0.3.0 — 公開データから都市を再現し、Jevの判断を検証するシミュレーション専用の研究基盤。**

実物のテクスチャ付き建物、航空写真、楕円体高の地形を取り込みます。「現実らしい生成画像」と「現地の測量・撮影データ」を混同しません。現時点で写真と区別できない東京や、東京での自動運転が完成したという意味ではありません。

## 3つの経路

| 経路 | 内容 | 限界 |
|---|---|---|
| Public world | PLATEAU 3D Tiles + terrain + ortho + OSM centerlines → hash-locked snapshot → GLB → audit | 可視化専用。車線・停止線・路面衝突は未検証 |
| Offline driving | 同梱の歴史的OSM抽出 → 簡略3Dワールド → 8シナリオ | 平面車両モデル・正解情報による試験。Jev実応答ではない |
| Jev / engines | 公式APIのshadow/liveモード、BlenderのGLB取り込み、CARLAアダプター | API・エンジンでの実行は各環境で別途検証が必要 |

## 起動

Python 3.10以上。仮想環境を作成してから、リポジトリ直下で実行します。

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
python -m jevdrive build-world
python tools/run_smoke.py
python tools/build_viewer.py
python -m http.server 8000 --bind 127.0.0.1
```

`http://127.0.0.1:8000/web/index.html` はAPI不要の記録再生です。`web/public-world.html` は公開配信へ接続する別の検査画面で、インターネットが必要です。存在しない `jevdrive.server` は起動しません。

## 実際の公開データを取得する

最初は東京・丸の内の小範囲を120 MB / 180ファイル以内で取得します。公開配信の通信料以外にAPIキーは不要です。欠損を架空の建物や平らな地形で埋めません。

```bash
python tools/live_world_check.py --config configs/tokyo-smoke.json --out runs/tokyo
```

個別に進める場合:

```bash
python -m jevdrive.publicworld fetch --config configs/tokyo-marunouchi.json --out runs/marunouchi
python -m jevdrive.publicworld verify runs/marunouchi
python -m jevdrive.publicworld build runs/marunouchi
python -m jevdrive.publicworld audit runs/marunouchi
```

取得に失敗した場合だけ、同じ設定と出力先で `fetch ... --resume` または `live_world_check.py ... --resume` を使用します。再開時も取得済みファイルのハッシュを確認し、容量制限をリセットしません。成功済みスナップショットを最新データで黙って置換しません。

出力は `public-world.json`、`download-lock.json`、`source-lock.json`、`visual-world.glb`、`visual-audit.json` です。GLBだけでなく、選択したタイル・座標変換・取得設定・道路の派生データまで検査します。ハッシュは改変検出用であり、公開元の署名や測量精度の証明ではありません。

現在の変換器は明示的タイルツリー、GLB/b3dmに対応します。implicit tiling、Draco、meshopt、BasisU、外部glTF画像等は未対応で、黙って欠落させず停止します。未対応形式の拡張は回帰テストを追加して行います。

## Blender / Unreal / CARLA

```bash
blender --background --python tools/blender_public_world.py -- --snapshot runs/tokyo --out runs/tokyo.blend --render runs/tokyo.png
```

詳細は [エンジン統合](docs/ENGINES.md)。Unrealでは公開3D Tilesを表示する層と、車線・交通規則・衝突形状を持つ走行層を分けます。可視化メッシュを取り込んだだけでは走行地図を完成扱いにしません。

## Jevを接続する

ローテーション済みのキーをローカル環境変数 `TYPESAFE_API_KEY` に設定します。`.env` は自動読込しません。キーをコマンド本文、HTML、Git、Issueへ貼らないでください。まずshadowで比較します。

```bash
python -m jevdrive simulate --scenario pedestrian --mode jev-shadow --realtime --max-calls 20 --out runs/jev-shadow.json
```

Choiceで行動、Noulで歩行者の譲歩要否、Scoreで視界の注意度を評価します。モデルは `jev-1.13.0`、接続先は `https://api.typesafe.ai/v1/systemone`。2 Hz以下・同時要求1件・要求上限・期限・再試行待機を実装しています。距離計算、最新状況による停止制約、車両制御は別コードです。`confidence` は安全確率ではなく、しきい値は未校正です。入力は現在シミュレーターの正解情報であり、カメラ認識ではありません。

## 検証とCI

ローカルでは168テスト、8つのオフラインシナリオ、GLB再生成を確認しました。168件は合成HTTP/地形/GLB試験と簡略走行試験であり、実都市の精度・Jev性能・実車安全性を示しません。

`offline-validation` はLinuxのPython 3.10–3.13とWindows 3.12でテスト・構文・秘密情報チェック・生成処理を実行する設定です。`public-world-live-check` はキーなしの実データ取得と変換を試し、失敗してもJSON診断を残します。CIの成功はActionsの実際の結果で確認してください。配信元障害とコード回帰を区別し、失敗を `continue-on-error` で隠しません。公開画像・生タイルはCI成果物へ自動公開しません。

次工程と証拠要件は [完了条件](docs/ACCEPTANCE_BACKLOG.md)。エージェントは [AGENTS.md](AGENTS.md) を先に読んでください。

## 出典と利用条件

コードはMIT。OSM抽出は © OpenStreetMap contributors / ODbL-1.0 で、2020-08-10のデータです。PLATEAU等のデータは各提供元の条件に従います。撮影日と取得日は別で、`latest` は2026年の現況を保証しません。

- [PLATEAU 3D Tiles](https://docs.plateauview.mlit.go.jp/datasets/3d-tiles/)
- [PLATEAU Terrain](https://docs.plateauview.mlit.go.jp/datasets/terrain/)
- [PLATEAU Ortho](https://docs.plateauview.mlit.go.jp/datasets/ortho/)
- [TypeSafe API](https://docs.typesafe.ai/api)
- [データ利用条件](data/LICENSE.txt) / [同梱OSMの出典](data/raw/PROVENANCE.json)
