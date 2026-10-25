"""Plan conservative audio/video edits in source-relative time."""

import logging
import math
import re
import subprocess

from pydantic import BaseModel, ConfigDict, Field, model_validator

from config import (
    SILENCE_CUT_ENABLED, SILENCE_KEEP_PAUSE, SILENCE_MIN_PAUSE,
    SILENCE_SPEECH_PADDING, SILENCE_THRESHOLD_DB,
)

logger = logging.getLogger(__name__)


class PauseSettings(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, frozen=True, validate_default=True)

    enabled: bool = SILENCE_CUT_ENABLED
    min_pause: float = Field(default=SILENCE_MIN_PAUSE, gt=0)
    keep_pause: float = Field(default=SILENCE_KEEP_PAUSE, gt=0)
    speech_padding: float = Field(default=SILENCE_SPEECH_PADDING, gt=0)
    threshold_db: float = Field(default=SILENCE_THRESHOLD_DB, lt=0)

    @model_validator(mode="after")
    def validate_spacing(self):
        if max(self.keep_pause, 2 * self.speech_padding) >= self.min_pause:
            raise ValueError("Retained pause and speech margins must be shorter than min_pause.")
        return self


class TimeInterval(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, frozen=True)

    start: float = Field(ge=0)
    end: float = Field(gt=0)

    @model_validator(mode="after")
    def validate_order(self):
        if self.end <= self.start:
            raise ValueError("Interval end must follow its start.")
        return self


class PausePlan(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, frozen=True)

    source_start: float = Field(ge=0)
    source_end: float = Field(gt=0)
    kept: list[TimeInterval] = Field(min_length=1)
    settings: PauseSettings

    @model_validator(mode="after")
    def validate_intervals(self):
        duration = self.source_end - self.source_start
        previous_end = 0.0
        if duration <= 0:
            raise ValueError("Invalid source cut.")
        for interval in self.kept:
            if interval.start < previous_end or interval.end > duration + 1e-6:
                raise ValueError("Kept intervals must be ordered within the source cut.")
            previous_end = interval.end
        if self.kept[0].start != 0 or abs(self.kept[-1].end - duration) > 1e-6:
            raise ValueError("Pause editing must preserve source cut edges.")
        if not self.settings.enabled and len(self.kept) != 1:
            raise ValueError("Disabled pause editing cannot remove intervals.")
        return self

    @property
    def duration(self) -> float:
        return sum(interval.end - interval.start for interval in self.kept)

    @property
    def removed_seconds(self) -> float:
        return self.source_end - self.source_start - self.duration

    def validate_cut(self, start: float, end: float) -> None:
        if abs(self.source_start - start) > 1e-6 or abs(self.source_end - end) > 1e-6:
            raise ValueError("Saved pause plan does not match the approved source cut.")


def identity_plan(start: float, end: float, settings: PauseSettings) -> PausePlan:
    return PausePlan(source_start=start, source_end=end, settings=settings,
                     kept=[TimeInterval(start=0, end=end - start)])


def speech_intervals(words: list[dict], start: float, end: float) -> list[TimeInterval]:
    intervals = []
    for word in words:
        try:
            left, right = float(word["start"]), float(word["end"])
            if not all(map(math.isfinite, (left, right))):
                raise ValueError("Invalid word timing")
            if max(left, right) <= start or min(left, right) >= end:
                continue
            if not str(word.get("word", "")).strip() or right <= left:
                raise ValueError("Invalid word timing")
        except (KeyError, TypeError, ValueError):
            logger.warning("Invalid word timestamps; preserving pauses in this cut.")
            return []
        left, right = max(start, left), min(end, right)
        if right > left:
            intervals.append((left - start, right - start))
    merged = []
    for left, right in sorted(intervals):
        if merged and left <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], right)
        else:
            merged.append([left, right])
    return [TimeInterval(start=left, end=right) for left, right in merged]


def parse_silences(stderr: str, duration: float) -> list[TimeInterval]:
    intervals = []
    start = None
    for match in re.finditer(r"silence_(start|end):\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)", stderr):
        time = max(0.0, min(duration, float(match.group(2))))
        if match.group(1) == "start":
            start = time
        elif start is not None:
            if time > start:
                intervals.append(TimeInterval(start=start, end=time))
            start = None
    if start is not None and start < duration:
        intervals.append(TimeInterval(start=start, end=duration))
    return intervals


def has_audio(video_path: str) -> bool:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries",
         "stream=index", "-of", "csv=p=0", video_path],
        capture_output=True, text=True, check=True,
    )
    return bool(result.stdout.strip())


