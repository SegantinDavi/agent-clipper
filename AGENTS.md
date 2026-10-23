# 🤖 Diretrizes para Agentes de IA (AGENTS.md)

**Atenção, Agente de IA/LLM:** Ao auxiliar na escrita de código, refatoração ou debug deste repositório, você deve ler e obedecer estritamente às regras arquiteturais e limitações de hardware definidas neste documento.

## 📌 Contexto do Projeto

Este é o **agent-clipper**, um pipeline 100% autônomo, local, de custo zero e rodando em ambiente isolado (Docker) para ingestão de vídeos longos do YouTube e conversão para formatos curtos e verticais (Shorts/TikTok/Reels).
Todo o processamento de linguagem (LLM) e transcrição roda localmente na máquina do usuário.

## 🛠️ Stack Tecnológico Restrito

- **Python:** 3.12+
- **Ambiente:** Docker (Debian-slim) sobre WSL2 (Ubuntu) limitados a 8GB RAM e 8GB Swap.
- **LLM Backend Exclusivo:** Ollama (Qwen2.5:14b). NÃO use APIs externas (OpenAI) e NÃO sugira o uso de múltiplos modelos (ex: DeepSeek + Qwen) devido à restrição de 12GB VRAM. Use `base_url="http://127.0.0.1:11434/v1"`.
- **Orquestração e Extração:** `langgraph`, `instructor`, `pydantic`. (O uso de `autogen` é estritamente proibido).
- **Edição de Vídeo:** `moviepy==1.0.3` (NÃO utilize métodos da v2.x).
- **Processamento de Imagem/Texto:** `imagemagick` + `fonts-liberation`
- **Transcrição:** `faster-whisper`
- **Download:** `yt-dlp`

## 🚨 Regras Arquiteturais Absolutas (Não negocie estas regras)

### 1. Gerenciamento de Memória (WSL 8GB RAM & RTX 3060 12GB VRAM)

O ambiente opera no limite físico de memória.

- **Transcrição na CPU:** O `faster-whisper` DEVE rodar na CPU (`device="cpu"`, `compute_type="int8"`). A VRAM da CUDA é reservada 100% para o Qwen2.5.
- **Prevenção de Memory Leak (RAM):** Após a conclusão da transcrição de qualquer vídeo ou chunk, é obrigatório destruir a instância do modelo e forçar a limpeza de memória (`del model` seguido de `import gc; gc.collect()`).
- **Dependência Fixada:** A biblioteca `av` deve estar fixada em `<19` no `Dockerfile` para evitar crash (`metadata_errors`) durante a extração de áudio.

### 2. Ingestão e Fatiamento Preventivo (Chunking)

Para evitar o estouro da janela de contexto do LLM e o esgotamento de RAM:

- **Corte via FFmpeg:** Vídeos extensos (acima de ~15 min) não devem ser processados de uma vez. Use o filtro `silencedetect` do FFmpeg via subprocess para fatiar o vídeo bruto em chunks lógicos de áudio antes de enviar para o LLM.
- **Otimização de Transcrição:** A `transcript_string` enviada ao modelo LLM NUNCA deve conter timestamps palavra por palavra. Agrupe os tempos por frases ou segmentos para economizar tokens. O array granulado de palavras (`word_timestamps_list`) deve transitar pelo estado oculto apenas para ser usado no nó de Edição.

### 3. Orquestração Obrigatória (LangGraph)

O projeto abandonou a orquestração conversacional procedural. Todo o fluxo deve ser um DAG (Directed Acyclic Graph).

- Use `StateGraph` do `langgraph`.
- Defina o estado global (`VideoState`) usando `TypedDict`, trafegando apenas URIs de arquivos (salvos no host) e objetos serializáveis enxutos.
- **Persistência:** Configure o Checkpointer (`SqliteSaver`) apontando para um banco na pasta montada no Docker (ex: `/app/output/estado.db`) para garantir retomada caso o container sofra crash.

### 4. Padrão "Cognitive Routing" (Single-Model)

Use dois nós sequenciais operando o MESMO modelo (Qwen2.5) para separar raciocínio de formatação, maximizando o QI do pipeline:

- **Nó 1 (Pensador):** Recebe a transcrição e tem liberdade total para escrever parágrafos de raciocínio (Chain of Thought).
- **Nó 2 (Extrator):** Lê o raciocínio do Nó 1 e formata os dados.

### 5. Extração e Tratamento (O Fim das Alucinações)

É expressamente proibido o uso de Regex (`re.search`) ou `json.loads` manual para limpar marcações (como ```json ou TERMINATE) das respostas da IA.

- Utilize exclusivamente **Constrained Decoding** acoplando a biblioteca `instructor` com classes do `pydantic` (ex: `class Corte(BaseModel)`).
- OLLAMA local será forçado pelo schema Pydantic a retornar a estrutura de dados Python exata, impossibilitando erros de sintaxe e alucinações de formatação.

### 6. Manipulação de Vídeo (MoviePy & ImageMagick)

- **Dimensões Pares:** O H.264 quebra (`BrokenPipeError`) se largura/altura forem ímpares. Sempre force pares no crop (`if new_width % 2 != 0: new_width -= 1`).
- **Compatibilidade:** A exportação do vídeo (`write_videofile`) exige: `ffmpeg_params=["-pix_fmt", "yuv420p", "-profile:v", "main"]`.
- **Fontes:** Use estritamente fontes do `fonts-liberation` (ex: `font="Liberation-Sans-Bold"`). Nenhuma fonte do Windows.

### 7. Containerização e Variáveis (Dockerfile)

- A instalação de pacotes pesados (`faster-whisper`, `ctranslate2`, `onnxruntime`, `av<19`) deve ser feita isolada do resto do `requirements.txt` via `--prefer-binary`.
- Nenhuma URL ou parâmetro deve ficar _hardcoded_ no Python. A inicialização deve ler a variável de ambiente via `os.getenv` (ex: injetada via `docker run -e YOUTUBE_URL=...`).
- Todo o output final (vídeos, logs e estado) deve ser gerado no volume mapeado `/app/output`.

### 8. Padrões de Código (Clean Code)

- **Nomenclatura em Inglês:** Todas as variáveis, funções, classes, métodos e argumentos devem ser nomeados estritamente em inglês para manter o padrão universal de desenvolvimento.
- **Limitação de Comentários:** O código deve ser limpo e autoexplicativo. Evite comentários redundantes que explicam "o que" o código faz. Restrinja o uso de comentários apenas para documentar o "porquê" de lógicas complexas, decisões arquiteturais ou contornos de limitações físicas do ambiente.
