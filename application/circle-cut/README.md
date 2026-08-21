# C109 サークルカット — 制作経緯

サークル名: **くろぱんだ団** / 頒布物: **ミリしらが AI で同人誌を作ってみた。**
テンプレート: `B0400_template.png`（635×903 px。左上の小枠はスペース番号欄なので空ける）

## 成果物

| ファイル | 用途 |
|---|---|
| `C109_circlecut_C.png` | **採用（フルカラー）** |
| `C109_circlecut_C_gray.png` | **採用（グレースケール）**。申込登録用。8bit グレー、コントラスト 1.12 倍 |
| `C109_circlecut_A.png` | 下書き A: 基準画像（教室で手を振る）を流用。経過観察用 |
| `C109_circlecut_B.png` | 下書き B: 白背景アップを流用。経過観察用 |
| `src_floating_book_1200_s0.png` | C の元絵（LoRA kuropanda_v1 step 1200 / seed 0 の生成そのまま） |
| `src_floating_book_1200_s0_pupils.png` | C の元絵に黒目を描き足した版（実際に使用） |
| `src_best_waving.png` / `src_closeup_white.png` | A / B の元絵 |
| `make_circlecut.py` | 生成スクリプト |

## 経緯（2026-08-21）

1. **テンプレート解析**: 外枠内側 22..612 × 22..880、小枠 22..163 × 22..164、小枠右の帯 182..612 × 22..180 を実測
2. **下書き A / B**: 既存の生成画像（基準画像 / 白背景アップ）を本体に、上帯にサークル名＋副題、下帯にタイトルの 3 段構成。サークル名を「くろぱんた団」と誤記 → 「**くろぱんだ団**」に修正
3. **レイアウト変更（指示）**: 副題「Krea 2 LoRA で作る…」を削除。絵は番号欄以外の全面に敷き、文字は**黒＋太い白縁取り**で絵の上に載せる（背景が写り込んでも読めるように）
4. **C 案の絵を LoRA で生成（指示）**: 「斜め横向き、両手の手のひらを器のようにした上に同人誌が浮いている。その同人誌自体がミリしら本。ちょっとびっくりした表情」
   - LoRA `kuropanda_v1` step 1200 / seed 0、衣装のフル記述＋ポーズ文、白背景。1 枚目で採用
   - 表紙の中に同じ子が描かれる入れ子構図が自然に出た
   - LoRA 適用時の生成が 1 枚 14 分かかる問題を発見 → `gen.sh` に `--blocks_to_swap 12` を追加して 100 秒に改善
5. **C 案の組版**: 白背景の絵なので切り抜かず `--fit --yshift -0.2` で全体を収める（本・両手・耳が切れない）
6. **黒目の追加（指示）**: フードの白い目の縁に黒目が無かった → 再生成せず画像に直接描画。本人（右 19×22 px / 左 15×17 px）と、表紙の子（4.2×4.4 px / 2.4×2.8 px）の計 4 か所
7. **グレースケール版**: 申込登録がグレースケール必須のため作成。`~/Downloads/` にカラー・グレーの両方をコピー

## 再生成

```bash
cd application/circle-cut
# C（カラー）
python3 make_circlecut.py B0400_template.png src_floating_book_1200_s0_pupils.png C109_circlecut_C.png --fit --yshift -0.2
# A / B（切り抜きモード）
python3 make_circlecut.py B0400_template.png src_best_waving.png C109_circlecut_A.png
python3 make_circlecut.py B0400_template.png src_closeup_white.png C109_circlecut_B.png
# グレースケール
python3 -c "from PIL import Image, ImageOps, ImageEnhance; g=ImageEnhance.Contrast(ImageOps.grayscale(Image.open('C109_circlecut_C.png'))).enhance(1.12); g.save('C109_circlecut_C_gray.png', optimize=True)"
```

文言は `make_circlecut.py` 冒頭の `CIRCLE` / `TITLE_LINES` で変更する。

## 元絵のプロンプト（C）

```
kuropanda, a Japanese girl with black bob hair and dark brown eyes, wearing a black animal-ear hoodie with white drawstrings.
The hood is black with two round white ears on top, and the front of the hood has two white circular patches around the eye area.
The inside lining of the hood is a traditional Japanese hanafuda card pattern: red and orange maple leaves with a brown deer.
The hoodie body is black with a white kangaroo pocket.
Three-quarter view, her body turned diagonally, holding both hands together in front of her chest with palms up like a bowl.
A small doujinshi book floats magically above her cupped palms, glowing softly; the book cover shows the same girl in the black hoodie.
Slightly surprised expression with wide eyes and a small open mouth. Upper body, simple white background.
```

LoRA: `kuropanda_v1-step00001200.safetensors`（multiplier 1.0）、seed 0、Krea 2 Turbo、8 step。
ギャラリー: `circlecut` フォルダ（別 seed の予備 3 枚も同フォルダ）。
