# Krea2 Gallery（Pi5）

生成画像を確認する WebApp。`http://100.69.125.56:8020/`（Tailscale）

- 画像・メタデータ・お気に入りは `./data/` に永続化
- WSL2 の `~/krea2/scripts/gen.sh` が生成後に `/api/upload` へ POST する（トークンは `.env` の `GALLERY_TOKEN`）
- 手動アップロード例:
  `curl -H "Authorization: Bearer $TOKEN" -F file=@x.png -F folder=test -F 'meta={"prompt":"..."}' http://100.69.125.56:8020/api/upload`

更新: `docker compose up -d --build`
