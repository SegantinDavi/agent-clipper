import json
import openai
import instructor
from schemas import CorteVideo
from ingestion import download_video_and_transcript
from editor import cut_and_format_video

# Configure the OpenAI client with Ollama
client = openai.OpenAI(
    base_url="http://127.0.0.1:11434/v1",
    api_key="ollama"
)
client = instructor.from_openai(client, mode=instructor.Mode.JSON)

def main():
    print("[1] Iniciando o Download e Transcrição...")
    url = "https://www.youtube.com/watch?v=jNQXAC9IVRw"
    
    # Execução Manual da Ferramenta 1 (Evita alucinações de argumentos)
    ingestion_result = download_video_and_transcript(url)
    
    if ingestion_result["status"] == "error":
        print(f"Erro na Ingestão: {ingestion_result['message']}")
        exit(1)
        
    print("[2] Vídeo baixado. Iniciando a Análise via IA...")
    
    # Create the system and user prompts
    system_prompt = (
        "Você é um Analista Especialista para YouTube Shorts. Sua tarefa é analisar transcrições com timestamps e escolher os 3 melhores cortes.\n"
        "Regras:\n"
        "1. SÓ PODE usar timestamps (start_time e end_time) que existam no texto.\n"
        "2. Retorne APENAS a lista de cortes no formato JSON."
    )
    user_prompt = f"Aqui está a transcrição do vídeo:\n\n{ingestion_result['transcript']}\n\nExtraia os 3 melhores cortes e retorne o JSON."

    # Call the OpenAI client to get the response
    response = client.chat.completions.create(
        model="qwen2.5:14b",
        response_model=list[CorteVideo],
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
    )

    # Extract the list of CorteVideo instances from the response
    cortes_extraidos = response

    # Serialize the list of CorteVideo instances to a JSON string
    cuts_json = json.dumps([corte.model_dump() for corte in cortes_extraidos])

    print("[3] Análise concluída. Iniciando os Cortes (MoviePy)...")
    
    # Extract word_timestamps
    word_timestamps = ingestion_result["word_timestamps"]
    
    # Execução Manual da Ferramenta 2 com o texto gerado
    generated_files = cut_and_format_video(
        video_path=ingestion_result["video_path"],
        cuts_json=cuts_json,
        word_timestamps=word_timestamps,
        output_dir="output"
    )
    
    if generated_files:
        print("\n🎉 SUCESSO! Vídeos gerados:")
        for file in generated_files:
            print(f"- {file}")
    else:
        print("\nFalha ao gerar os vídeos. O JSON gerado pode estar incorreto.")

if __name__ == "__main__":
    main()
