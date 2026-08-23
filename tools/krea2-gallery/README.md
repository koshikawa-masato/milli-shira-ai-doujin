# Krea2 Gallery（Pi5）

生成画像を確認する WebApp。`http://100.69.125.56:8020/`（Tailscale）

- 画像・メタデータ・お気に入りは `./data/` に永続化
- WSL2 の `~/krea2/scripts/gen.sh` が生成後に `/api/upload` へ POST する（トークンは `.env` の `GALLERY_TOKEN`）
- 手動アップロード例:
  `curl -H "Authorization: Bearer $TOKEN" -F file=@x.png -F folder=test -F 'meta={"prompt":"..."}' http://100.69.125.56:8020/api/upload`

更新: `docker compose up -d --build`

## RunPod 中継ワーカー（編集ジョブ）

`runpod_worker.py`（compose の `runpod-worker`）が、操作タブの「編集」ジョブを RunPod で実行して結果を登録する。
Pod/Serverless は tailnet 外で Pi5 に届かないので、Pi5 側から起動・送信・回収する。

- **Pod モード**（学習フェーズ向け、単価が安い）: `.env` に `RUNPOD_API_KEY` と `RUNPOD_POD_ID` を設定。
  ジョブが来たら Pod を起動 → `pod_boot.sh` で復元 → 参照画像を scp → `edit_batch.sh` を ssh 実行 → 結果を scp で回収して登録 →
  キューが空になったら `RUNPOD_IDLE_STOP_SEC`（既定 0 = 即）後に Pod を停止。
  ssh 鍵は `./ssh/id_ed25519`（`ssh-keygen -t ed25519 -N "" -f ssh/id_ed25519`）。公開鍵を Pod の env `PUBLIC_KEY` に改行区切りで追加する
  （**env 更新は Pod のコンテナを作り直す**ので、ジョブが動いていないときに）
- **Serverless モード**: `.env` に `RUNPOD_API_KEY` と `RUNPOD_ENDPOINT_ID`。ワーカーイメージは `tools/runpod-serverless/`（GHCR に CI で公開）
- `.env` を変えたら `./deploy.sh rebuild`
