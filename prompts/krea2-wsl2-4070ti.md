# Krea 2 LoRA 手順書（RTX 4070 Ti 16GB / WSL2）

Claude機から 4070 Ti 機の WSL2 に入って動かす前提です。
（実機は RTX 4060 Ti 16GB / ホスト `kossy-ai-tech-1`、`ssh wsl2` で入れる。VRAM は同じ 16GB なので手順はそのまま）
工具はろてじん式と同じ **musubi-tuner** です。

- 学習: Krea 2 RAW
- 生成: Krea 2 Turbo
- 歩数: 1800 まで作って 1200 を候補採用

公式: https://github.com/kohya-ss/musubi-tuner/blob/main/docs/krea2.md

---

## 0. 機器の役割

- Claude機: 指示、キャプション案、進捗管理
- 4070 Ti 機 (WSL2): 学習と生成

Claude機からは SSH するだけ。

```bash
ssh user@4070ti-host
# Windows 側の WSL に入る
# 例: ssh user@192.168.x.x
# または Windows に入ったあと wsl -d Ubuntu
```

長時間作業は tmux を使う。

```bash
sudo apt update && sudo apt install -y tmux
tmux new -s krea2
```

切れたら `tmux attach -t krea2`

---

## 1. WSL2 の前提

Windows 側に NVIDIA ドライバ最新。WSL2 内で確認。

```bash
nvidia-smi
# command not found の場合は WSL 専用パスを通す
export PATH=$PATH:/usr/lib/wsl/lib
```

16GB の GPU が出ること。
Python 3.10 以上、ディスクに 80GB 以上空きが安心。

---

## 2. フォルダ

```bash
mkdir -p ~/krea2/{models,dataset,cache,output,scripts}
cd ~/krea2
```

```
~/krea2/
  models/
    raw.safetensors
    turbo.safetensors
    qwen_image_vae.safetensors
    qwen3vl_4b_bf16.safetensors
  dataset/
    images/          # png + 同名 txt
  cache/
  output/
  musubi-tuner/
  dataset.toml
```

---

## 3. musubi-tuner インストール

```bash
cd ~/krea2
sudo apt install -y git python3-venv python3-pip
git clone https://github.com/kohya-ss/musubi-tuner.git
cd musubi-tuner
python3 -m venv .venv
source .venv/bin/activate

pip install -U pip
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124
pip install -e .
```

CUDA 12.8 なら `cu128` に変える。

```bash
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
```

`True NVIDIA GeForce RTX 4070 Ti` でOK。

---

## 4. モデル入手

Hugging Face アカウントが必要。Krea 2 のライセンス同意も必要なことがある。

```bash
# musubi-tuner は huggingface_hub==0.34.3 を要求するので上げない（pip install -e . で入る版のまま使う）
huggingface-cli login
```

Krea-2-Raw / Krea-2-Turbo は **gated**。先に HF のモデルページで同意し、`huggingface-cli login` にトークンを入れる。
VAE と Text Encoder は gated ではないので先に落とせる。

```bash
cd ~/krea2/models

# DiT RAW
huggingface-cli download krea/Krea-2-Raw raw.safetensors --local-dir .

# DiT Turbo
huggingface-cli download krea/Krea-2-Turbo turbo.safetensors --local-dir .

# VAE（Qwen-Image-Edit_ComfyUI には無い。Qwen-Image_ComfyUI が正）
huggingface-cli download Comfy-Org/Qwen-Image_ComfyUI split_files/vae/qwen_image_vae.safetensors --local-dir .

# Text Encoder
huggingface-cli download Comfy-Org/Qwen3-VL text_encoders/qwen3vl_4b_bf16.safetensors --local-dir .

# --local-dir . だとサブフォルダ付きで落ちるので、手順書のパスに合わせてリンクを張る
ln -sf split_files/vae/qwen_image_vae.safetensors qwen_image_vae.safetensors
ln -sf text_encoders/qwen3vl_4b_bf16.safetensors qwen3vl_4b_bf16.safetensors
```

ファイル名が違う場合は実際のパスに合わせる。

---

## 5. データセット

20–30枚。

- 正面 / 斜め / 横
- 全身を数枚
- 表情差分
- 服は固定、背景はバラす
- 崩れ画は入れない

各画像に同名 `.txt` を置く。

```
dataset/images/001.png
dataset/images/001.txt
```

`001.txt` 例:

```text
kuropanda, 1girl, black panda hoodie, front view, standing, simple background
```

### dataset.toml

`~/krea2/dataset.toml`

```toml
[general]
resolution = [512, 512]
caption_extension = ".txt"
batch_size = 1
enable_bucket = true
bucket_no_upscale = false

[[datasets]]
image_directory = "/home/USER/krea2/dataset/images"
cache_directory = "/home/USER/krea2/cache"
num_repeats = 1
```