def detect_silences(video_path: str, start: float, end: float,
                    settings: PauseSettings) -> list[TimeInterval]:
    if not has_audio(video_path):
        logger.info("No audio stream; preserving original cut timing.")
        return []
    result = subprocess.run(
        ["ffmpeg", "-nostdin", "-hide_banner", "-nostats", "-ss", str(start),
         "-threads", "2", "-i", video_path, "-t", str(end - start), "-map", "0:a:0", "-vn",
         "-af", f"silencedetect=noise={settings.threshold_db}dB:d={settings.min_pause}",
         "-f", "null", "-"],
        capture_output=True, text=True,
    )
    if result.returncode:
        raise RuntimeError(f"Silence detection failed: {result.stderr[-2000:]}")
    return parse_silences(result.stderr, end - start)


def plan_from_silences(start: float, end: float, speech: list[TimeInterval],
                       silences: list[TimeInterval], settings: PauseSettings) -> PausePlan:
    plan = identity_plan(start, end, settings)
    if not settings.enabled:
        return plan
    margin = max(settings.speech_padding, settings.keep_pause / 2)
    removed = []
    for previous, following in zip(speech, speech[1:]):
        if following.start - previous.end < settings.min_pause - 1e-6:
            continue
        for silence in silences:
            left = max(previous.end + margin, silence.start)
            right = min(following.start - margin, silence.end)
            if right > left + 1e-6:
                removed.append((left, right))
    kept = []
    cursor = 0.0
    for left, right in sorted(removed):
        if left > cursor:
            kept.append(TimeInterval(start=cursor, end=left))
        cursor = max(cursor, right)
    if cursor < end - start:
        kept.append(TimeInterval(start=cursor, end=end - start))
    return PausePlan(source_start=start, source_end=end, settings=settings, kept=kept)


def build_pause_plan(video_path: str, start: float, end: float,
                     words: list[dict], settings: PauseSettings) -> PausePlan:
    plan = identity_plan(start, end, settings)
    speech = speech_intervals(words, start, end) if settings.enabled else []
    if not settings.enabled or len(speech) < 2:
        logger.info("Pause detection skipped: disabled or insufficient reliable word timestamps.")
    elif any(right.start - left.end >= settings.min_pause - 1e-6
             for left, right in zip(speech, speech[1:])):
        plan = plan_from_silences(start, end, speech,
                                 detect_silences(video_path, start, end, settings), settings)
    logger.info("Pause edits: %.3fs -> %.3fs; removed %.3fs in %d cuts",
                end - start, plan.duration, plan.removed_seconds, len(plan.kept) - 1)
    return plan


def remap_word_groups(words: list[dict], plan: PausePlan) -> list[list[dict]]:
    groups = []
    offset = 0.0
    for interval in plan.kept:
        group = []
        for word in words:
            try:
                start, end = float(word["start"]), float(word["end"])
                text = str(word["word"])
                if not all(map(math.isfinite, (start, end))):
                    continue
            except (KeyError, TypeError, ValueError):
                continue
            left = max(start - plan.source_start, interval.start)
            right = min(end - plan.source_start, interval.end)
            if right > left:
                group.append({"word": text,
                              "start": offset + left - interval.start,
                              "end": offset + right - interval.start})
        groups.append(sorted(group, key=lambda word: word["start"]))
        offset += interval.end - interval.start
    return groups


def preview_filter(plan: PausePlan) -> str:
    filters = []
    inputs = []
    selections = []
    shifts = []
    previous_end = 0.0
    for index, interval in enumerate(plan.kept):
        span = f"start={interval.start:.9f}:end={interval.end:.9f}"
        filters.append(f"[0:a:0]atrim={span},asetpts=PTS-STARTPTS[a{index}]")
        inputs.append(f"[a{index}]")
        selections.append(f"gte(t,{interval.start:.9f})*lt(t,{interval.end:.9f})")
        if index:
            shifts.append(f"gte(T,{interval.start:.9f})*{interval.start - previous_end:.9f}")
        previous_end = interval.end
    filters.append("".join(inputs) + f"concat=n={len(inputs)}:v=0:a=1[a]")
    # One video branch avoids buffering decoded full-resolution segments for concat.
    filters.append(f"[0:v:0]select='{'+'.join(selections)}',"
                   f"setpts='PTS-({'+'.join(shifts) or '0'})/TB',"
                   "scale=w='min(640,iw)':h=-2:force_divisible_by=2[outv]")
    return ";".join(filters)
