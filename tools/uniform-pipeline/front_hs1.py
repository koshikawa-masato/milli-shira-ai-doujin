"""高一 正面 Oracle を決定論的に組み立てる（AI 不使用、同じ入力から同じ出力）
入力:  B = oracle/20260822-211146-418_1.png（高一の等身 Oracle）、V5 = oracle/bust_smile_hand_v5.png（口を閉じた微笑 Oracle、顔 = A）
出力:  out/B_white.png（切り抜き白背景）、out/front_hs1_base.png（右腕を鏡像で左腕に）、
       out/front_hs1_faceB.png（B の顔のまま口だけ閉じる）、out/front_hs1_faceA.png（V5 の頭を B の頭幅に縮小して貼る）
使い方: python3 front_hs1.py <B.png> <V5.png> <outdir>
要件: prompts/kuropanda-uniform-requirements.md（12 画素一致 / 13 口を閉じた微笑 / 14 白背景・手を斜め下）
"""
import os
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from rembg import new_session, remove

B_PATH, V5_PATH, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
os.makedirs(OUT, exist_ok=True)
LINE = (96, 56, 50)           # 口の線の色（輪郭線の濃い茶）
SHADOW_SKIN = (224, 186, 162)  # 指の影の肌色

# ---------- 1. 切り抜き → 白背景 ----------
b = Image.open(B_PATH).convert("RGB")
W, H = b.size
cut = remove(b, session=new_session("isnet-anime"), alpha_matting=False).convert("RGBA")
a = np.array(cut)
al = a[..., 3]
n, lab, stats, _ = cv2.connectedComponentsWithStats((al > 128).astype(np.uint8), 8)
main = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))          # 人物本体（最大成分）だけ残す
keep = cv2.dilate((lab == main).astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool)
al = np.where(keep, al, 0)
al = np.where(al < 40, 0, al)                                      # 薄い影の残りを落とす
rgb = a[..., :3].astype(int)
r, g, bl = rgb[..., 0], rgb[..., 1], rgb[..., 2]
wood = (r > 90) & (r < 200) & (g < 150) & (bl < 130) & (r - bl > 30) & ~((r > 200) & (g > 170))
win = np.zeros_like(wood); win[620:730, 590:720] = True             # 右手に接していた机の角
al = np.where(wood & win, 0, al)
a[..., 3] = al
white = Image.new("RGB", (W, H), (255, 255, 255)); white.paste(Image.fromarray(a), (0, 0), Image.fromarray(a))
wa = np.array(white)
# 右手の中の閉じた白い穴を影の肌色で埋める（外の白背景と繋がっていない白成分）
x0, y0, x1, y1 = 580, 590, 720, 730
sub = wa[y0:y1, x0:x1]; wh = (sub.min(axis=2) >= 235).astype(np.uint8)
n2, lab2 = cv2.connectedComponents(wh, connectivity=4)
border = set(np.unique(np.concatenate([lab2[0], lab2[-1], lab2[:, 0], lab2[:, -1]])))
for k in range(1, n2):
    if k not in border:
        sub[lab2 == k] = SHADOW_SKIN
wa[y0:y1, x0:x1] = sub
white = Image.fromarray(wa); white.save(f"{OUT}/B_white.png")

# ---------- 2. 右腕を体の軸で鏡像にして左腕に ----------
nonwhite = (wa.min(axis=2) <= 235)
def center(y0, y1):
    cols = np.where(nonwhite[y0:y1].any(axis=0))[0]; return (cols.min() + cols.max()) / 2
