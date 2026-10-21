FROM python:3.12-slim

# Instala dependências do sistema, ImageMagick e fontes padrão do Linux
RUN apt-get update && \
    apt-get install -y ffmpeg libgomp1 nodejs imagemagick fonts-liberation fontconfig && \
    rm -rf /var/lib/apt/lists/*

# Remove a regra de segurança do ImageMagick em qualquer versão instalada
RUN sed -i '/pattern="@\*"/d' /etc/ImageMagick*/policy.xml

WORKDIR /app

COPY requirements.txt .

# Etapa 1: Instala pacotes pesados de IA
RUN pip install --no-cache-dir --prefer-binary faster-whisper ctranslate2 onnxruntime av

# Etapa 2: Instala o restante das dependências
RUN pip install --no-cache-dir --prefer-binary -r requirements.txt && \
    rm -rf /tmp/* /root/.cache/pip

COPY . .

CMD ["python", "orchestrator.py"]
