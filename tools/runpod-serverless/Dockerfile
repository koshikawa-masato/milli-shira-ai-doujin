# Krea2 編集ワーカー（RunPod Serverless）。モデルは同梱せず Network volume から読む
# Pod と同じベース（torch 2.8 / CUDA 12.8 / Python 3.12）
FROM runpod/pytorch:1.0.2-cu1281-torch280-ubuntu2404
ARG MUSUBI_COMMIT=e0cbd8f3dfe38365b10f8bc790b980f8894e8ba1
WORKDIR /app
RUN apt-get update -qq && apt-get install -y -qq --no-install-recommends git && rm -rf /var/lib/apt/lists/* \
 && git clone -q https://github.com/kohya-ss/musubi-tuner.git && cd musubi-tuner && git checkout -q $MUSUBI_COMMIT \
 # ベース同梱の torch を流用しつつ、musubi の依存は venv 側に入れる（システム側を上書きしようとして失敗するのを避ける）
 && python -m venv --system-site-packages /opt/venv && /opt/venv/bin/pip install --no-cache-dir -e . runpod
ENV KREA2_ROOT=/runpod-volume/krea2 PYTHONUNBUFFERED=1 PATH=/opt/venv/bin:$PATH
COPY handler.py /app/handler.py
CMD ["/opt/venv/bin/python", "-u", "/app/handler.py"]