axis = (center(40, 120) + center(900, 950) + center(1150, 1200)) / 3 + 5   # 髪・脚・靴の中心。+5 は袖を胴の縁に付ける補正
poly = [(558, 262), (640, 262), (652, 360), (640, 470), (702, 600), (738, 650), (732, 714), (588, 720), (562, 652), (552, 560), (552, 455), (556, 400)]
m = Image.new("L", (W, H), 0); ImageDraw.Draw(m).polygon(poly, fill=255)
alpha = Image.fromarray((((np.array(m) > 0) & nonwhite) * 255).astype("uint8"))
arm = Image.new("RGBA", (W, H), (0, 0, 0, 0)); arm.paste(white, (0, 0), alpha)
arm_m = arm.transpose(Image.FLIP_LEFT_RIGHT); shift = int(round(2 * axis - W))
base = white.copy(); d = ImageDraw.Draw(base)
d.polygon([(150, 190), (292, 190), (292, 470), (250, 500), (165, 500), (145, 330)], fill=(255, 255, 255))  # 上げた前腕・手・袖を消す
base.paste(arm_m, (shift, 0), arm_m)
ba = np.array(base)
def inpaint_dark(img, x0, x1, y0, y1, thr=150, dil=3, rad=3):
    """矩形内の暗い画素（線）を周囲から補間して消す（決定論的）"""
    sub = img[y0:y1, x0:x1].astype(int); dark = (sub.max(axis=2) < thr)
    mk = np.zeros(img.shape[:2], np.uint8); mk[y0:y1, x0:x1] = dark.astype(np.uint8) * 255
    mk = cv2.dilate(mk, np.ones((dil, dil), np.uint8))
    return cv2.cvtColor(cv2.inpaint(cv2.cvtColor(img, cv2.COLOR_RGB2BGR), mk, rad, cv2.INPAINT_TELEA), cv2.COLOR_BGR2RGB)
lx = int(round(2 * axis - 223)); ba = inpaint_dark(ba, lx, lx + 12, 652, 692)        # 左手の親指と人差し指の間の線
ba = inpaint_dark(ba, 283, 316, 268, 350, thr=170, dil=5, rad=5)                    # 肩の付け根に残る旧袖の線
base = Image.fromarray(ba); base.save(f"{OUT}/front_hs1_base.png")

# ---------- 3a. 顔案 1: B の顔のまま口を閉じる（v5 と同じ方法） ----------
def close_mouth(img, win_box, k=8):
    a = np.array(img); r, g, b_ = [a[..., i].astype(int) for i in range(3)]
    red = ((r > 150) & (g < 120) & (b_ < 130) & (r - g > 60)).astype(np.uint8) * 255
    w = np.zeros(a.shape[:2], np.uint8); w[win_box[1]:win_box[3], win_box[0]:win_box[2]] = 255; red = cv2.bitwise_and(red, w)
    ys, xs = np.where(red > 0); x0, y0, x1, y1 = xs.min(), ys.min(), xs.max(), ys.max()
    near = cv2.dilate(red, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (19, 19)))
    dark = ((r < 170) & (g < 120) & (b_ < 120)).astype(np.uint8) * 255
    mk = cv2.dilate(cv2.bitwise_or(red, cv2.bitwise_and(dark, near)), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)))
    filled = cv2.cvtColor(cv2.inpaint(cv2.cvtColor(a, cv2.COLOR_RGB2BGR), mk, 9, cv2.INPAINT_TELEA), cv2.COLOR_BGR2RGB)
    out = Image.fromarray(filled)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2 - 0.1 * (y1 - y0); hw = (x1 - x0) / 2 * 0.8; dy = (y1 - y0) * 0.16
    pts = [(cx - hw, cy - 0.6 * dy), (cx - 0.8 * hw, cy + 0.25 * dy), (cx - 0.55 * hw, cy + 0.8 * dy), (cx - 0.28 * hw, cy + 0.95 * dy), (cx, cy + dy),
           (cx + 0.28 * hw, cy + 0.95 * dy), (cx + 0.55 * hw, cy + 0.8 * dy), (cx + 0.8 * hw, cy + 0.25 * dy), (cx + hw, cy - 0.6 * dy)]
    P = [pts[0]] + pts + [pts[-1]]; curve = []
    for i in range(1, len(P) - 2):
        p0, p1, p2, p3 = P[i - 1], P[i], P[i + 1], P[i + 2]
        for kk in range(40):
            t = kk / 40; t2 = t * t; t3 = t2 * t
            curve.append((0.5 * ((2 * p1[0]) + (-p0[0] + p2[0]) * t + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2 + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3),
                          0.5 * ((2 * p1[1]) + (-p0[1] + p2[1]) * t + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2 + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3)))
    big = out.resize((out.width * k, out.height * k), Image.LANCZOS); dd = ImageDraw.Draw(big); N = len(curve)
    thick = max(1.0, (x1 - x0) / 28.0)   # 口幅に比例した線の太さ（v5: 口幅 74px → 中央半径 1.3px）
    for i, (x, y) in enumerate(curve):
        t = i / (N - 1); rad = (0.42 + 0.58 * np.sin(np.pi * t)) * thick * k
        dd.ellipse((x * k - rad, y * k - rad, x * k + rad, y * k + rad), fill=LINE)
    res = big.resize(out.size, Image.LANCZOS)
    return Image.composite(res, img, Image.fromarray(mk).filter(ImageFilter.GaussianBlur(1.2)))
