import subprocess
import re
import os
import json

def get_silence_points(audio_path: str, silence_thresh: str = "-30dB", silence_dur: float = 0.6) -> list[float]:
    command = ["ffmpeg", "-i", audio_path, "-af", f"silencedetect=noise={silence_thresh}:d={silence_dur}", "-f", "null", "-"]
    result = subprocess.run(command, stderr=subprocess.PIPE, text=True)
    return [float(time) for time in re.findall(r"silence_end:\s*([0-9.]+)", result.stderr)]

def node_0_preventive_slicing(video_path: str, output_dir: str = "/app/output", max_chunk_sec: int = 600) -> list[dict]:
    full_audio_path = os.path.join(output_dir, "full_audio.wav")
    subprocess.run(["ffmpeg", "-y", "-i", video_path, "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", full_audio_path], check=True, stderr=subprocess.DEVNULL)

    silence_points = get_silence_points(full_audio_path)
    
    chunks = []
    last_cut = 0.0
    chunk_index = 0
    ultimo_silencio_valido = 0.0
    
    for silence_end in silence_points:
        if silence_end - last_cut > max_chunk_sec:
            if ultimo_silencio_valido <= last_cut:
                ultimo_silencio_valido = silence_end
                
            chunk_path = os.path.join(output_dir, f"audio_chunk_{chunk_index:03d}.wav")
            subprocess.run(["ffmpeg", "-y", "-i", full_audio_path, "-ss", str(last_cut), "-to", str(ultimo_silencio_valido), chunk_path], check=True, stderr=subprocess.DEVNULL)
            
            chunks.append({"chunk_path": chunk_path, "offset": last_cut})
            
            last_cut = ultimo_silencio_valido
            chunk_index += 1
            
        ultimo_silencio_valido = silence_end

    final_chunk_path = os.path.join(output_dir, f"audio_chunk_{chunk_index:03d}.wav")
    subprocess.run(["ffmpeg", "-y", "-i", full_audio_path, "-ss", str(last_cut), final_chunk_path], check=True, stderr=subprocess.DEVNULL)
    chunks.append({"chunk_path": final_chunk_path, "offset": last_cut})

    state_path = os.path.join(output_dir, "node0_state.json")
    with open(state_path, "w") as f:
        json.dump({"original_video_path": video_path, "chunks": chunks}, f, indent=2)

    os.remove(full_audio_path)
    return chunks
