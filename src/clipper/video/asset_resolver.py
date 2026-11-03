"""Resolvedor semântico de assets e planos de execução de inserts de motion design."""
import json
import logging
import os
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

from clipper.core.schemas import (
    AssetItem,
    AssetManifest,
    AssetPosition,
    AssetType,
    Scene,
)
from clipper.runtime.config import PROJECT_ROOT

logger = logging.getLogger(__name__)


def normalize_text(text: str) -> str:
    """Normaliza texto removendo acentos, pontuações e convertendo para minúsculas."""
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = "".join(c for c in normalized if not unicodedata.combining(c))
    cleaned = "".join(c if c.isalnum() or c.isspace() else " " for c in ascii_text)
    return " ".join(cleaned.lower().split())


@dataclass
class EasingProfile:
    """Perfil de aceleração matemática para animação de inserts."""
    overshoot_factor: float = 1.70158
    pop_duration: float = 0.30
    fade_duration: float = 0.25
    float_amplitude: float = 4.0
    float_frequency: float = 0.8


@dataclass
class ResolvedInsert:
    """Plano de execução do insert vinculado a uma cena específica do corte."""
    scene_index: int
    start_time: float
    duration: float
    asset_path: Optional[str]
    asset_type: AssetType
    label_text: str
    target_width: int
    target_height: int
    center_x_ratio: float = 0.5
    center_y_ratio: float = 0.20
    sfx_path: Optional[str] = None
    easing: EasingProfile = field(default_factory=EasingProfile)


@dataclass
class AssetValidationResult:
    """Relatório técnico da validação de um asset individual."""
    file_path: str
    valid: bool
    asset_type: str
    has_alpha: bool
    dimensions: Optional[Tuple[int, int]] = None
    duration: Optional[float] = None
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class AssetResolver:
    """Carrega o manifest de assets e resolve mapeamentos semânticos para cenas."""

    def __init__(self, assets_dir: Optional[str] = None):
        self.assets_dir = (
            Path(assets_dir) if assets_dir else Path(PROJECT_ROOT) / "assets"
        )
        self.manifest_path = self.assets_dir / "manifest.json"
        self.manifest: Optional[AssetManifest] = None
        self._load_manifest()

    def _load_manifest(self) -> None:
        """Carrega e valida o arquivo manifest.json de forma resiliente."""
        if not self.manifest_path.exists():
            logger.warning("Manifest file not found at %s. Running in fallback mode.", self.manifest_path)
            self.manifest = None
            return

        try:
            content = self.manifest_path.read_text(encoding="utf-8")
            self.manifest = AssetManifest.model_validate_json(content)
            logger.info(
                "Loaded %d assets from %s", len(self.manifest.assets), self.manifest_path
            )
        except Exception as exc:
            logger.warning(
                "Failed to parse asset manifest at %s: %s. Using procedural fallback.",
                self.manifest_path,
                exc,
            )
            self.manifest = None

    def match_asset(self, metaphor: str) -> Optional[AssetItem]:
        """
        Localiza o melhor asset do catálogo compatível com o texto da metáfora.
        Retorna o AssetItem correspondente se o arquivo físico existir, ou None.
        """
        if not self.manifest or not self.manifest.assets:
            return None

        normalized_metaphor = normalize_text(metaphor)
        if not normalized_metaphor or normalized_metaphor == "-":
            return None

        tokens = set(normalized_metaphor.split())

        # 1ª Prioridade: Correspondência exata de token com tag
        for item in self.manifest.assets:
            normalized_tags = [normalize_text(t) for t in item.tags]
            for tag in normalized_tags:
                tag_tokens = set(tag.split())
                if tokens.intersection(tag_tokens) or tag in tokens or normalized_metaphor == tag:
                    full_path = self.assets_dir / item.file
                    if full_path.exists():
                        return item
                    else:
                        logger.warning(
                            "Asset file '%s' registered in manifest does not exist on disk.",
                            full_path,
                        )

        # 2ª Prioridade: Correspondência parcial/substring (para tags com mais de 3 caracteres)
        for item in self.manifest.assets:
            normalized_tags = [normalize_text(t) for t in item.tags]
            for tag in normalized_tags:
                if len(tag) >= 4 and any(
                    (tag in tok or tok in tag) for tok in tokens if len(tok) >= 4
                ):
                    full_path = self.assets_dir / item.file
                    if full_path.exists():
                        return item

        return None

    def resolve_insert_for_scene(
        self,
        scene: Scene,
        scene_index: int,
        scene_start_time: float,
        scene_duration: float,
        visual_identity: Optional[dict] = None,
    ) -> Optional[ResolvedInsert]:
        """
        Produz o ResolvedInsert planejado para uma determinada cena.
        Garante dimensões pares e posicionamento em zona segura (y <= 72%).
        """
        metaphor = getattr(scene, "visual_metaphor", "").strip()
        if not metaphor or metaphor == "-":
            return None

        # Cenas muito curtas não têm tempo suficiente para animação de insert
        if scene_duration < 0.6:
            return None

        matched_asset = self.match_asset(metaphor)

        if matched_asset:
            asset_path = str(self.assets_dir / matched_asset.file)
            asset_type = matched_asset.type
            max_dur = matched_asset.max_duration or 3.0
            duration = min(scene_duration, max_dur)

            # Posicionamento vertical
            if matched_asset.default_position == AssetPosition.MIDDLE_THIRD:
                center_y = 0.45
            elif matched_asset.default_position == AssetPosition.LOWER_THIRD:
                center_y = 0.65
            else:
                center_y = 0.20

            # Dimensões padrão pares
            if matched_asset.type == AssetType.ANIMATED_VIDEO:
                target_w, target_h = 360, 360
            else:
                target_w, target_h = 480, 140

            # SFX associado
            sfx_path = None
            if matched_asset.default_sfx:
                candidate_sfx = self.assets_dir / matched_asset.default_sfx
                if candidate_sfx.exists():
                    sfx_path = str(candidate_sfx)
        else:
            # Fallback procedural: Card Pill dinâmico com texto da metáfora
            asset_path = None
            asset_type = AssetType.ICON_WITH_CARD
            duration = min(scene_duration, 2.5)
            center_y = 0.20
            target_w, target_h = 480, 120
            sfx_path = None

        # Força dimensões estritamente pares para compatibilidade FFmpeg
        if target_w % 2 != 0:
            target_w -= 1
        if target_h % 2 != 0:
            target_h -= 1

        # Respeita o limite máximo vertical para nunca colidir com legendas (y >= 75%)
        if center_y > 0.70:
            center_y = 0.70

        return ResolvedInsert(
            scene_index=scene_index,
            start_time=scene_start_time,
            duration=duration,
            asset_path=asset_path,
            asset_type=asset_type,
            label_text=metaphor,
            target_width=target_w,
            target_height=target_h,
            center_x_ratio=0.5,
            center_y_ratio=center_y,
            sfx_path=sfx_path,
        )
