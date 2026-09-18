# 車載視点と判断の検証

## 対象と現在の分離

東京2025の実都市モデルをBlenderで描画する経路は、`camera_inspection_not_driving` です。カメラは道路中心線に沿って動きますが、車両モデル・認識・Jevの閉ループ制御は動かしません。Kirchbergの運動学シミュレーションとは、地図も試験目的も異なります。両者を連結したような映像やラベルを作らないでください。

データセット版は2025、航空写真配信セットは2023です。整備年・配信年・撮影日・取得日を同一視しません。公開の道路モデルをカメラの高さに使うことは、車線や停止線、信号位相を検証したことにもなりません。

## 実データから描画する

PythonとNode.jsの準備はREADMEを参照し、Blenderとffmpegを別途インストールしてください。

```bash
npm install --ignore-scripts --no-audit --no-fund --prefix tools/gltf
export JEVDRIVE_DECODE_GEOMETRY=1
python tools/prepare_ego_capture.py --config configs/tokyo-ego.json --out runs/ego
blender --background --threads 2 --python-exit-code 2 --python tools/blender_ego_capture.py -- --capture runs/ego
python tools/encode_ego_capture.py runs/ego
```

1280×720、水平画角80度、地表から1.55m、12fps×8秒が既定です。カメラ内部行列K、外部行列、全フレームの位置と時刻を保存します。メートル/センチメートル、ENU/glTF/Blender、光学座標とBlenderカメラ座標は明示的に変換します。実カメラを測定して得た校正値ではありません。

道路・街路設備・植生のLOD3は、取得できたものだけを追加し、個別の失敗を記録します。航空写真zoom19の実リクエストは404だったため、設定に明記してnative zoom18を選択しました。AIによる超解像や架空の壁面の追加はしません。Ubuntu配布Blender4.0.2でOIDNが利用できなかったため、Cyclesの16サンプル・ノイズ除去なしで実行します。元の写真には陰影が焼き込まれているため、写真マテリアルを二重に照らさない処理を行っています。

`real-public-data-ego-stills` は2枚の先行画像を確認する独立した小さな実行です。1fpsの2フレームを滑らかな走行映像と呼ばず、画質検査に使います。`real-public-data-ego-view` が96フレームの別実行です。

## APIの判断を検証する

```bash
python tools/record_jev_evidence.py --mode baseline --seconds 12 --out runs/baseline-evidence
python tools/record_jev_evidence.py --mode jev-shadow --seconds 12 --max-calls 24 --out runs/shadow-evidence
python tools/record_jev_evidence.py --mode jev-live --seconds 12 --max-calls 24 --out runs/live-evidence
```

Jevモードはローカル環境変数 `TYPESAFE_API_KEY` を使い、対話端末では未設定時に非表示入力を求めます。コマンド行・Git・ブラウザーにキーを渡しません。接続に失敗しても架空の応答を代入しません。ライブの成立条件を満たさなければ終了コード3、設定や記録の検証に失敗すれば2を返します。

新しい記録は、各時刻の観測、要求本文、受信応答、判断の採否、制約後の加減速、操舵、実際の次車両状態を保持します。監査器は同じ運動モデルで一歩ずつ再計算し、APIに送った観測と元の観測、指示と応答、時刻とハッシュを突き合わせます。ループ終了後に返った応答も保存しますが、制御に使った回数には含めません。

同一時刻・同一観測に対するルール制御との違いも記録します。これは別軌道を走らせた比較実験やモデルの優位性の証明ではありません。ハッシュと自己記録は整合性の検査であって、第三者が署名したAPI利用証明でもありません。合成テストを実API成功に昇格させません。

現行Jevはテキスト/JSON入力のみです。画像認識の結果を、時刻・対象・距離・不確実性を含む状態へ変換して渡す必要があります。現在の走行入力はシミュレーターの真値であり、その認識器はまだ実装・評価されていません。
出典: https://docs.typesafe.ai/models

## 実写に近づけるためのデータ方針

地上の壁面・路面の細部が元データにない場合、描画エンジンや解像度の設定だけで復元できたとは言えません。PLATEAUは実形状と座標の検査を継続する一方、車載視点の外観層には、実車カメラ/LiDAR記録からの再構成を追加する方針です。建物の見た目のために、測量された道路形状を勝手に変更しません。

調査した次の実装候補はNVIDIA NuRecです。公式資料はNCoreの実センサー記録、再構成済みUSDZ、CARLA/AlpaSim/gRPCでの利用を説明しています。CARLAの手順にはGPU、CUDA、Docker、Hugging Faceのアカウントとデータアクセス同意が必要で、コレクション全体は非常に大きいため無条件の全取得を実行しません。1つの許諾済み区間を明示して、モデル・カメラ・座標・版を固定する必要があります。

- https://docs.nvidia.com/nurec/av/index.html （2026-08-25更新を確認）
- https://carla.readthedocs.io/en/latest/nvidia_nurec/

このリポジトリにNuRecの実行済み統合や実際のGPU描画があるとは主張しません。制約なくGoogleの画像を取得・再配布する方式や、他社のデモ映像を自作の走行成果に見せる方式も採用しません。
