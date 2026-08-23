# 参考: RunPod Serverless のチューニングガイド（LLM 推論向け）を画像生成に読み替える

出典: Runpod "Optimize LLM inference on Runpod Serverless" https://www.runpod.io/articles/guides/optimize-llm-inference-on-runpod-serverless
天の声の指示で読んだ（2026-08-23）。vLLM 前提の記事だが、うちの Qwen-Image-Edit / Krea2 ワーカーに効く点だけ抜き出す。

## そのまま効く点
- **FlashBoot を有効にする**: コールドスタートを「モデル読込の 30〜120 秒」から「200ms 級」へ。ワーカーの状態（読込済みモデル）を温存して再起動する仕組みなので、**散発的にしか呼ばないエンドポイントには効きにくい**（温存されたワーカーが解放されると結局読み直し）。うちの使い方（数時間に数枚）では期待しすぎない
- **1 変数ずつ変えて丸 1 日測る**: チューニングは逐次。今日の「常駐サーバ＋10 分猶予」も、まず数日このまま使って読込回数と費用を見る
- **費用をジョブ単位で記録する**: 記事は vLLM の /metrics と課金を突き合わせる話。うちはギャラリーの履歴にジョブごとの所要秒（`elapsed_sec`）が残るので、そこに Pod の $/h を掛ければ 1 枚あたりの費用が出る → ギャラリーに「このジョブの費用」を出す余地
- **オートスケールの目安**: 「同時利用者数 ÷ 1 ワーカーの同時処理数」を下限に、バーストに応じて余裕を足す。うちは利用者 1 人なので max workers 1 で十分（Serverless を使う場合）

## LLM 専用で、うちには当てはまらない点
- `MAX_NUM_SEQS`（連続バッチのサイズ）、`MAX_MODEL_LEN`（KV キャッシュ長）、AWQ/GPTQ/FP8 量子化の選択
- ただし「量子化で VRAM と読込を減らす」発想は **fp8 の重み（Edit 40GB→20GB）** として残っている。顔の再現性を最優先している間は見送り

## うちの結論（2026-08-23 時点）
- 学習フェーズは Pod ＋ 常駐サーバ（`edit_server.py`）＋ 猶予停止。Serverless は本の制作が「生成・編集だけ」になった段階で再検討
- Serverless にするなら: FlashBoot ON、max workers 1、モデルは Network volume（同 DC）、idle timeout は数分、`executionTimeoutMs` は 10 分
