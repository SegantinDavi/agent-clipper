import os
import json
import re
from moviepy.editor import VideoFileClip
from moviepy.video.fx.all import crop

def cut_and_format_video(video_path: str, cuts_json: str, output_dir: str = "output") -> list:
    try:
        cuts = json.loads(cuts_json)
    except json.JSONDecodeError as e:
        print(f"Erro ao decodificar JSON: {e}")
        return []

    os.makedirs(output_dir, exist_ok=True)
    video = VideoFileClip(video_path)

    target_ratio = 9 / 16
    if video.w / video.h > target_ratio:
        new_width = int(video.h * target_ratio)
        x_center = video.w / 2
        video = crop(video, width=new_width, height=video.h, x_center=x_center)

    generated_files = []
    for corte in cuts:
        titulo_limpo = re.sub(r'[^\w\s]', '', corte['title']).replace(' ', '_')
        clip = video.subclip(corte["start_time"], corte["end_time"])
        filepath = os.path.join(output_dir, f"{titulo_limpo}.mp4")
        clip.write_videofile(filepath, codec="libx264", audio_codec="aac", logger=None)
        generated_files.append(filepath)

    video.close()
    return generated_files

if __name__ == "__main__":
    test_video_path = "downloads/jNQXAC9IVRw.mp4"
    test_cuts_json = '[{"title": "Test Cut 1", "start_time": 10, "end_time": 20}, {"title": "Test Cut 2", "start_time": 30, "end_time": 40}]'
    result = cut_and_format_video(test_video_path, test_cuts_json)
    print(f"Generated files: {result}")
