import requests
from autogen import UserProxyAgent, AssistantAgent, GroupChat, GroupChatManager

# 1. Configuração de LLM e Endpoints
llm_config_manager = {
    "base_url": "http://127.0.0.1:11434/v1",
    "api_key": "ollama",
    "model": "qwen2.5:14b"
}

llm_config_analyst = {
    "base_url": "http://127.0.0.1:11434/v1",
    "api_key": "ollama",
    "model": "deepseek-r1:8b"
}

llm_config_coder = {
    "base_url": "http://127.0.0.1:11434/v1",
    "api_key": "ollama",
    "model": "qwen2.5-coder:14b"
}

# 2. Gerenciamento de VRAM
def force_unload_model(model_name: str):
    try:
        response = requests.post(
            "http://127.0.0.1:11434/api/generate",
            json={"model": model_name, "keep_alive": 0}
        )
        if response.status_code == 200:
            print(f"[VRAM Manager] Model {model_name} unloaded successfully.")
        else:
            print(f"[VRAM Manager] Failed to unload model {model_name}: {response.text}")
    except Exception as e:
        print(f"[VRAM Manager] Error unloading model {model_name}: {e}")

# 3. Definição dos Agentes
admin = UserProxyAgent(
    name="Admin",
    human_input_mode="NEVER",
    code_execution_config={"use_docker": False}
)

orchestrator_manager = AssistantAgent(
    name="Orchestrator_Manager",
    llm_config=llm_config_manager,
    system_prompt="Receba um link de YouTube, planeje os passos e chame os outros agentes na ordem correta, finalizando a tarefa quando o vídeo estiver editado."
)

content_analyst = AssistantAgent(
    name="Content_Analyst",
    llm_config=llm_config_analyst,
    system_prompt=(
        "Você é um Analista de Conteúdo Especialista e Diretor de Vídeo para YouTube Shorts e TikTok.\n"
        "Sua única tarefa é receber a transcrição de um vídeo com timestamps e identificar os 3 melhores cortes que tenham alto potencial de engajamento (gancho forte, retenção e conclusão).\n\n"
        "REGRAS ESTRITAS DE PREVENÇÃO DE ALUCINAÇÃO:\n"
        "1. Você SÓ PODE usar os timestamps (start_time e end_time) que existem exatamente no texto fornecido.\n"
        "2. NUNCA invente, arredonde ou adivinhe segundos ou minutos.\n"
        "3. Use o seu raciocínio (tags <think>) para avaliar a qualidade do corte antes de gerar a resposta final.\n\n"
        "FORMATO DE SAÍDA OBRIGATÓRIO:\n"
        "Após o seu raciocínio, você deve retornar APENAS um bloco de código JSON válido, sem texto adicional antes ou depois do bloco. O formato deve ser exatamente este:\n\n"
        "```json\n"
        "[\n"
        "  {\n"
        "    \"title\": \"Título Curto e Chamativo\",\n"
        "    \"exact_quote_start\": \"Primeiras 5 palavras da fala exata onde o corte começa\",\n"
        "    \"start_time\": 12.5,\n"
        "    \"end_time\": 45.2,\n"
        "    \"justification\": \"Por que este corte retém a atenção\"\n"
        "  }\n"
        "]\n"
        "```"
    )
)

video_coder = AssistantAgent(
    name="Video_Coder",
    llm_config=llm_config_coder,
    system_prompt=(
        "Receber timestamps e escrever scripts em Python usando a biblioteca moviepy para cortar e salvar o vídeo.\n"
        "Use a biblioteca re (Regex) ou json para extrair apenas o conteúdo que estiver dentro do bloco ```json gerado pelo Analyst, ignorando qualquer texto fora dele (como as tags )."
    )
)

# 4. Registro de Ferramentas (Tools Stubs)
def download_video_and_transcript(url: str) -> dict:
    """Download video and transcript using yt-dlp."""
    pass

def execute_moviepy_script(script_code: str) -> str:
    """Execute moviepy script."""
    pass

# Ensure autogen is imported
import autogen

autogen.agentchat.register_function(
    name="download_video_and_transcript",
    function=download_video_and_transcript,
    description="Download video and transcript using yt-dlp."
)

autogen.agentchat.register_function(
    name="execute_moviepy_script",
    function=execute_moviepy_script,
    description="Execute moviepy script."
)

# 5. Orquestração (Group Chat)
groupchat = GroupChat(
    agents=[admin, orchestrator_manager, content_analyst, video_coder],
    speaker_selection_method="auto"
)

groupchat_manager = GroupChatManager(
    groupchat=groupchat,
    llm_config=llm_config_manager
)

# VRAM Management
AGENT_MODELS = {
    "Orchestrator_Manager": "qwen2.5:14b",
    "Content_Analyst": "deepseek-r1:8b",
    "Video_Coder": "qwen2.5-coder:14b"
}

def vram_management_callback(sender, message, receiver, **kwargs):
    if sender in AGENT_MODELS:
        previous_model = AGENT_MODELS[sender]
        force_unload_model(previous_model)
        print(f"[VRAM Manager] Switching from model {previous_model} to {AGENT_MODELS[receiver]}...")

groupchat_manager.register_reply(vram_management_callback)

if __name__ == "__main__":
    groupchat_manager.start()
    admin.initiate_chat(
        message="Por favor, baixe e edite os melhores momentos deste vídeo: https://youtube.com/watch?v=TESTE"
    )
