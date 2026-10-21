# 🤖 Diretrizes para Agentes de IA (AGENTS.md)

**Atenção, Agente de IA/LLM:** Ao auxiliar na escrita de código, refatoração ou debug deste repositório, você deve ler e obedecer estritamente às regras arquiteturais e limitações de hardware definidas neste documento.

## 📌 Contexto do Projeto

Este é o **agent-clipper**, um pipeline 100% autônomo, local, de custo zero e rodando em ambiente isolado (Docker) para ingestão de vídeos longos do YouTube e conversão para formatos curtos e verticais (Shorts/TikTok/Reels).
Todo o processamento de linguagem (LLM) e transcrição roda localmente na máquina do usuário.

## 🛠️ Stack Tecnológico Restrito

- **Python:** 3.12+
- **Ambiente:** Docker (Debian-slim) sobre WSL2 (Ubuntu)
- **LLM Backend:** Ollama (NÃO crie códigos que exijam a API da OpenAI. Use sempre `base_url="http://127.0.0.1:11434/v1"` via `--network host`).
- **Edição de Vídeo:** `moviepy==1.0.3` (NÃO utilize métodos exclusivos do MoviePy v2.x).
- **Processamento de Imagem/Texto:** `imagemagick` + `fonts-liberation`
- **Transcrição:** `faster-whisper`
- **Download:** `yt-dlp`

## 🚨 Regras Arquiteturais Absolutas (Não negocie estas regras)

### 1. Gerenciamento de VRAM & Recursos de Hardware (RTX 3060 12GB)

O ambiente tem recursos limitados de VRAM.

- **Transcrição:** O `faster-whisper` DEVE rodar na CPU (`device="cpu"`, `compute_type="int8"`). Nunca direcione o Whisper para a CUDA, pois a VRAM está reservada exclusivamente para o Ollama (Qwen/DeepSeek).
- **PyAV:** A dependência `av` deve estar fixada em `<19` para evitar quebra no `metadata_errors` durante a extração de áudio.

### 2. Manipulação de Vídeo e Renderização de Texto (MoviePy & ImageMagick)

Já resolvemos bugs complexos de codecs, permissões do Linux e renderização de fontes:

- **Dimensões Pares:** O codec `libx264` quebra com `BrokenPipeError` se a largura (width) ou altura (height) do recorte for um número ímpar. Sempre force cálculos matemáticos que garantam números pares (ex: `if new_width % 2 != 0: new_width -= 1`).
- **Compatibilidade de Player:** Para que o vídeo seja reproduzido nativamente no Windows e VS Code, você DEVE incluir os parâmetros do FFmpeg na exportação: `ffmpeg_params=["-pix_fmt", "yuv420p", "-profile:v", "main"]`.
- **Fontes em Containers Linux:** NUNCA utilize fontes proprietárias do Windows (como `Arial` ou `Arial-Bold`) no `TextClip`. Use sempre fontes nativas do pacote `fonts-liberation` instalado na imagem (ex: `font="Liberation-Sans-Bold"`).
- **Política do ImageMagick:** Qualquer alteração no `Dockerfile` deve manter a remoção da política de restrição de leitura de arquivos temporários (`@*`) do ImageMagick (`sed -i '/pattern="@\*"/d' /etc/ImageMagick*/policy.xml`).

### 3. Containerização e Gerenciamento de Build (Dockerfile)

O projeto é executado dentro de containers Docker.

- **Prevenção de Estouro de RAM (OOM):** NUNCA agrupe a instalação do `requirements.txt` inteiro em uma única instrução `pip install` pesada no `Dockerfile`. Mantenha a instalação das bibliotecas de IA/C++ (`faster-whisper`, `ctranslate2`, `onnxruntime`, `av`) isolada em uma camada anterior usando `--prefer-binary`.
- **Persistência de Arquivos:** Todo o código Python deve gerar/exportar os arquivos finais na pasta `/app/output` (que é montada via volume para `./output` no host).

### 4. Extração e Tratamento de JSON (Prevenção de Alucinações)

Agentes LLM frequentemente injetam marcações Markdown (```json) ou palavras como `TERMINATE` na saída estruturada.

- Nunca passe o output do LLM diretamente para um `json.loads()`.
- Use extração por Expressões Regulares (`re.search(r'\[.*\]', text, re.DOTALL)`) ou implemente _Constrained Decoding_ com Pydantic (ex: bibliotecas `instructor`) para garantir o isolamento apenas da estrutura de dados válida.
- Não delegue ao LLM a tarefa de invocar a última ferramenta Python por meio de Function Calling nativo se houver risco de alucinação de argumentos; prefira o fluxo onde o script em Python orquestra a chamada de função após capturar e validar o JSON do agente.

### 5. Orquestração Futura (Meta de Migração)

O projeto iniciou com AutoGen v0.2.x, mas a arquitetura-alvo visa um design determinístico de grafos.
Ao sugerir refatorações estruturais em grande escala, prefira abordagens baseadas em State Machines (como **LangGraph**), separando a carga cognitiva (Agente Analista) da carga formativa (Agente de Extração/Instructor).
