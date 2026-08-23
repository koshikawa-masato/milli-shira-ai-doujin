#!/bin/bash
# RunPod の Pod が（再）起動した直後に実行する。コンテナ側（/root）が初期化されても /workspace から復元し、
# 常駐編集サーバ（edit_server.py）を tmux で立ち上げる（モデル読込が先に始まる）
# 使い方: bash /workspace/krea2/scripts/pod_boot.sh   （中継ワーカーが起動のたびに ssh で実行。何度呼んでも安全）
set -e
W=/workspace/krea2
[ -L ~/krea2 ] || ln -sfn $W ~/krea2
command -v tmux >/dev/null || (apt-get update -qq >/dev/null 2>&1 && apt-get install -y -qq tmux >/dev/null 2>&1) || true
mkdir -p $W/incoming $W/queue
if ! tmux has-session -t editsrv 2>/dev/null; then
  rm -f $W/queue/server.ready
  tmux new-session -d -s editsrv "cd $W/musubi-tuner && source .venv/bin/activate && KREA2_ROOT=$W python $W/scripts/edit_server.py >> $W/edit_server.log 2>&1"
  echo "edit_server started"
fi
echo "BOOT_OK $(hostname) $(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null)"
