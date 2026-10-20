# Auto Video Factory 🎬🤖

Um pipeline 100% autônomo e local para criação de vídeos curtos (YouTube Shorts/TikTok). O sistema baixa vídeos do YouTube, transcreve o áudio silenciosamente, utiliza agentes de IA para identificar os momentos de maior retenção e corta/formata os clipes automaticamente na vertical.

**Stack Tecnológico:** Python, AutoGen, Ollama (Qwen2.5), yt-dlp, faster-whisper, MoviePy.

---

## 🛑 Pré-requisitos

Antes de iniciar, certifique-se de ter os seguintes componentes instalados na sua máquina:

- **Python:** Versão 3.12 ou superior.
- **FFmpeg:** Essencial para o download e manipulação de vídeo/áudio.
  - No Ubuntu/WSL, instale com: `sudo apt update && sudo apt install ffmpeg -y`
- **Ollama:** Instalado e rodando localmente.
  - Baixe o modelo principal executando: `ollama run qwen2.5:14b`

## ⚠️ Atenção Usuários de WSL2 (Windows)

Se você está rodando este projeto dentro do WSL (Ubuntu) no Windows, é **obrigatório** configurar a rede do WSL para o modo espelhado. Isso permite que o código Python dentro do WSL consiga se comunicar perfeitamente com o Ollama rodando no Windows na porta `11434`.

1. No Windows, abra o bloco de notas e edite (ou crie) o arquivo `C:\Users\<SeuUsuario>\.wslconfig`.
2. Adicione as seguintes linhas:
   ```ini
   [wsl2]
   networkingMode=mirrored
   ```
3. Salve o arquivo, abra o PowerShell do Windows e reinicie o WSL com o comando: `wsl --shutdown`.

## ⚙️ Variáveis de Ambiente e Configuração

Uma das grandes vantagens deste projeto é que ele é **100% Local e Gratuito**.

- **NÃO** é necessário criar arquivo `.env`.
- **NÃO** é necessário configurar chaves da API da OpenAI.

A comunicação com a IA já está configurada diretamente nos dicionários do arquivo `orchestrator.py`, apontando para a sua máquina:

```python
"base_url": "http://127.0.0.1:11434/v1"
"api_key": "ollama"
```

## 🚀 Instalação (Quick Start)

1. Clone este repositório e acesse a pasta do projeto.
2. Crie um ambiente virtual Python:
   ```bash
   python3 -m venv venv
   ```
3. Ative o ambiente virtual:
   - **Linux/WSL:** `source venv/bin/activate`
   - **Windows:** `venv\Scripts\activate`
4. Instale as dependências com as versões estabilizadas:
   ```bash
   pip install -r requirements.txt
   ```

## 🕹️ Como Usar

1. Abra o arquivo `orchestrator.py` no seu editor de código.
2. Role até o final do arquivo (próximo à linha `if __name__ == "__main__":`).
3. Altere a variável `url` para o link do vídeo do YouTube que você deseja processar:
   ```python
   url = "https://www.youtube.com/watch?v=SEU_LINK_AQUI"
   ```
4. Salve o arquivo e rode o orquestrador no terminal:
   ```bash
   python orchestrator.py
   ```

O sistema executará todas as etapas de forma autônoma. Ao finalizarem, os cortes verticais estarão disponíveis e prontos para uso na pasta `/output`!
