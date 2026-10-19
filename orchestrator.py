import requests
from autogen import UserProxyAgent, AssistantAgent, GroupChat, GroupChatManager
from ingestion import download_video_and_transcript
from editor import cut_and_format_video

# 1. Configuração de LLM e Endpoints
llm_config_manager = {
    "base_url": "http://127.0.0.1:11434/v1",
    "api_key": "ollama",
    "model": "qwen2.5:14b",
    "max_tokens": 1500,
    "stop": ["TERMINATE"]
}

llm_config_analyst = {
    "base_url": "http://127.0.0.1:11434/v1",
    "api_key": "ollama",
    "model": "deepseek-r1:8b",
    "max_tokens": 1500,
    "stop": ["TERMINATE", "```\n"]
}

llm_config_coder = {
    "base_url": "http://127.0.0.1:11434/v1",
    "api_key": "ollama",
    "model": "qwen2.5-coder:14b",
    "max_tokens": 1500,
    "stop": ["TERMINATE", "```\n"]
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
    code_execution_config={"work_dir": ".", "use_docker": False},
    is_termination_msg=lambda x: isinstance(x, dict) and x.get("content", "") and "TERMINATE" in x.get("content", "")
)

orchestrator_manager = AssistantAgent(
    name="Orchestrator_Manager",
    llm_config=llm_config_manager,
    system_message="Receba um link de YouTube, planeje os passos e chame os outros agentes na ordem correta, finalizando a tarefa quando o vídeo estiver editado.\n\n"
                  "Quando todo o processo terminar e os vídeos finais estiverem salvos com sucesso no disco, responda APENAS com a palavra TERMINATE."
)

content_analyst = AssistantAgent(
    name="Content_Analyst",
    llm_config=llm_config_analyst,
    system_message=(
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
    system_message="Você é um assistente especializado em codificação de vídeo. Sua tarefa é receber o caminho do vídeo original e um JSON de timestamps, cortar os trechos e salvar no disco em formato vertical."
)

# 4. Registro de Ferramentas (AutoGen API)
autogen.agentchat.register_function(
    download_video_and_transcript,
    caller=orchestrator_manager,
    executor=admin,
    name="download_video_and_transcript",
    description="Baixa o vídeo e retorna a transcrição com timestamps."
)

autogen.agentchat.register_function(
    cut_and_format_video,
    caller=video_coder,
    executor=admin,
    name="cut_and_format_video",
    description="Recebe o caminho do vídeo e um JSON com timestamps, corta e salva os vídeos."
)

# 5. Inicialização do Grupo de Chat
group = GroupChat(
    agents=[admin, orchestrator_manager, content_analyst, video_coder],
    messages=[],
    max_round=15
)

# 6. Inicialização do Gerenciador de Grupo de Chat
manager = GroupChatManager(groupchat=group, llm_config=llm_config_manager)

# 7. Início do Processo
admin.initiate_chat(manager, message="Por favor, baixe o vídeo https://www.youtube.com/watch?v=jNQXAC9IVRw, analise a transcrição para encontrar os 3 melhores cortes e edite os vídeos.")
