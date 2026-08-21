#!/usr/bin/env python3
"""C109 サークルカット生成

テンプレート B0400.png（635×903）に、キャラ画像・サークル名・タイトルを流し込む。
左上の小枠（スペース番号欄）は空けたまま。2 倍解像度で描いてから縮小して文字を滑らかにする。

使い方:
  python3 make_circlecut.py <テンプレート.png> <キャラ画像.png> <出力.png> [--crop x0,y0,x1,y1]
"""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

CIRCLE = "くろぱんた団"
TITLE_LINES = ["ミリしらが AI で", "同人誌を作ってみた。"]
SUB = "Krea 2 LoRA で作るオリジナルキャラ本"

# テンプレート実測（635×903）: 外枠内側 22..612 × 22..880、小枠 22..163 × 22..164、
# 小枠の右側の帯 182..612 × 22..180、本体 22..612 × 182..880
MAIN = (22, 182, 612, 880)
STRIP = (182, 22, 612, 180)
S = 2  # 作業倍率


def font(size: int, weight: str = "W8") -> ImageFont.FreeTypeFont:
    for cand in [f"/System/Library/Fonts/ヒラギノ角ゴシック {weight}.ttc",
                 "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
                 "/System/Library/Fonts/Hiragino Sans GB.ttc",
                 "/Library/Fonts/Arial Unicode.ttf"]:
        try:
            return ImageFont.truetype(cand, size)
        except OSError:
            continue
    return ImageFont.load_default()


def fit_font(draw, text, max_w, start, weight="W8", min_size=20):
    size = start
    while size > min_size:
        f = font(size, weight)
        if draw.textlength(text, font=f) <= max_w:
            return f
        size -= 2
    return font(min_size, weight)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("template")
    ap.add_argument("image")
    ap.add_argument("out")
    ap.add_argument("--crop", help="元画像の切り出し x0,y0,x1,y1（省略時は上半身を自動）")
    a = ap.parse_args()

    tpl = Image.open(a.template).convert("RGB")
    W, H = tpl.size
    canvas = tpl.resize((W * S, H * S), Image.NEAREST)
    d = ImageDraw.Draw(canvas)

    # ---- 本体: 画像 + 下部のタイトル帯 ----
    mx0, my0, mx1, my1 = [v * S for v in MAIN]
    band_h = 150 * S
    img_box = (mx0, my0, mx1, my1 - band_h)
    bw, bh = img_box[2] - img_box[0], img_box[3] - img_box[1]

    src = Image.open(a.image).convert("RGB")
    if a.crop:
        x0, y0, x1, y1 = [int(v) for v in a.crop.split(",")]
        src = src.crop((x0, y0, x1, y1))
    # 枠の縦横比に合わせて中央（やや上寄り）で切り出す
    ratio = bw / bh
    sw, sh = src.size
    if sw / sh > ratio:
        nw = int(sh * ratio)
        x0 = (sw - nw) // 2
        src = src.crop((x0, 0, x0 + nw, sh))
    else:
        nh = int(sw / ratio)
        y0 = max(0, int((sh - nh) * 0.15))
        src = src.crop((0, y0, sw, y0 + nh))
    src = src.resize((bw, bh), Image.LANCZOS)
    canvas.paste(src, (img_box[0], img_box[1]))

    # タイトル帯（白地、上に細い黒線）
    d.rectangle((mx0, my1 - band_h, mx1, my1), fill="white")
    d.rectangle((mx0, my1 - band_h, mx1, my1 - band_h + 4 * S), fill="black")
    f_title = fit_font(d, max(TITLE_LINES, key=len), (mx1 - mx0) - 24 * S, 54 * S)
    lh = f_title.size + 6 * S
    ty = my1 - band_h + (band_h - lh * len(TITLE_LINES)) // 2 + 2 * S
    for line in TITLE_LINES:
        tw = d.textlength(line, font=f_title)
        d.text(((mx0 + mx1 - tw) / 2, ty), line, font=f_title, fill="black")
        ty += lh

    # ---- 上の帯: サークル名 ----
    sx0, sy0, sx1, sy1 = [v * S for v in STRIP]
    d.rectangle((sx0, sy0, sx1, sy1), fill="white")
    f_circle = fit_font(d, CIRCLE, (sx1 - sx0) - 24 * S, 66 * S)
    f_sub = fit_font(d, SUB, (sx1 - sx0) - 24 * S, 20 * S, weight="W6", min_size=14 * S)
    ch = f_circle.size
    total = ch + 8 * S + f_sub.size
    cy = sy0 + ((sy1 - sy0) - total) // 2 - 4 * S
    cw = d.textlength(CIRCLE, font=f_circle)
    d.text(((sx0 + sx1 - cw) / 2, cy), CIRCLE, font=f_circle, fill="black")
    sw2 = d.textlength(SUB, font=f_sub)
    d.text(((sx0 + sx1 - sw2) / 2, cy + ch + 10 * S), SUB, font=f_sub, fill="#222222")

    out = canvas.resize((W, H), Image.LANCZOS)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    out.save(a.out, optimize=True)
    print("saved", a.out, out.size)


if __name__ == "__main__":
    main()
