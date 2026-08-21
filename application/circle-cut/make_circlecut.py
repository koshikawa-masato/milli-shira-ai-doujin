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

CIRCLE = "くろぱんだ団"
TITLE_LINES = ["ミリしらが AI で", "同人誌を作ってみた。"]

# テンプレート実測（635×903）: 外枠内側 22..612 × 22..880、小枠（スペース番号欄）22..163 × 22..164、
# 小枠の右側の帯 182..612 × 22..180。絵は外枠内側いっぱいに敷き、小枠と L 字の黒帯はテンプレートから戻す
FULL = (22, 22, 612, 880)
STRIP = (182, 22, 612, 180)
CORNER = (0, 0, 182, 182)
S = 2  # 作業倍率
STROKE = 7  # 文字の白縁取り（1倍時の px）


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

    # ---- 絵を外枠内側いっぱいに敷く ----
    fx0, fy0, fx1, fy1 = [v * S for v in FULL]
    bw, bh = fx1 - fx0, fy1 - fy0
    src = Image.open(a.image).convert("RGB")
    if a.crop:
        x0, y0, x1, y1 = [int(v) for v in a.crop.split(",")]
        src = src.crop((x0, y0, x1, y1))
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
    canvas.paste(src.resize((bw, bh), Image.LANCZOS), (fx0, fy0))
    # 小枠（スペース番号欄）と L 字の黒帯をテンプレートから戻す
    cx0, cy0, cx1, cy1 = [v * S for v in CORNER]
    canvas.paste(tpl.resize((W * S, H * S), Image.NEAREST).crop((cx0, cy0, cx1, cy1)), (cx0, cy0))

    def outlined(text, xy, f):
        d.text(xy, text, font=f, fill="black", stroke_width=STROKE * S, stroke_fill="white")

    # ---- サークル名（右上の帯の位置、絵の上に白縁取りで） ----
    sx0, sy0, sx1, sy1 = [v * S for v in STRIP]
    f_circle = fit_font(d, CIRCLE, (sx1 - sx0) - 2 * (12 + STROKE) * S, 66 * S)
    cw = d.textlength(CIRCLE, font=f_circle)
    outlined(CIRCLE, ((sx0 + sx1 - cw) / 2, sy0 + ((sy1 - sy0) - f_circle.size) // 2 - 6 * S), f_circle)

    # ---- タイトル（下部、2 行、白縁取り） ----
    f_title = fit_font(d, max(TITLE_LINES, key=len), (fx1 - fx0) - 2 * (12 + STROKE) * S, 54 * S)
    lh = f_title.size + 10 * S
    ty = fy1 - lh * len(TITLE_LINES) - 18 * S
    for line in TITLE_LINES:
        tw = d.textlength(line, font=f_title)
        outlined(line, ((fx0 + fx1 - tw) / 2, ty), f_title)
        ty += lh

    out = canvas.resize((W, H), Image.LANCZOS)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    out.save(a.out, optimize=True)
    print("saved", a.out, out.size)


if __name__ == "__main__":
    main()
