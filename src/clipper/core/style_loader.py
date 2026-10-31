import json
import logging
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationInfo, field_validator

from clipper.runtime.config import (
    CAPTION_CENTER_X_RATIO,
    CAPTION_CENTER_Y_RATIO,
    CAPTION_COLOR,
    CAPTION_FONT_SIZE,
    CAPTION_MAX_DURATION,
    CAPTION_MAX_GAP,
    CAPTION_MAX_WORDS,
    CAPTION_REFERENCE_WIDTH,
    CAPTION_SAFE_WIDTH_RATIO,
    CAPTION_STROKE_COLOR,
    CAPTION_STROKE_WIDTH,
    PROJECT_ROOT,
)

logger = logging.getLogger("clipper.core.style_loader")

_HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")

DEFAULT_VISUAL_IDENTITY: dict[str, Any] = {
    "caption_color": CAPTION_COLOR,
    "caption_stroke_color": CAPTION_STROKE_COLOR,
    "caption_font_size": CAPTION_FONT_SIZE,
    "caption_stroke_width": CAPTION_STROKE_WIDTH,
    "caption_reference_width": CAPTION_REFERENCE_WIDTH,
    "caption_center_x_ratio": CAPTION_CENTER_X_RATIO,
    "caption_center_y_ratio": CAPTION_CENTER_Y_RATIO,
    "caption_safe_width_ratio": CAPTION_SAFE_WIDTH_RATIO,
    "caption_max_words": CAPTION_MAX_WORDS,
    "caption_max_gap": CAPTION_MAX_GAP,
    "caption_max_duration": CAPTION_MAX_DURATION,
}


class VisualIdentityConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    # palette
    caption_color: str = CAPTION_COLOR
    caption_stroke_color: str = CAPTION_STROKE_COLOR

    # typography
    caption_font_size: int = CAPTION_FONT_SIZE
    caption_stroke_width: int = CAPTION_STROKE_WIDTH
    caption_reference_width: int = CAPTION_REFERENCE_WIDTH

    # layout
    caption_center_x_ratio: float = CAPTION_CENTER_X_RATIO
    caption_center_y_ratio: float = CAPTION_CENTER_Y_RATIO
    caption_safe_width_ratio: float = CAPTION_SAFE_WIDTH_RATIO

    # motion
    caption_max_words: int = CAPTION_MAX_WORDS
    caption_max_gap: float = CAPTION_MAX_GAP
    caption_max_duration: float = CAPTION_MAX_DURATION

    @field_validator("caption_color", "caption_stroke_color", mode="before")
    @classmethod
    def validate_hex_color(cls, v: Any, info: ValidationInfo) -> str:
        field_name = info.field_name or "caption_color"
        default = str(DEFAULT_VISUAL_IDENTITY.get(field_name, "#000000"))
        if not isinstance(v, str) or not _HEX_COLOR_RE.fullmatch(v):
            logger.warning(
                "style_node: Invalid hex color '%s' for field '%s'. Using default '%s'.",
                v,
                field_name,
                default,
            )
            return default
        return v

    @field_validator(
        "caption_font_size",
        "caption_stroke_width",
        "caption_reference_width",
        "caption_max_words",
        mode="before",
    )
    @classmethod
    def validate_positive_int(cls, v: Any, info: ValidationInfo) -> int:
        field_name = info.field_name or "int_field"
        default = int(DEFAULT_VISUAL_IDENTITY.get(field_name, 1))
        try:
            val = int(v)
            if val <= 0:
                raise ValueError("Must be positive")
            return val
        except (ValueError, TypeError):
            logger.warning(
                "style_node: Invalid positive integer '%s' for field '%s'. Using default '%s'.",
                v,
                field_name,
                default,
            )
            return default

    @field_validator(
        "caption_max_gap",
        "caption_max_duration",
        mode="before",
    )
    @classmethod
    def validate_positive_float(cls, v: Any, info: ValidationInfo) -> float:
        field_name = info.field_name or "float_field"
        default = float(DEFAULT_VISUAL_IDENTITY.get(field_name, 1.0))
        try:
            val = float(v)
            if val <= 0:
                raise ValueError("Must be positive")
            return val
        except (ValueError, TypeError):
            logger.warning(
                "style_node: Invalid positive number '%s' for field '%s'. Using default '%s'.",
                v,
                field_name,
                default,
            )
            return default

    @field_validator(
        "caption_center_x_ratio",
        "caption_center_y_ratio",
        "caption_safe_width_ratio",
        mode="before",
    )
    @classmethod
    def validate_ratio(cls, v: Any, info: ValidationInfo) -> float:
        field_name = info.field_name or "ratio_field"
        default = float(DEFAULT_VISUAL_IDENTITY.get(field_name, 0.5))
        try:
            val = float(v)
            if not (0.0 <= val <= 1.0):
                raise ValueError("Ratio must be between 0.0 and 1.0")
            return val
        except (ValueError, TypeError):
            logger.warning(
                "style_node: Invalid ratio '%s' for field '%s'. Using default '%s'.",
                v,
                field_name,
                default,
            )
            return default


