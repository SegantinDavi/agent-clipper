"""CPU-only audiovisual speaker selection and bounded portrait framing."""

from dataclasses import dataclass
import gc
import hashlib
import json
import logging
import math
from pathlib import Path
import subprocess

import numpy as np

from config import (
    SPEAKER_FOCUS_DETECTION_INTERVAL, SPEAKER_FOCUS_DETECTION_WIDTH,
    SPEAKER_FOCUS_DETECTION_THRESHOLD, SPEAKER_FOCUS_FACE_VERTICAL_POSITION,
    SPEAKER_FOCUS_FACE_HEIGHT_RATIO, SPEAKER_FOCUS_MAX_FACES, SPEAKER_FOCUS_MAX_ZOOM,
    SPEAKER_FOCUS_MODEL_DIR, SPEAKER_FOCUS_SCENE_THRESHOLD,
    SPEAKER_FOCUS_SWITCH_HOLD,
    SPEAKER_FOCUS_SWITCH_MARGIN, SPEAKER_FOCUS_THREADS, SPEAKER_FOCUS_THRESHOLD,
    SPEAKER_FOCUS_TRACK_GAP, SPEAKER_FOCUS_TRACK_IOU, SPEAKER_FOCUS_WINDOW_SECONDS,
)

logger = logging.getLogger(__name__)
ANALYSIS_FPS = 25


def intersection_over_union(first: list, second: list) -> float:
    left, top = max(first[0], second[0]), max(first[1], second[1])
    right = min(first[0] + first[2], second[0] + second[2])
    bottom = min(first[1] + first[3], second[1] + second[3])
    overlap = max(0, right - left) * max(0, bottom - top)
    union = first[2] * first[3] + second[2] * second[3] - overlap
    return overlap / union if union else 0.0


