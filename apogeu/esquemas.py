from typing import Literal

from pydantic import BaseModel, Field

NomeAgente = Literal["pesquisador", "redator", "revisor"]
Destino = Literal["pesquisador", "redator", "revisor", "finalizar"]
TipoTexto = Literal["artigo", "post", "relatorio", "resumo"]


class Etapa(BaseModel):
    agente: NomeAgente = Field(description="Agente responsável pela etapa")
    objetivo: str = Field(description="O que o agente deve entregar nesta etapa")


class Plano(BaseModel):
    titulo: str = Field(description="Título provisório do texto final")
    abordagem: str = Field(description="Ângulo e estrutura escolhidos, em até três frases")
    perguntas: list[str] = Field(description="De três a seis perguntas que a pesquisa precisa responder")
    etapas: list[Etapa] = Field(description="Etapas em ordem, cada uma atribuída a um agente")


class Decisao(BaseModel):
    proximo: Destino = Field(description="Próximo agente a trabalhar, ou finalizar")
    instrucao: str = Field(description="Instrução objetiva para o próximo agente")
    motivo: str = Field(description="Por que esta é a melhor próxima etapa, em uma frase")


class Revisao(BaseModel):
    nota: float = Field(description="Nota de 0 a 10 para o rascunho")
    aprovado: bool = Field(description="Verdadeiro se o texto pode ser publicado como está")
    pontos_fortes: list[str] = Field(description="Até três pontos fortes")
    problemas: list[str] = Field(description="Problemas concretos encontrados, do mais grave ao menos grave")
    sugestoes: list[str] = Field(description="Ações objetivas para o redator corrigir os problemas")


class Briefing(BaseModel):
    tipo: TipoTexto = "artigo"
    publico: str = Field("público geral", min_length=2, max_length=120)
    tom: str = Field("claro e acessível", min_length=2, max_length=80)
    palavras: int = Field(700, ge=150, le=3000)
    idioma: str = Field("português do Brasil", min_length=2, max_length=40)


class NovaExecucao(BaseModel):
    tarefa: str = Field(min_length=10, max_length=2000)
    briefing: Briefing = Field(default_factory=Briefing)
    aprovar_plano: bool = False
    max_revisoes: int | None = Field(None, ge=0, le=5)


class AprovacaoPlano(BaseModel):
    aprovado: bool = True
    plano: Plano | None = None
    comentario: str = Field("", max_length=1000)


class AtualizacaoAgente(BaseModel):
    prompt_sistema: str | None = Field(None, min_length=20, max_length=8000)
    temperatura: float | None = Field(None, ge=0, le=1.5)
    modelo: str | None = Field(None, max_length=120)
    ferramentas: list[str] | None = None
    max_iteracoes: int | None = Field(None, ge=1, le=12)
