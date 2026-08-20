#!/bin/bash
# 使い方: upload.sh <png> [folder] [meta-json]
# ~/krea2/.gallery_env に GALLERY_URL / GALLERY_TOKEN
set -e
source ~/krea2/.gallery_env
FILE="${1:?png required}"; FOLDER="${2:-}"; META="${3:-{\}}"
curl -sS -m 120 -H "Authorization: Bearer $GALLERY_TOKEN" \
  -F "file=@$FILE" -F "folder=$FOLDER" -F "meta=$META" \
  "$GALLERY_URL/api/upload"
echo