def portrait_size(frame_size: tuple) -> tuple[int, int]:
    width, height = frame_size
    height = max(2, int(min(height, width * 16 / 9)) // 2 * 2)
    width = max(2, int(min(width, height * 9 / 16)) // 2 * 2)
    return width, height


def face_crop(frame_size: tuple, face: list | None) -> list[float]:
    width, height = frame_size
    base_width, base_height = portrait_size(frame_size)
    if face is None:
        return [(width - base_width) / 2, (height - base_height) / 2, base_width, base_height]
    face_x, face_y, face_width, face_height = face
    crop_height = min(base_height, max(base_height / SPEAKER_FOCUS_MAX_ZOOM,
                                     face_height / SPEAKER_FOCUS_FACE_HEIGHT_RATIO,
                                     face_width * 1.15 * base_height / base_width))
    crop_width = crop_height * base_width / base_height
    center_x = face_x + face_width / 2
    center_y = face_y + face_height / 2 + (0.5 - SPEAKER_FOCUS_FACE_VERTICAL_POSITION) * crop_height
    return [float(np.clip(center_x - crop_width / 2, 0, width - crop_width)),
            float(np.clip(center_y - crop_height / 2, 0, height - crop_height)),
            crop_width, crop_height]


def lock_static_crops(frame_size: tuple, samples: list[dict]) -> list[dict]:
    start = 0
    previous_rectangle = face_crop(frame_size, None)
    for end in range(1, len(samples) + 1):
        if end < len(samples) and not samples[end]["reset"]:
            continue
        boxes = [sample["face_box"] for sample in samples[start:end] if sample["face_box"]]
        if boxes:
            left = min(box[0] for box in boxes)
            top = min(box[1] for box in boxes)
            right = max(box[0] + box[2] for box in boxes)
            bottom = max(box[1] + box[3] for box in boxes)
            rectangle = face_crop(frame_size, [left, top, right - left, bottom - top])
        else:
            rectangle = previous_rectangle
        for sample in samples[start:end]:
            sample["rect"] = list(rectangle)
        previous_rectangle = rectangle
        start = end
    return samples


class FaceTracker:
    def __init__(self):
        self.tracks = {}
        self.next_id = 0
        self.last_update_time = 0.0

    def update(self, boxes: list, time: float, scene_cut: bool = False) -> None:
        self.last_update_time = time
        if scene_cut:
            self.tracks.clear()
        self.tracks = {key: value for key, value in self.tracks.items()
                       if time - value["last_seen"] <= SPEAKER_FOCUS_TRACK_GAP}
        candidates = sorted(
            ((intersection_over_union(box, track["box"]), index, key)
             for index, box in enumerate(boxes) for key, track in self.tracks.items()),
            reverse=True,
        )
        assigned_boxes, assigned_tracks = set(), set()
        for overlap, index, key in candidates:
            if overlap < SPEAKER_FOCUS_TRACK_IOU or index in assigned_boxes or key in assigned_tracks:
                continue
            self.tracks[key] = {"box": boxes[index], "last_seen": time}
            assigned_boxes.add(index)
            assigned_tracks.add(key)
        for index, box in enumerate(boxes):
            if index not in assigned_boxes:
                self.tracks[self.next_id] = {"box": box, "last_seen": time}
                self.next_id += 1

    def visible(self, time: float) -> list[dict]:
        recent = sorted(self.tracks.items(), key=lambda item: item[1]["last_seen"], reverse=True)
        return [{"id": key, "box": track["box"]} for key, track in recent
                if track["last_seen"] == self.last_update_time
                and time - track["last_seen"] <= SPEAKER_FOCUS_TRACK_GAP][:SPEAKER_FOCUS_MAX_FACES]


class SpeakerSelector:
    def __init__(self):
        self.selected = None
        self.pending = None
        self.pending_since = 0.0

    def choose(self, faces: list[dict], time: float, scene_cut: bool = False) -> dict | None:
        if scene_cut:
            self.selected = self.pending = None
        if not faces:
            return None
        by_id = {face["id"]: face for face in faces}
        current = by_id.get(self.selected)
        confident = [face for face in faces
                     if face.get("score", float("-inf")) > SPEAKER_FOCUS_THRESHOLD]
        best = max(confident, key=lambda face: face["score"], default=None)
        if current is None:
            chosen = best or max(faces, key=lambda face: face["box"][2] * face["box"][3])
            self.selected = chosen["id"]
            self.pending = None
            return chosen
        if best is None or best["id"] == self.selected:
            self.pending = None
            return current
        if best["score"] <= current.get("score", float("-inf")) + SPEAKER_FOCUS_SWITCH_MARGIN:
            self.pending = None
            return current
        if self.pending != best["id"]:
            self.pending, self.pending_since = best["id"], time
        elif time - self.pending_since >= SPEAKER_FOCUS_SWITCH_HOLD:
            self.selected, self.pending = best["id"], None
            return best
        return current


@dataclass
class FramingPlan:
    frame_size: tuple
    samples: list[dict]

    def rectangle_at(self, time: float) -> list[float]:
        index = min(len(self.samples) - 1, max(0, int(time * ANALYSIS_FPS)))
        return self.samples[index]["rect"]


class SpeakerModels:
    def __init__(self):
        if not (0 < SPEAKER_FOCUS_FACE_HEIGHT_RATIO <= 1 and SPEAKER_FOCUS_MAX_ZOOM >= 1
                and 0 <= SPEAKER_FOCUS_FACE_VERTICAL_POSITION <= 1
                and 1 <= SPEAKER_FOCUS_MAX_FACES <= 8 and SPEAKER_FOCUS_THREADS >= 1
                and 1 <= SPEAKER_FOCUS_DETECTION_INTERVAL <= ANALYSIS_FPS
                and 0.2 <= SPEAKER_FOCUS_WINDOW_SECONDS <= 4):
            raise ValueError("Invalid SPEAKER_FOCUS configuration: check ratios, zoom, face count, threads and window limits.")
        try:
            import cv2
            import onnxruntime as ort
            import python_speech_features
        except ImportError as error:
            raise RuntimeError("Install speaker focus dependencies: pip install -r requirements.txt") from error
        self.cv2 = cv2
        self.mfcc = python_speech_features.mfcc
        directory = Path(SPEAKER_FOCUS_MODEL_DIR)
        manifest_path = directory / "manifest.json"
        if not manifest_path.is_file():
            raise RuntimeError("Speaker model assets are missing. Prepare them with tools/export_speaker_models.py.")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for name, expected in manifest["files"].items():
            path = directory / name
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                raise RuntimeError(f"Speaker model checksum mismatch: {name}. Restore the prepared assets.")
        cv2.setNumThreads(SPEAKER_FOCUS_THREADS)
        self.detector = cv2.FaceDetectorYN.create(
            str(directory / "face_detection_yunet.onnx"), "", (320, 320),
            SPEAKER_FOCUS_DETECTION_THRESHOLD, 0.3, 5000,
        )
        options = ort.SessionOptions()
        options.intra_op_num_threads = SPEAKER_FOCUS_THREADS
        options.inter_op_num_threads = 1
        self.session = ort.InferenceSession(
            str(directory / "light_asd.onnx"), options, providers=["CPUExecutionProvider"],
        )

    def detect(self, frame: np.ndarray) -> list[list[float]]:
        scale = min(1.0, SPEAKER_FOCUS_DETECTION_WIDTH / frame.shape[1])
        reduced = self.cv2.resize(frame, None, fx=scale, fy=scale)
        bgr = self.cv2.cvtColor(reduced, self.cv2.COLOR_RGB2BGR)
        self.detector.setInputSize((bgr.shape[1], bgr.shape[0]))
        _, faces = self.detector.detect(bgr)
        if faces is None:
            return []
        faces = sorted(faces, key=lambda face: face[2] * face[3], reverse=True)
        return [(face[:4] / scale).astype(float).tolist() for face in faces[:SPEAKER_FOCUS_MAX_FACES]]

    def face_patch(self, frame: np.ndarray, box: list) -> np.ndarray:
        x, y, width, height = box
        half_size = max(width, height) / 2
        center_x, center_y = x + width / 2, y + height / 2
        border = math.ceil(half_size * 2)
        padded = self.cv2.copyMakeBorder(frame, border, border, border, border,
                                         self.cv2.BORDER_CONSTANT, value=(110, 110, 110))
        left = int(center_x + border - half_size * 1.4)
        right = int(center_x + border + half_size * 1.4)
        top = int(center_y + border - half_size)
        bottom = int(center_y + border + half_size * 1.8)
        patch = padded[top:bottom, left:right]
        patch = self.cv2.cvtColor(patch, self.cv2.COLOR_RGB2GRAY)
        return self.cv2.resize(patch, (224, 224))[56:168, 56:168].copy()

    def scores(self, audio: np.ndarray, faces: list[np.ndarray]) -> np.ndarray:
        values = self.session.run(None, {
            "audio": np.asarray(audio[None], dtype=np.float32),
            "faces": np.asarray(faces, dtype=np.float32)[None],
        })[0].reshape(-1)
        return np.convolve(np.pad(values, (2, 2), mode="edge"), np.ones(5) / 5, mode="valid")


def read_audio_features(source: str, start: float, duration: float, models: SpeakerModels) -> np.ndarray:
    result = subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-ss", str(start), "-i", source,
         "-t", str(duration), "-vn", "-ac", "1", "-ar", "16000", "-f", "s16le", "pipe:1"],
        capture_output=True, check=False,
    )
    if result.returncode:
        raise RuntimeError(f"Speaker audio extraction failed: {result.stderr.decode(errors='replace')[-1000:]}")
    audio = np.frombuffer(result.stdout, dtype="<i2")
    if not len(audio):
        return np.zeros((math.ceil(duration * 100) + 4, 13), dtype=np.float32)
    return models.mfcc(audio, samplerate=16000, numcep=13, winlen=0.025, winstep=0.010)