`USER` は実際のユーザ名に置換。

---

## 6. キャッシュ（学習前に必須）

```bash
cd ~/krea2/musubi-tuner
source .venv/bin/activate

python src/musubi_tuner/krea2_cache_latents.py \
  --dataset_config ~/krea2/dataset.toml \
  --vae ~/krea2/models/qwen_image_vae.safetensors

python src/musubi_tuner/krea2_cache_text_encoder_outputs.py \
  --dataset_config ~/krea2/dataset.toml \
  --text_encoder ~/krea2/models/qwen3vl_4b_bf16.safetensors \
  --batch_size 1
```

---

## 7. 学習（16GB 用）

12GB よりゆとるいが、RAW は重いので FP8 + block swap は残す。

```bash
cd ~/krea2/musubi-tuner
source .venv/bin/activate

accelerate launch --num_cpu_threads_per_process 1 --mixed_precision bf16 \
  src/musubi_tuner/krea2_train_network.py \
  --dit ~/krea2/models/raw.safetensors \
  --vae ~/krea2/models/qwen_image_vae.safetensors \
  --dataset_config ~/krea2/dataset.toml \
  --sdpa --mixed_precision bf16 \
  --timestep_sampling shift --weighting_scheme none --discrete_flow_shift 2.5 \
  --optimizer_type adamw8bit --learning_rate 1e-4 \
  --gradient_checkpointing \
  --max_data_loader_n_workers 2 --persistent_data_loader_workers \
  --network_module networks.lora_krea2 \
  --network_dim 32 --network_alpha 32 \
  --fp8_base --fp8_scaled \
  --blocks_to_swap 16 \
  --max_train_steps 1800 \
  --save_every_n_steps 300 \
  --seed 42 \
  --output_dir ~/krea2/output \
  --output_name kuropanda_krea2
```

OOM したら `--blocks_to_swap 20` または `26` 。
ゆとるくなら `12`。

出力例:

- `kuropanda_krea2-000300.safetensors`
- `kuropanda_krea2-000600.safetensors`
- `kuropanda_krea2-000900.safetensors`
- `kuropanda_krea2-001200.safetensors`
- `kuropanda_krea2-001500.safetensors`
- `kuropanda_krea2-001800.safetensors`

---

## 8. 生成で比較

同じプロンプト・同じ seed で各チェックポイントを出す。

```bash
python src/musubi_tuner/krea2_generate_image.py \
  "kuropanda, 1girl, black panda hoodie, standing, looking at viewer, simple background" \
  --dit ~/krea2/models/turbo.safetensors \
  --vae ~/krea2/models/qwen_image_vae.safetensors \
  --text_encoder ~/krea2/models/qwen3vl_4b_bf16.safetensors \
  --steps 8 --guidance_scale 1 --mu 1.15 \
  --width 1024 --height 1024 \
  --attn_mode torch \
  --seed 0 \
  --save_path ~/krea2/output/compare \
  --lora_weight ~/krea2/output/kuropanda_krea2-001200.safetensors \
  --lora_multiplier 1.0 \
  --fp8_scaled
```

1200 を基準に、900 / 1500 も見る。
背景まで一致し始めたら歩数が過ぎている。

---

## 9. Real-ESRGAN

```bash
pip install realesrgan
# または
# git clone https://github.com/xinntao/Real-ESRGAN.git
```

採用画像を 2x または 4x に拡大し、印刷用は 350dpi 目安で整える。

---

## 10. Claude 機からの使い方

1. 素材画像を Claude 機で作る
2. `scp` または `rsync` で 4070 Ti 機の `dataset/images` へ
3. この手順書をそのまま貼り付ける
4. 出力 LoRA を戻す

```bash
rsync -avP ./dataset/images/ user@4070ti:~/krea2/dataset/images/
rsync -avP user@4070ti:~/krea2/output/ ./output/
```

---

## スクリプト（`prompts/krea2-scripts/`）

WSL2 の `~/krea2/scripts/` に同じものを置いてある。

- `setup_krea2.sh`: §2〜§4 の環境構築と VAE / TE 取得を一括で行う
- `download_dit.sh`: HF ログイン後に Turbo / Raw を取得
- `gen.sh "プロンプト" [seed] [LoRAパス] [出力dir]`: §8 の生成。LoRA 無しなら第3引数を `""`

```bash
~/krea2/scripts/gen.sh "kuropanda, 1girl, black panda hoodie" 0 ~/krea2/output/kuropanda_krea2-001200.safetensors
```

---

## こまったとき

- `nvidia-smi` が出ない: Windows ドライバ更新、WSL 再起動
- OOM: `--blocks_to_swap` を増やす
- キャラが定まらない: 画像を減らし、崩れを除く
- 背景まで変わらない: 1200 より前のチェックポイントを使う
