import requests
from autogen import UserProxyAgent, AssistantAgent, GroupChat, GroupChatManager, agentchat
from ingestion import download_video_and_transcript
from editor import cut_and_format_video

# 1. Configuração de LLM e Endpoints
llm_config_manager = {
    "base_url": "http://127.0.0.1:11434/v1",
    "api_key": "ollama",
    "model": "qwen2.5:14b",
    "max_tokens": 1500,
    "stop": ["TERMINATE"],
    "timeout": 300
}

llm_config_analyst = {
    "base_url": "http://127.0.0.1:11434/v1",
    "api_key": "ollama",
    "model": "deepseek-r1:8b",
    "max_tokens": 1500,
    "stop": ["TERMINATE", "```\n"],
    "timeout": 300
}

llm_config_coder = {
    "base_url": "http://127.0.0.1:11434/v1",
    "api_key": "ollama",
    "model": "qwen2.5-coder:14b",
    "max_tokens": 1500,
    "stop": ["TERMINATE", "```\n"],
    "timeout": 300
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
            print(f"[VRAM Manager] Failed to unload model {model_name}. Status code: {response.status_code}")
    except Exception as e:
        print(f"[VRAM Manager] Error unloading model {model_name}: {e}")

# 3. Inicialização dos agentes
manager = GroupChatManager()
admin = UserProxyAgent(name="admin", system_message="Você é um administrador assistente.", max_tokens=1000, llm_config=llm_config_manager)
content_analyst = AssistantAgent(name="ContentAnalyst", system_message="Você é um assistente para analisar e extrair informações da transcrição.", max_tokens=1000, llm_config=llm_config_analyst)
video_editor = AssistantAgent(name="VideoEditor", system_message="Você é um assistente para editar e gerar vídeos.", max_tokens=1000, llm_config=llm_config_coder)

manager.register(admin)
manager.register(content_analyst)
manager.register(video_editor)

# 4. Inicialização do chat
admin.initiate_chat(manager, message="Por favor, baixe o vídeo [https://www.youtube.com/watch?v=jNQXAC9IVRw](https://www.youtube.com/watch?v=jNQXAC9IVRw). Em seguida, passe a transcrição para o ContentAnalyst extrair os cortes em JSON. Por fim, mande o JSON para o VideoEditor editar. Não pare até os arquivos existirem.")
