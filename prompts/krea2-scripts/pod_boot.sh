#!/bin/bash
# RunPod の Pod が（再）起動した直後に実行する。コンテナ側（/root）が初期化されても /workspace から復元する
# 使い方: bash /workspace/krea2/scripts/pod_boot.sh   （中継ワーカーが起動のたびに ssh で実行）
set -e
[ -L ~/krea2 ] || ln -sfn /workspace/krea2 ~/krea2
command -v tmux >/dev/null || (apt-get update -qq >/dev/null 2>&1 && apt-get install -y -qq tmux >/dev/null 2>&1) || true
mkdir -p /workspace/krea2/incoming
echo "BOOT_OK $(hostname) $(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null)"
