#!/bin/bash
# 使い方: upload.sh <png> [folder] [meta-json]
set -e
source ~/krea2/.gallery_env
FILE="${1:?png required}"; FOLDER="${2:-}"; META="${3:-{\}}"
# メタデータ・フォルダ名は --form-string で渡す（-F だと値中の ';' を curl がオプションとして解釈して壊れる）
curl -sS -m 120 -H "Authorization: Bearer $GALLERY_TOKEN" \
  -F "file=@$FILE" --form-string "folder=$FOLDER" --form-string "meta=$META" \
  "$GALLERY_URL/api/upload"
echo
