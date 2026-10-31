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

