#!/bin/bash
set -x
export PATH=$PATH:/usr/lib/wsl/lib
mkdir -p ~/krea2/{models,dataset/images,cache,output,scripts}
cd ~/krea2
[ -d musubi-tuner ] || git clone https://github.com/kohya-ss/musubi-tuner.git
cd musubi-tuner
[ -x .venv/bin/python ] || python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
pip install -e .
python -c "import torch; print('CUDA:', torch.cuda.is_available(), torch.cuda.get_device_name(0))"
cd ~/krea2/models
huggingface-cli download Comfy-Org/Qwen-Image_ComfyUI split_files/vae/qwen_image_vae.safetensors --local-dir .
huggingface-cli download Comfy-Org/Qwen3-VL text_encoders/qwen3vl_4b_bf16.safetensors --local-dir .
ln -sf split_files/vae/qwen_image_vae.safetensors qwen_image_vae.safetensors
ln -sf text_encoders/qwen3vl_4b_bf16.safetensors qwen3vl_4b_bf16.safetensors
ls -la ~/krea2/models ~/krea2/models/split_files/vae ~/krea2/models/text_encoders
echo "=== SETUP DONE ==="
