#!/bin/sh
# Krea2 Gallery の起動・Tailscale Serve 公開・停止（MineNISA の deploy/nisa.sh と同じ流儀）
# Pi5 上で実行: ~/krea2-gallery/deploy.sh up|rebuild|down|status|logs
set -eu
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"; cd "$ROOT"
APP_URL="${APP_URL:-http://127.0.0.1:8020}"
HEALTH_URL="${APP_URL}/api/health"
# 443=Gitea, 8443=oto, 8444=MineNISA, 8450/8451 使用中 → 既定 8452
HTTPS_PORT="${TAILSCALE_HTTPS_PORT:-8452}"

need() { command -v "$1" >/dev/null 2>&1 || { echo "必要なコマンドがありません: $1" >&2; exit 1; }; }
ensure_env() {
  if [ ! -f .env ]; then
    echo "GALLERY_TOKEN=$(openssl rand -hex 24)" > .env; chmod 600 .env
    echo ".env を作成しました（GALLERY_TOKEN を WSL2 の ~/krea2/.gallery_env にも設定してください）"
  fi
}
wait_health() {
  i=0; while [ "$i" -lt 30 ]; do curl -fsS "$HEALTH_URL" >/dev/null 2>&1 && return 0; i=$((i+1)); sleep 1; done
  echo "ヘルスチェック失敗: $HEALTH_URL" >&2; docker compose logs --tail 50; return 1
}
serve_on() { need tailscale; sudo tailscale serve --bg --https="${HTTPS_PORT}" "${APP_URL}"; }
serve_off() { command -v tailscale >/dev/null 2>&1 && sudo tailscale serve --https="${HTTPS_PORT}" off || true; }
status() {
  echo "=== compose ==="; docker compose ps || true
  echo "=== health ==="; curl -sS "$HEALTH_URL" || echo "(未応答)"; echo
  echo "=== tailscale serve ==="; tailscale serve status 2>/dev/null | grep -A1 ":${HTTPS_PORT}" || echo "(未公開)"
  echo; echo "iPhone からは https://$(tailscale status --json 2>/dev/null | python3 -c 'import sys,json; print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))'):${HTTPS_PORT}/"
}
case "${1:-}" in
  up)      need docker; ensure_env; docker compose up -d --build; wait_health; serve_on; status ;;
  rebuild) need docker; ensure_env; docker compose up -d --build; wait_health; status ;;
  down)    serve_off; docker compose down ;;
  status)  status ;;
  logs)    docker compose logs --tail 100 -f ;;
  *) echo "使い方: deploy.sh up|rebuild|down|status|logs"; exit 1 ;;
esac
