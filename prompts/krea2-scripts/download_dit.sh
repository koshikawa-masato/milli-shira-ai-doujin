#!/bin/bash
# HF トークン設定後に実行: Krea-2 Turbo/Raw をダウンロード
set -e
cd ~/krea2/musubi-tuner && source .venv/bin/activate
cd ~/krea2/models
huggingface-cli download krea/Krea-2-Turbo turbo.safetensors --local-dir .
huggingface-cli download krea/Krea-2-Raw raw.safetensors --local-dir .
ls -la ~/krea2/models
