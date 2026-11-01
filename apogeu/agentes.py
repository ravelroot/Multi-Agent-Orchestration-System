from dataclasses import asdict, dataclass, field

from . import prompts
from .db import Repositorio


@dataclass
class Agente:
    chave: str
    nome: str
    papel: str
    cor: str
    prompt_sistema: str
    temperatura: float
    ferramentas: list[str]
    permitidas: list[str]
    max_iteracoes: int
    modelo: str = ""
    personalizado: bool = False
    padrao: dict = field(default_factory=dict, repr=False)

    def publico(self) -> dict:
        dados = asdict(self)
        dados.pop("padrao")
        return dados


PADROES: dict[str, dict] = {
    "supervisor": {
        "nome": "Supervisor",
        "papel": "Planeja a tarefa, decide quem trabalha a cada passo e encerra quando o texto está pronto.",
        "cor": "#15171C",
        "prompt_sistema": prompts.SUPERVISOR,
        "temperatura": 0.1,
        "ferramentas": [],
        "permitidas": [],
        "max_iteracoes": 1,
    },
    "pesquisador": {
        "nome": "Pesquisador",
        "papel": "Busca na web e na Wikipédia, lê páginas e devolve notas com fontes numeradas.",
        "cor": "#2E6A8E",
        "prompt_sistema": prompts.PESQUISADOR,
        "temperatura": 0.2,
        "ferramentas": ["buscar_web", "consultar_wikipedia", "ler_pagina", "calcular", "data_atual"],
        "permitidas": ["buscar_web", "consultar_wikipedia", "ler_pagina", "calcular", "data_atual"],
        "max_iteracoes": 6,
    },
    "redator": {
        "nome": "Redator",
        "papel": "Escreve o texto completo a partir das notas, citando as fontes, e reescreve após cada revisão.",
        "cor": "#8C5A2B",
        "prompt_sistema": prompts.REDATOR,
        "temperatura": 0.6,
        "ferramentas": [],
        "permitidas": [],
        "max_iteracoes": 1,
    },
    "revisor": {
        "nome": "Revisor",
        "papel": "Mede o rascunho, confere as citações e devolve nota, problemas e sugestões.",
        "cor": "#3D7650",
        "prompt_sistema": prompts.REVISOR,
        "temperatura": 0.1,
        "ferramentas": ["metricas_do_rascunho", "verificar_citacoes", "contar_palavras"],
        "permitidas": ["metricas_do_rascunho", "verificar_citacoes", "contar_palavras"],
        "max_iteracoes": 4,
    },
}

ORDEM = list(PADROES)


def garantir_padroes(repo: Repositorio) -> None:
    existentes = repo.agentes()
    for chave, padrao in PADROES.items():
        if chave not in existentes:
            repo.salvar_agente(
                chave,
                prompt_sistema=padrao["prompt_sistema"],
                temperatura=padrao["temperatura"],
                modelo="",
                ferramentas=list(padrao["ferramentas"]),
                max_iteracoes=padrao["max_iteracoes"],
            )


def carregar_agentes(repo: Repositorio) -> dict[str, Agente]:
    salvos = repo.agentes()
    agentes: dict[str, Agente] = {}
    for chave in ORDEM:
        padrao = PADROES[chave]
        salvo = salvos.get(chave)
        ferramentas = [f for f in (salvo.ferramentas if salvo else padrao["ferramentas"]) if f in padrao["permitidas"]]
        agente = Agente(
            chave=chave,
            nome=padrao["nome"],
            papel=padrao["papel"],
            cor=padrao["cor"],
            prompt_sistema=salvo.prompt_sistema if salvo else padrao["prompt_sistema"],
            temperatura=salvo.temperatura if salvo else padrao["temperatura"],
            ferramentas=ferramentas,
            permitidas=list(padrao["permitidas"]),
            max_iteracoes=salvo.max_iteracoes if salvo else padrao["max_iteracoes"],
            modelo=(salvo.modelo or "") if salvo else "",
            padrao=padrao,
        )
        agente.personalizado = (
            agente.prompt_sistema != padrao["prompt_sistema"]
            or agente.temperatura != padrao["temperatura"]
            or agente.ferramentas != padrao["ferramentas"]
            or agente.max_iteracoes != padrao["max_iteracoes"]
            or bool(agente.modelo)
        )
        agentes[chave] = agente
    return agentes


def restaurar_padrao(repo: Repositorio, chave: str) -> None:
    padrao = PADROES[chave]
    repo.salvar_agente(
        chave,
        prompt_sistema=padrao["prompt_sistema"],
        temperatura=padrao["temperatura"],
        modelo="",
        ferramentas=list(padrao["ferramentas"]),
        max_iteracoes=padrao["max_iteracoes"],
    )