def build_framing_plan(clip, source: str, source_start: float, timeline_path: str) -> FramingPlan:
    models = SpeakerModels()
    try:
        audio = read_audio_features(source, source_start, clip.duration, models)
        frame_count = max(1, math.ceil(clip.duration * ANALYSIS_FPS))
        if len(audio) < frame_count * 4:
            audio = np.pad(audio, ((0, frame_count * 4 - len(audio)), (0, 0)), mode="edge")
        tracker = FaceTracker()
        records = []
        previous_scene = None
        window_frames = max(1, round(SPEAKER_FOCUS_WINDOW_SECONDS * ANALYSIS_FPS))
        empty_patch = np.zeros((112, 112), dtype=np.uint8)
        logger.info("Analyzing visible speakers on CPU: %.2fs", clip.duration)
        for window_start in range(0, frame_count, window_frames):
            window_end = min(frame_count, window_start + window_frames)
            patches, visibility = {}, {}
            for index in range(window_start, window_end):
                time = index / ANALYSIS_FPS
                frame = clip.get_frame(min(time, max(0, clip.duration - 1 / clip.fps)))
                scene_cut = False
                if index % SPEAKER_FOCUS_DETECTION_INTERVAL == 0:
                    scene = models.cv2.resize(frame, (32, 18)).astype(np.float32) / 255
                    scene_cut = previous_scene is not None and float(
                        np.mean(np.abs(scene - previous_scene))
                    ) > SPEAKER_FOCUS_SCENE_THRESHOLD
                    previous_scene = scene
                    tracker.update(models.detect(frame), time, scene_cut)
                faces = tracker.visible(time)
                records.append({"faces": faces, "scene_cut": scene_cut})
                local_index = index - window_start
                visible = {face["id"]: face for face in faces}
                for face in faces:
                    if face["id"] not in patches:
                        patches[face["id"]] = [empty_patch] * local_index
                        visibility[face["id"]] = []
                for track_id, track_patches in patches.items():
                    face = visible.get(track_id)
                    track_patches.append(models.face_patch(frame, face["box"]) if face else empty_patch)
                    if face:
                        visibility[track_id].append(local_index)
            for track_id, track_patches in patches.items():
                valid = visibility[track_id]
                if len(valid) < 5:
                    continue
                first, last = valid[0], valid[-1] + 1
                audio_start, audio_end = (window_start + first) * 4, (window_start + last) * 4
                scores = models.scores(audio[audio_start:audio_end], track_patches[first:last])
                for local_index in valid:
                    for face in records[window_start + local_index]["faces"]:
                        if face["id"] == track_id:
                            face["score"] = float(scores[local_index - first])
            del patches, visibility

        selector = SpeakerSelector()
        samples = []
        previous_id = None
        fallback_frames = 0
        for index, record in enumerate(records):
            time = index / ANALYSIS_FPS
            chosen = selector.choose(record["faces"], time, record["scene_cut"])
            track_id = chosen["id"] if chosen else selector.selected
            reset = index == 0 or record["scene_cut"] or track_id != previous_id
            confident = chosen is not None and chosen.get("score", float("-inf")) > SPEAKER_FOCUS_THRESHOLD
            if not confident:
                fallback_frames += 1
            samples.append({"time": time, "track_id": track_id,
                            "reset": reset, "confident": confident,
                            "face_box": chosen["box"] if chosen else None,
                            "score": chosen.get("score") if chosen else None,
                            "scene_cut": record["scene_cut"]})
            previous_id = track_id
        samples = lock_static_crops(tuple(clip.size), samples)
        plan = FramingPlan(tuple(clip.size), samples)
        Path(timeline_path).write_text(json.dumps({
            "source": source, "source_start": source_start, "duration": clip.duration,
            "frame_size": list(clip.size), "output_size": list(portrait_size(clip.size)),
            "framing_mode": "static_per_speaker_turn",
            "fallback_frames": fallback_frames, "samples": samples,
        }), encoding="utf-8")
        logger.info("Speaker focus: %d frames, %d tracks; uncertain/offscreen %.1f%%",
                    frame_count, tracker.next_id, 100 * fallback_frames / frame_count)
        return plan
    finally:
        del models
        gc.collect()


def apply_framing_plan(clip, plan: FramingPlan):
    import cv2

    output_width, output_height = portrait_size(plan.frame_size)

    def transform(get_frame, time):
        frame = get_frame(time)
        x, y, width, height = plan.rectangle_at(time)
        width = max(2, min(frame.shape[1], int(width) // 2 * 2))
        height = max(2, min(frame.shape[0], int(height) // 2 * 2))
        x = max(0, min(round(x), frame.shape[1] - width))
        y = max(0, min(round(y), frame.shape[0] - height))
        return cv2.resize(frame[y:y + height, x:x + width], (output_width, output_height),
                          interpolation=cv2.INTER_LINEAR)

    return clip.fl(transform, apply_to=[])
