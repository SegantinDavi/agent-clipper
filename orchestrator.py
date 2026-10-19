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
        print(f"[VRAM Manager] Exception occurred while unloading model {model_name}: {e}")

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
    system_message="You are the Orchestrator Manager. Your task is to coordinate the workflow between the agents. Ensure that the video is downloaded, transcribed, and then edited according to the specified cuts."
)

content_analyst = AssistantAgent(
    name="Content_Analyst",
    llm_config=llm_config_analyst,
    system_message="You are the Content Analyst. Your task is to analyze the video transcript and extract the relevant cuts in JSON format."
)

video_coder = AssistantAgent(
    name="Video_Coder",
    llm_config=llm_config_coder,
    system_message="You are the Video Coder. Your task is to edit the video according to the JSON cuts provided by the Content Analyst."
)

# 4. Inicialização do chat
admin.initiate_chat(manager, message="Por favor, baixe o vídeo [https://www.youtube.com/watch?v=jNQXAC9IVRw](https://www.youtube.com/watch?v=jNQXAC9IVRw). Em seguida, passe a transcrição para o Content_Analyst extrair os cortes em JSON. Por fim, mande o JSON para o Video_Coder editar. Não pare até os arquivos existirem.")
