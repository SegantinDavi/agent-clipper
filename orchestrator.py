import requests
from autogen import UserProxyAgent, AssistantAgent, GroupChat, GroupChatManager

# 1. Configuração de LLM e Endpoints
llm_config_manager = {
    "base_url": "http://localhost:11434/v1",
    "api_key": "ollama",
    "model": "qwen2.5:14b"
}

llm_config_analyst = {
    "base_url": "http://localhost:11434/v1",
    "api_key": "ollama",
    "model": "deepseek-r1:8b"
}

llm_config_coder = {
    "base_url": "http://localhost:11434/v1",
    "api_key": "ollama",
    "model": "qwen2.5-coder:14b"
}

# 2. Gerenciamento de VRAM
def unload_ollama_model(model_name: str):
    response = requests.post(
        "http://localhost:11434/api/generate",
        json={"model": model_name, "keep_alive": 0}
    )
    if response.status_code != 200:
        raise Exception(f"Failed to unload model {model_name}: {response.text}")

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
    system_prompt="Processar transcrições de vídeos e devolver um JSON estrito contendo timestamps (start, end) e justificativas para os cortes."
)

video_coder = AssistantAgent(
    name="Video_Coder",
    llm_config=llm_config_coder,
    system_prompt="Receber timestamps e escrever scripts em Python usando a biblioteca moviepy para cortar e salvar o vídeo."
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

if __name__ == "__main__":
    groupchat_manager.start()
    admin.initiate_chat(
        message="Por favor, baixe e edite os melhores momentos deste vídeo: https://youtube.com/watch?v=TESTE"
    )
