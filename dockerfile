FROM python:3.12-slim

RUN apt-get update && \
    apt-get install -y ffmpeg libgomp1 nodejs imagemagick fonts-liberation fontconfig && \
    rm -rf /var/lib/apt/lists/*

RUN sed -i '/pattern="@\*"/d' /etc/ImageMagick*/policy.xml

WORKDIR /app

COPY requirements.txt .
COPY requirements-cuda.txt .

RUN pip install --no-cache-dir --prefer-binary -r requirements-cuda.txt onnxruntime "av<19"

RUN pip install --no-cache-dir --prefer-binary -r requirements.txt && \
    rm -rf /tmp/* /root/.cache/pip

COPY . .

ENV PYTHONPATH=/app/src

EXPOSE 8765

CMD ["python", "-m", "clipper.core.orchestrator"]
