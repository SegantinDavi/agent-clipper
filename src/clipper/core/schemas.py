from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class Scene(BaseModel):
    start_word: str = Field(
        min_length=1,
        description="Palavra exata de início do segmento da cena na transcrição.",
    )
    end_word: str = Field(
        min_length=1,
        description="Palavra exata de término do segmento da cena na transcrição.",
    )
    visual_metaphor: str = Field(
        min_length=1,
        description="Metáfora visual, imagem conceitual ou representação gráfica de apoio.",
    )
    animation_trigger: str = Field(
        min_length=1,
        description="Gatilho de animação, corte ou movimento de câmera recomendado (ex: zoom_in, impact, cut_transition).",
    )


class CorteVideo(BaseModel):
    title: str = Field(description="O título curado do corte para viralização.")
    description: str = Field(
        default="", description="Resumo factual do tema do corte em uma ou duas frases."
    )
    start_time: float = Field(description="O tempo de início do corte em segundos.")
    end_time: float = Field(description="O tempo de término do corte em segundos.")
    scenes: list[Scene] = Field(
        default_factory=list,
        json_schema_extra={"minItems": 1},
        description="Lista ordenada de cenas lógicas de 2 a 4 segundos com metáforas e gatilhos de animação.",
    )


class CortesResponse(BaseModel):
    cortes: list[CorteVideo] = Field(
        description="Lista contendo os melhores cortes selecionados para Shorts.",
        min_length=0,
    )


class RenderScriptPayload(BaseModel):
    script_code: str = Field(
        min_length=1,
        description="Código Python completo e auto-contido para renderização do corte vertical usando MoviePy 1.0.3 e Pillow.",
    )


class AssetType(str, Enum):
    ANIMATED_VIDEO = "animated_video"
    ICON_WITH_CARD = "icon_with_card"
    SFX = "sfx"


class AssetPosition(str, Enum):
    UPPER_THIRD = "upper_third"
    MIDDLE_THIRD = "middle_third"
    LOWER_THIRD = "lower_third"


class AssetItem(BaseModel):
    """Representa um elemento catalogado no manifest de assets."""
    id: str = Field(..., min_length=1, description="Identificador único (ex: 'chart_growth')")
    file: str = Field(..., min_length=1, description="Caminho relativo a partir de /assets")
    type: AssetType = Field(..., description="Tipo do elemento (animated_video, icon_with_card, sfx)")
    tags: List[str] = Field(default_factory=list, description="Lista de palavras-chave normalizadas para match com metáforas")
    default_position: AssetPosition = Field(default=AssetPosition.UPPER_THIRD, description="Posicionamento vertical seguro recomendado")
    default_sfx: Optional[str] = Field(default=None, description="Caminho relativo do SFX padrão associado (opcional)")
    max_duration: Optional[float] = Field(default=3.0, description="Duração máxima de exibição do insert em segundos")


class AssetManifest(BaseModel):
    """Estrutura raiz do arquivo assets/manifest.json."""
    version: str = Field(default="1.0.0", description="Versão do schema do catálogo")
    assets: List[AssetItem] = Field(default_factory=list, description="Lista de assets disponíveis")