faceB = close_mouth(base, (380, 170, 460, 240)); faceB.save(f"{OUT}/front_hs1_faceB.png")

# ---------- 3b. 顔案 2: V5（A の顔）の頭を B の頭幅に合わせて貼る ----------
v5 = Image.open(V5_PATH).convert("RGB")
def hair_bbox(img, seed_frac):
    a = np.array(img).astype(int); Hh, Ww = a.shape[:2]; black = (a.max(axis=2) < 48)
    sx, sy = int(Ww * seed_frac[0]), int(Hh * seed_frac[1])
    ys, xs = np.where(black[max(0, sy - 40):sy + 40, max(0, sx - 120):sx + 120]); sy0, sx0 = ys[0] + max(0, sy - 40), xs[0] + max(0, sx - 120)
    seen = np.zeros_like(black); stack = [(sy0, sx0)]; seen[sy0, sx0] = True
    while stack:
        y, x = stack.pop()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < Hh and 0 <= nx < Ww and black[ny, nx] and not seen[ny, nx]:
                seen[ny, nx] = True; stack.append((ny, nx))
    ys, xs = np.where(seen); return xs.min(), ys.min(), xs.max(), ys.max()
# V5 の頭（髪〜顎）だけを背景抜きで貼る。頭の横幅を B の髪の幅に合わせる
v5cut = remove(v5, session=new_session("isnet-anime"), alpha_matting=False).convert("RGBA")
bb = hair_bbox(base, (0.5, 0.06))
va = np.array(v5); vblack = (va.max(axis=2) < 48); vblack[560:, :] = False                # 髪は y<560（襟の線や影を除外）
ys, xs = np.where(vblack[:, 250:800]); hb = (xs.min() + 250, ys.min(), xs.max() + 250, ys.max())
NECK = 610                                                                                 # V5 の首の付け根（1024² 基準）。ここから下（襟・手）は貼らない
sc = (bb[2] - bb[0]) / (hb[2] - hb[0])
x0, x1, y0, y1 = max(0, hb[0] - 6), min(v5.width, hb[2] + 6), max(0, hb[1] - 6), NECK
head = v5cut.crop((x0, y0, x1, y1))
# 頭の形の楕円で切る（左の手・右の襟を除外）。下端は首で水平に切る
em = Image.new("L", head.size, 0); ImageDraw.Draw(em).ellipse((0, 0, head.width, int(head.height * 1.12)), fill=255)
ha = np.array(head); ha[..., 3] = np.minimum(ha[..., 3], np.array(em)); head = Image.fromarray(ha)
head_s = head.resize((int(head.width * sc), int(head.height * sc)), Image.LANCZOS)
px, py = int(bb[0] - (hb[0] - x0) * sc), int(bb[1] - (hb[1] - y0) * sc)
faceA = base.copy()
# B の頭（髪〜首）を白で消してから貼る。B の首から下（襟・胴）はそのまま
ImageDraw.Draw(faceA).ellipse((px - 6, py - 6, px + head_s.width + 6, py + int(head_s.height * 1.12) + 6), fill=(255, 255, 255))
faceA.paste(head_s, (px, py), head_s)
faceA.save(f"{OUT}/front_hs1_faceA.png")
print("axis", round(axis, 1), "head scale", round(sc, 3), "paste", px, py, head_s.size)