def validate_visual_identity_primitives(
    identity: dict[str, Any],
) -> dict[str, str | int | float | bool]:
    """Ensures all values in visual_identity are JSON-primitive serializable.

    Only str, int, float, and bool are allowed. Non-primitive values are logged
    at WARNING level and replaced with defaults (or discarded if not a known key).
    """
    defaults = DEFAULT_VISUAL_IDENTITY
    cleaned: dict[str, str | int | float | bool] = {}

    for k, v in identity.items():
        if isinstance(v, (str, int, float, bool)):
            cleaned[k] = v
        else:
            logger.warning(
                "style_node: Non-primitive value '%s' of type %s for field '%s'. Reverting to default.",
                v,
                type(v).__name__,
                k,
            )
            if k in defaults:
                cleaned[k] = defaults[k]

    try:
        json.dumps(cleaned)
    except (TypeError, OverflowError) as exc:
        logger.warning(
            "style_node: Failed to serialize visual identity to JSON: %s. Using default visual identity.",
            exc,
        )
        return dict(defaults)

    return cleaned


def load_visual_identity(path: Path | str | None = None) -> dict[str, str | int | float | bool]:
    defaults = VisualIdentityConfig().model_dump()
    target_path = Path(path) if path is not None else PROJECT_ROOT / "estilo.json"

    if not target_path.exists():
        logger.warning(
            "style_node: Style file not found at '%s'. Using default visual identity.",
            target_path,
        )
        return defaults

    try:
        with open(target_path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning(
            "style_node: Failed to parse style file '%s': %s. Using default visual identity.",
            target_path,
            exc,
        )
        return defaults

    if not isinstance(raw_data, dict):
        logger.warning(
            "style_node: Style file root is not a dictionary: '%s'. Using default visual identity.",
            target_path,
        )
        return defaults

    flattened: dict[str, Any] = {}
    for k, v in raw_data.items():
        if isinstance(v, dict):
            for nested_k, nested_v in v.items():
                flattened[nested_k] = nested_v
        else:
            flattened[k] = v

    for k in defaults:
        if k not in flattened:
            logger.warning(
                "style_node: Missing field '%s' in style file. Using default '%s'.",
                k,
                defaults[k],
            )

    try:
        validated = VisualIdentityConfig.model_validate(flattened)
        result: dict[str, Any] = validated.model_dump()
    except Exception as exc:
        logger.warning(
            "style_node: Validation error for style file '%s': %s. Using default visual identity.",
            target_path,
            exc,
        )
        return defaults

    result = validate_visual_identity_primitives(result)

    logger.info("style_node: Loaded visual identity from '%s': %s", target_path, result)
    return result
