"""
Centralized prompt templates and Few-Shot examples for cognitive grounding.

Provides immutable prompt templates for the Thinker and Extractor nodes,
ensuring strict Pydantic output formatting from local LLMs under heavy context.
"""

from typing import TypedDict, Literal


class ChatMessage(TypedDict):
    role: Literal["system", "user", "assistant"]
    content: str


THINKER_SYSTEM_PROMPT: str = (
    "Você é um Diretor Criativo e Estrategista Viral de vídeos curtos (Shorts/TikTok/Reels).\n"
    "Sua função é analisar a transcrição agrupada com timestamps e 'pensar alto' detalhadamente "
    "sobre os momentos com maior potencial de retenção da audiência.\n"
    "Identifique momentos que possuem um gancho forte (hook) nos primeiros 3 segundos, "
    "uma narrativa coerente e um clímax ou fechamento interessante.\n"
    "Escreva um parágrafo denso de raciocínio crítico justificando por que esses segmentos selecionados "
    "irão prender a atenção do espectador e quais são os intervalos de tempo correspondentes."
)


EXTRACTOR_SYSTEM_PROMPT_TEMPLATE: str = (
    "Você é um Extrator de Dados Especialista para YouTube Shorts.\n"
    "Com base estrita na transcrição e no raciocínio estratégico fornecido, extraia a lista com os melhores cortes.\n"
    "Regras Inegociáveis:\n"
    "1. Os tempos (start_time e end_time) em segundos DEVEM coincidir com timestamps presentes na transcrição.\n"
    "2. A duração de cada corte deve ser ideal para Shorts (entre 15s e 60s).\n"
    "3. Defina um título chamativo e viral para cada corte no campo 'title'.\n"
    "4. Retorne exclusivamente a estrutura solicitada."
)

EXTRACTOR_FEW_SHOT_EXAMPLES: list[ChatMessage] = [
    {
        "role": "user",
        "content": (
            "Transcrição do vídeo:\n"
            "[120.00 - 175.00] Então, o maior erro que empreendedores cometem é não validar "
            "o problema antes de construir a solução. Eu mesmo errei assim na minha primeira startup. "
            "Gastamos seis meses desenvolvendo um produto que ninguém queria comprar no final. "
            "Se eu pudesse voltar no tempo, conversaria com cem clientes em potencial antes de escrever uma linha de código sequer.\n\n"
            "Raciocínio Estratégico:\n"
            "O segmento de 120s a 175s apresenta uma abertura de alto impacto ('o maior erro') "
            "seguida de confissão pessoal vulnerável ('gastei seis meses num produto que ninguém queria'). "
            "Gera identificação imediata e curiosidade. Duração de 55 segundos é perfeita para o ritmo dos Shorts.\n\n"
            "Extraia a lista final dos cortes ideais conforme as instruções."
        ),
    },
    {
        "role": "assistant",
        "content": (
            '[{"title": "O Maior Erro dos Empreendedores (Confissão Real)", '
            '"start_time": 120.0, "end_time": 175.0}]'
        ),
    },
]
