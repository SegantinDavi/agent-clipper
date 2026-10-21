import requests
import json
from autogen import UserProxyAgent, AssistantAgent, GroupChat, GroupChatManager, agentchat
from ingestion import download_video_and_transcript
from editor import cut_and_format_video

# 1. Configuração de LLM
llm_config_manager = {
    "base_url": "http://127.0.0.1:11434/v1",
    "api_key": "ollama",
    "model": "qwen2.5:14b",
    "max_tokens": 1500,
    "timeout": 300
}

# 2. Definição dos Agentes (Apenas 2 necessários)
admin = UserProxyAgent(
    name="Admin",
    human_input_mode="NEVER",
    code_execution_config={"work_dir": ".", "use_docker": False},
    is_termination_msg=lambda x: "TERMINATE" in x.get("content", "").upper()
)

content_analyst = AssistantAgent(
    name="Content_Analyst",
    llm_config=llm_config_manager,
    system_message=(
        "Você é um Analista Especialista para YouTube Shorts. Sua tarefa é analisar transcrições com timestamps e escolher os 3 melhores cortes.\n"
        "Regras:\n"
        "1. SÓ PODE usar timestamps (start_time e end_time) que existam no texto.\n"
        "2. Retorne APENAS o bloco JSON válido e termine sua mensagem com a palavra TERMINATE.\n"
        "Formato Obrigatório:\n"
        "```json\n"
        "[\n"
        "  {\"title\": \"Titulo1\", \"start_time\": 0.0, \"end_time\": 5.0},\n"
        "  {\"title\": \"Titulo2\", \"start_time\": 10.0, \"end_time\": 15.0}\n"
        "]\n"
        "```\nTERMINATE"
    )
)

if __name__ == "__main__":
    print("[1] Iniciando o Download e Transcrição...")
    url = "https://www.youtube.com/watch?v=jNQXAC9IVRw"
    
    # Execução Manual da Ferramenta 1 (Evita alucinações de argumentos)
    ingestion_result = download_video_and_transcript(url)
    
    if ingestion_result["status"] == "error":
        print(f"Erro na Ingestão: {ingestion_result['message']}")
        exit(1)
        
    print("[2] Vídeo baixado. Iniciando a Análise via IA...")
    
    # Conversa focada apenas em extrair o JSON
    chat_result = admin.initiate_chat(
        content_analyst,
        message=f"Aqui está a transcrição do vídeo:\n\n{ingestion_result['transcript']}\n\nExtraia os 3 melhores cortes e retorne o JSON."
    )
    
    # Extração do JSON da resposta
    final_message = admin.last_message(content_analyst)["content"]
    
    print("[3] Análise concluída. Iniciando os Cortes (MoviePy)...")
    
    # Extract word_timestamps
    word_timestamps = ingestion_result["word_timestamps"]
    
    # Execução Manual da Ferramenta 2 com o texto gerado
    generated_files = cut_and_format_video(
        video_path=ingestion_result["video_path"],
        cuts_json=final_message,
        word_timestamps=word_timestamps,
        output_dir="output"
    )
    
    if generated_files:
        print("\n🎉 SUCESSO! Vídeos gerados:")
        for file in generated_files:
            print(f"- {file}")
    else:
        print("\nFalha ao gerar os vídeos. O JSON gerado pode estar incorreto.")
