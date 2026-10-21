# Agent Clipper 🎬🤖

Um pipeline 100% autônomo, local e isolado em container (Docker) para criação de vídeos curtos (YouTube Shorts / TikTok / Reels).

O sistema baixa vídeos do YouTube, transcreve o áudio via CPU (`faster-whisper`), utiliza agentes de IA (`AutoGen` + `Ollama`/`Qwen2.5`) para identificar os momentos de maior retenção e corta/formata os clipes automaticamente na vertical (9:16) com legendas dinâmicas.

**Stack Tecnológico:** Python 3.12, AutoGen, Ollama (Qwen2.5), yt-dlp, faster-whisper (CPU), MoviePy, ImageMagick e Docker.

---

## 🛑 Pré-requisitos

Antes de iniciar, certifique-se de ter os seguintes componentes configurados na sua máquina:

1. **Docker Desktop** (com suporte ao WSL2 habilitado no Windows).
2. **Ollama:** Instalado e rodando localmente no host.
   - Baixe e inicie o modelo executando: `ollama run qwen2.5:14b`

---

## ⚠️ Configuração Obrigatória do WSL2 (Windows)

Para que o container Docker consiga se comunicar com a API do Ollama na porta `11434` da sua máquina host sem configurações complexas de IP, a rede do WSL2 deve estar configurada no modo espelhado (_mirrored_).

1. No Windows, edite (ou crie) o arquivo `C:\Users\<SeuUsuario>\.wslconfig`.
2. Adicione as seguintes configurações de rede e memória:

```ini
[wsl2]
networkingMode=mirrored
memory=8GB
swap=8GB
```

3. Salve o arquivo e reinicie o WSL no PowerShell do Windows com o comando:

```powershell
wsl --shutdown
```

---

## 🚀 Como Usar com Docker (Recomendado / Sandboxed)

A execução via Docker garante que todas as dependências do sistema operacional (`ffmpeg`, `imagemagick`, `fonts-liberation`, `libgomp1`) estejam devidamente isoladas do seu sistema principal.

### 1. Construir a imagem Docker

No terminal do Ubuntu/WSL na pasta do projeto, rode:

```bash
docker build -t agent-clipper .
```

### 2. Configurar o link do vídeo

Abra o arquivo `orchestrator.py` e altere a variável `url` no final do arquivo:

```python
if __name__ == "__main__":
    url = "https://www.youtube.com/watch?v=SEU_LINK_AQUI"
```

### 3. Executar o container

Rode o container mapeando a pasta `./output` para que os vídeos gerados fiquem salvos no seu computador:

```bash
docker run --rm --network host -v $(pwd)/output:/app/output agent-clipper
```

Os clipes curtos formatados e legendados estarão disponíveis na pasta `./output` do seu repositório ao término da execução!

---

## ⚙️ Execução Local sem Docker (Desenvolvimento)

Caso prefira rodar fora do Docker, você precisará instalar as dependências do sistema operacional diretamente no seu Linux/WSL:

1. **Instalar dependências de sistema:**

   ```bash
   sudo apt update && sudo apt install -y ffmpeg libgomp1 nodejs imagemagick fonts-liberation fontconfig
   ```

2. **Criar e ativar o ambiente virtual Python:**

   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Instalar dependências Python:**

   ```bash
   pip install --prefer-binary -r requirements.txt
   ```

4. **Executar o orquestrador:**

   ```bash
   python orchestrator.py
   ```

---

## 🛠️ Variáveis de Ambiente e Comunicação

- **100% Local e Gratuito:** O projeto não exige chave de API da OpenAI ou arquivos `.env`.
- A comunicação com o Ollama local é feita diretamente em `http://127.0.0.1:11434/v1`.
