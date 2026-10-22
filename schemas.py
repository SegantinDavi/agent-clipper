from pydantic import BaseModel, Field

class CorteVideo(BaseModel):
    title: str = Field(description="O título curado do corte para viralização.")
    start_time: float = Field(description="O tempo de início do corte em segundos.")
    end_time: float = Field(description="O tempo de término do corte em segundos.")
