import subprocess
import re
import os
import json

def get_silence_points(audio_path: str, silence_thresh: str = "-30dB", silence_dur: float = 0.6) -> list[float]:
    command = [
        "ffmpeg",
        "-i", audio_path,
        "-af", f"silencedetect=noise={silence_thresh}:d={silence_dur}",
        "-f", "null",
        "-"
    ]
    result = subprocess.run(command, stderr=subprocess.PIPE, text=True)
    silence_end_times = re.findall(r"silence_end:\s*([0-9.]+)", result.stderr)
    return [float(time) for time in silence_end_times]

def node_0_preventive_slicing(video_path: str, output_dir: str = "/app/output", max_chunk_sec: int = 600) -> list[dict]:
    # Extract full audio from video
    full_audio_path = os.path.join(output_dir, "full_audio.wav")
    command = [
        "ffmpeg",
        "-i", video_path,
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", "16000",
        "-ac", "1",
        full_audio_path
    ]
    subprocess.run(command, check=True)

    # Get silence points
    silence_points = get_silence_points(full_audio_path)

    # Calculate chunk points
    chunks = []
    current_chunk_start = 0.0
    current_chunk_end = 0.0
    chunk_index = 0

    for silence_end in silence_points:
        if silence_end - current_chunk_start >= max_chunk_sec:
            chunks.append({
                "chunk_path": os.path.join(output_dir, f"audio_chunk_{chunk_index}.wav"),
                "offset": current_chunk_start
            })
            current_chunk_start = silence_end
            chunk_index += 1

    # Add the last chunk if there's any remaining audio
    if current_chunk_start < silence_points[-1]:
        chunks.append({
            "chunk_path": os.path.join(output_dir, f"audio_chunk_{chunk_index}.wav"),
            "offset": current_chunk_start
        })

    # Slice the audio into chunks
    for chunk in chunks:
        command = [
            "ffmpeg",
            "-i", full_audio_path,
            "-ss", str(chunk["offset"]),
            "-to", str(chunk["offset"] + max_chunk_sec) if chunk_index < len(chunks) - 1 else str(silence_points[-1]),
            "-c", "copy",
            chunk["chunk_path"]
        ]
        subprocess.run(command, check=True)

    # Save state
    state = {
        "original_video_path": video_path,
        "chunks": chunks
    }
    state_path = os.path.join(output_dir, "node0_state.json")
    with open(state_path, "w") as f:
        json.dump(state, f)

    # Clean up
    os.remove(full_audio_path)

    return chunks
