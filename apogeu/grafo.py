import asyncio
import re
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, TypedDict

from langchain_core.exceptions import OutputParserException
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from pydantic import ValidationError

from . import prompts
from .agentes import Agente
from .config import Configuracao
from .contexto import (
    RelatorioContexto,
    Secao,
    compactar_resultados_antigos,
    montar_contexto,
    texto_da_resposta,
    tokens_mensagens,
    tokens_texto,
    truncar,
)
from .esquemas import Decisao, Etapa, Plano, Revisao
from .ferramentas import ColetorFontes, Ferramentas, analisar_citacoes, analisar_texto
from .llm import Provedor, criar_modelo, estruturado

ROTAS = {"pesquisador": "pesquisar", "redator": "redigir", "revisor": "revisar", "finalizar": "finalizar"}
ERROS_DE_FORMATO = (OutputParserException, ValidationError, ValueError, KeyError, TypeError)


class EstadoEquipe(TypedDict, total=False):
    tarefa: str
    briefing: dict
    orientacao: str
    aprovar_plano: bool
    max_revisoes: int
    plano: dict
    recusado: bool
    notas: list[str]
    notas_compactas: str
    pesquisas: int
    fontes: list[dict]
    rascunho: str
    versao: int
    revisoes: list[dict]
    proximo: str
    instrucao: str
    passos: int
    historico: list[dict]
    resultado: str
    metricas: dict


@dataclass
class ContextoExecucao:
    cfg: Configuracao
    provedor: Provedor
    agentes: dict[str, Agente]
    emitir: Callable[..., Awaitable[None]]
    inicio: float = field(default_factory=time.monotonic)
    uso: dict[str, dict[str, int]] = field(default_factory=dict)

    def modelo(self, chave: str, papel: str | None = None) -> BaseChatModel:
        agente = self.agentes.get(chave)
        return criar_modelo(
            self.cfg,
            self.provedor,
            papel or chave,
            agente.modelo if agente else "",
            agente.temperatura if agente else None,
        )

    def contabilizar(self, chave: str, mensagens: list[BaseMessage], resposta: BaseMessage) -> None:
        uso = self.uso.setdefault(chave, {"chamadas": 0, "tokens_entrada": 0, "tokens_saida": 0})
        meta = getattr(resposta, "usage_metadata", None) or {}
        uso["chamadas"] += 1
        uso["tokens_entrada"] += int(meta.get("input_tokens") or tokens_mensagens(mensagens))
        uso["tokens_saida"] += int(meta.get("output_tokens") or tokens_texto(texto_da_resposta(resposta.content)))


def _ctx(config: RunnableConfig) -> ContextoExecucao:
    return config["configurable"]["contexto"]


def sistema(ctx: ContextoExecucao, chave: str, estado: EstadoEquipe) -> SystemMessage:
    idioma = (estado.get("briefing") or {}).get("idioma", "português do Brasil")
    return SystemMessage(content=f"{ctx.agentes[chave].prompt_sistema}\n\n{prompts.REGRAS_COMUNS.format(idioma=idioma)}")


def texto_briefing(briefing: dict) -> str:
    return "\n".join(
        [
            f"Tipo: {prompts.TIPOS.get(briefing.get('tipo', 'artigo'), 'artigo')}",
            f"Público: {briefing.get('publico', 'público geral')}",
            f"Tom: {briefing.get('tom', 'claro e acessível')}",
            f"Tamanho: cerca de {briefing.get('palavras', 700)} palavras",
            f"Idioma: {briefing.get('idioma', 'português do Brasil')}",
        ]
    )


def texto_plano(plano: dict) -> str:
    if not plano:
        return ""
    perguntas = "\n".join(f"- {p}" for p in plano.get("perguntas", []))
    return f"Título: {plano.get('titulo', '')}\nAbordagem: {plano.get('abordagem', '')}\nPerguntas:\n{perguntas}"


def texto_notas(estado: EstadoEquipe) -> str:
    partes = []
    if estado.get("notas_compactas"):
        partes.append(estado["notas_compactas"])
    partes.extend(estado.get("notas", []))
    return "\n\n".join(p for p in partes if p.strip())


def texto_fontes(fontes: list[dict]) -> str:
    return "\n".join(f"[{f['id']}] {f['titulo']} ({f['url']})" for f in fontes)


def texto_revisao(revisao: dict | None) -> str:
    if not revisao:
        return ""
    linhas = [f"Versão {revisao['versao']}: nota {revisao['nota']} ({'aprovada' if revisao['aprovado'] else 'reprovada'})"]
    if revisao.get("problemas"):
        linhas.append("Problemas:")
        linhas.extend(f"- {p}" for p in revisao["problemas"])
    if revisao.get("sugestoes"):
        linhas.append("Sugestões:")
        linhas.extend(f"- {s}" for s in revisao["sugestoes"])
    return "\n".join(linhas)


def contar_fatos(texto: str) -> int:
    return len([l for l in texto.splitlines() if re.search(r"\[\d+\]", l)])


def permitidos(estado: EstadoEquipe, cfg: Configuracao) -> tuple[set[str], str, str]:
    tem_notas = bool(texto_notas(estado).strip())
    versao = estado.get("versao", 0)
    revisoes = estado.get("revisoes", [])
    ultima = revisoes[-1] if revisoes else None
    revisada = ultima["versao"] if ultima else 0
    pesquisa_extra = estado.get("pesquisas", 0) < cfg.max_pesquisas
    reescritas = max(0, versao - 1)
    limite_revisoes = estado.get("max_revisoes", cfg.max_revisoes)
    if not tem_notas:
        return {"pesquisador"}, "pesquisador", "Sem notas de pesquisa, a equipe começa pelo pesquisador."
    if versao == 0:
        opcoes = {"redator"} | ({"pesquisador"} if pesquisa_extra else set())
        return opcoes, "redator", "Com as notas prontas, o próximo passo é escrever o rascunho."
    if revisada < versao:
        return {"revisor"}, "revisor", "Toda versão passa pelo revisor antes de seguir."
    if ultima and ultima["aprovado"]:
        return {"finalizar"}, "finalizar", "A revisão aprovou o texto."
    if reescritas >= limite_revisoes:
        return {"finalizar"}, "finalizar", "O limite de rodadas de revisão foi atingido; a melhor versão será publicada."
    opcoes = {"redator"} | ({"pesquisador"} if pesquisa_extra else set())
    return opcoes, "redator", "A última revisão pediu correções e ainda há rodadas disponíveis."


def instrucao_padrao(destino: str, estado: EstadoEquipe) -> str:
    if destino == "pesquisador":
        return "Pesquise as perguntas do plano e traga fatos verificáveis com as fontes numeradas."
    if destino == "redator":
        if estado.get("revisoes"):
            return "Reescreva o texto corrigindo cada problema da última revisão e mantendo o que estava bom."
        return "Escreva o texto completo seguindo o plano e o briefing, citando as fontes com [n]."
    if destino == "revisor":
        return f"Revise a versão {estado.get('versao', 1)}: briefing, citações, estrutura e legibilidade."
    return "Monte a versão final com as fontes citadas."


def texto_estado(estado: EstadoEquipe, cfg: Configuracao) -> str:
    revisoes = estado.get("revisoes", [])
    ultima = revisoes[-1] if revisoes else None
    opcoes, _, _ = permitidos(estado, cfg)
    linhas = [
        f"notas: {contar_fatos(texto_notas(estado))}",
        f"pesquisas_feitas: {estado.get('pesquisas', 0)} de {cfg.max_pesquisas}",
        f"fontes: {len(estado.get('fontes', []))}",
        f"versao_rascunho: {estado.get('versao', 0)}",
        f"versao_revisada: {ultima['versao'] if ultima else 0}",
        f"ultima_revisao: {('aprovada' if ultima['aprovado'] else 'reprovada') if ultima else 'nenhuma'}",
        f"nota_ultima_revisao: {ultima['nota'] if ultima else '-'}",
        f"rodadas_de_revisao_usadas: {max(0, estado.get('versao', 0) - 1)} de {estado.get('max_revisoes', cfg.max_revisoes)}",
        f"passo: {estado.get('passos', 0) + 1} de {cfg.max_passos}",
        f"opcoes_validas: {', '.join(sorted(opcoes))}",
    ]
    return "\n".join(linhas)


async def registrar_contexto(ctx: ContextoExecucao, chave: str, mensagens: list[BaseMessage], relatorio: RelatorioContexto | None = None) -> None:
    tokens = tokens_mensagens(mensagens)
    limite = ctx.cfg.limite_contexto
    await ctx.emitir(
        "contexto.uso",
        {
            "agente": chave,
            "tokens": tokens,
            "limite": limite,
            "percentual": round(tokens / limite * 100) if limite else 0,
            "secoes_cortadas": relatorio.secoes_cortadas if relatorio else [],
        },
    )
    if relatorio and relatorio.compactado:
        await ctx.emitir(
            "contexto.compactado",
            {
                "agente": chave,
                "antes": relatorio.tokens_antes,
                "depois": relatorio.tokens_depois,
                "motivo": "Seções reduzidas para caber no limite: " + ", ".join(relatorio.secoes_cortadas),
            },
        )


async def chamar_estruturado(ctx: ContextoExecucao, chave: str, mensagens: list[BaseMessage], esquema, reserva):
    runnable = estruturado(ctx.modelo(chave), esquema, ctx.provedor)
    ultimo_erro: Exception | None = None
    for _ in range(2):
        try:
            resultado = await runnable.ainvoke(mensagens)
            if isinstance(resultado, dict):
                resultado = esquema.model_validate(resultado)
            if resultado is None:
                raise ValueError("o modelo não devolveu a estrutura pedida")
            ctx.contabilizar(chave, mensagens, AIMessage(content=resultado.model_dump_json()))
            return resultado, False
        except ERROS_DE_FORMATO as erro:
            ultimo_erro = erro
            mensagens = [
                *mensagens,
                HumanMessage(content=f"A resposta anterior não seguiu o formato pedido ({str(erro)[:200]}). Responda de novo seguindo exatamente o esquema."),
            ]
    await ctx.emitir(
        "agente.aviso",
        {"agente": chave, "mensagem": f"A saída estruturada falhou duas vezes ({type(ultimo_erro).__name__}); a regra padrão foi usada."},
    )
    return reserva, True


async def executar_ferramenta(ctx: ContextoExecucao, chave: str, por_nome: dict[str, BaseTool], chamada: dict) -> ToolMessage:
    nome = chamada.get("name", "")
    argumentos = chamada.get("args") or {}
    identificador = chamada.get("id") or f"{nome}-{time.monotonic_ns()}"
    await ctx.emitir("ferramenta.chamada", {"agente": chave, "ferramenta": nome, "argumentos": argumentos, "chamada_id": identificador})
    inicio = time.monotonic()
    erro = False
    if nome not in por_nome:
        conteudo = f"A ferramenta {nome} não está disponível para este agente."
        erro = True
    else:
        try:
            conteudo = str(await asyncio.wait_for(por_nome[nome].ainvoke(argumentos), ctx.cfg.timeout_ferramentas + 5))
        except Exception as falha:
            conteudo = f"A ferramenta {nome} falhou: {type(falha).__name__}: {str(falha)[:240]}"
            erro = True
    conteudo = truncar(conteudo, ctx.cfg.limite_saida_ferramenta)
    await ctx.emitir(
        "ferramenta.resultado",
        {
            "agente": chave,
            "ferramenta": nome,
            "chamada_id": identificador,
            "resultado": truncar(conteudo, 1500),
            "duracao_ms": round((time.monotonic() - inicio) * 1000),
            "erro": erro,
        },
    )
    return ToolMessage(content=conteudo, tool_call_id=identificador, name=nome)


async def executar_com_ferramentas(
    ctx: ContextoExecucao,
    agente: Agente,
    mensagens: list[BaseMessage],
    ferramentas: list[BaseTool],
    relatorio: RelatorioContexto | None,
) -> tuple[str, list[BaseMessage]]:
    modelo = ctx.modelo(agente.chave)
    ligado = modelo.bind_tools(ferramentas) if ferramentas else modelo
    por_nome = {f.name: f for f in ferramentas}
    for iteracao in range(agente.max_iteracoes):
        mensagens, compactadas = compactar_resultados_antigos(mensagens, ctx.cfg.limite_contexto)
        if compactadas:
            await ctx.emitir(
                "contexto.compactado",
                {"agente": agente.chave, "motivo": f"{compactadas} resultado(s) antigo(s) de ferramenta resumido(s) para caber no contexto."},
            )
        await registrar_contexto(ctx, agente.chave, mensagens, relatorio if iteracao == 0 else None)
        resposta = await ligado.ainvoke(mensagens)
        ctx.contabilizar(agente.chave, mensagens, resposta)
        mensagens.append(resposta)
        chamadas = getattr(resposta, "tool_calls", None) or []
        if not chamadas:
            return texto_da_resposta(resposta.content).strip(), mensagens
        resultados = await asyncio.gather(*(executar_ferramenta(ctx, agente.chave, por_nome, c) for c in chamadas))
        mensagens.extend(resultados)
    mensagens.append(HumanMessage(content=prompts.CONCLUIR))
    await registrar_contexto(ctx, agente.chave, mensagens)
    resposta = await ligado.ainvoke(mensagens)
    ctx.contabilizar(agente.chave, mensagens, resposta)
    mensagens.append(resposta)
    return texto_da_resposta(resposta.content).strip(), mensagens


def normalizar_plano(plano: Plano, tarefa: str = "") -> Plano:
    perguntas = [p.strip() for p in plano.perguntas if p and p.strip()][:6]
    if not perguntas:
        perguntas = [f"Quais são os fatos essenciais sobre: {tarefa[:120]}?"]
    etapas = [e for e in plano.etapas if e.objetivo.strip()] or [
        Etapa(agente="pesquisador", objetivo="Reunir fatos com fontes."),
        Etapa(agente="redator", objetivo="Escrever o texto completo."),
        Etapa(agente="revisor", objetivo="Revisar e apontar correções."),
    ]
    return Plano(
        titulo=(plano.titulo.strip() or tarefa[:80] or "Texto sem título")[:200],
        abordagem=plano.abordagem.strip()[:600],
        perguntas=perguntas,
        etapas=etapas[:8],
    )


def plano_reserva(tarefa: str) -> Plano:
    return normalizar_plano(Plano(titulo=tarefa[:80], abordagem="Pesquisar, escrever e revisar.", perguntas=[], etapas=[]), tarefa)


async def planejar(estado: EstadoEquipe, config: RunnableConfig) -> dict[str, Any]:
    ctx = _ctx(config)
    inicio = time.monotonic()
    await ctx.emitir("agente.iniciou", {"agente": "supervisor", "instrucao": "Montar o plano da tarefa."})
    contexto, relatorio = montar_contexto(
        [
            Secao("tarefa", estado["tarefa"], 100, False),
            Secao("briefing", texto_briefing(estado.get("briefing", {})), 90, False),
            Secao("orientacao", estado.get("orientacao", ""), 95, False),
        ],
        ctx.cfg.limite_contexto,
    )
    mensagens = [sistema(ctx, "supervisor", estado), HumanMessage(content=prompts.PLANEJAR.format(contexto=contexto))]
    await registrar_contexto(ctx, "supervisor", mensagens, relatorio)
    plano, _ = await chamar_estruturado(ctx, "supervisor", mensagens, Plano, plano_reserva(estado["tarefa"]))
    plano = normalizar_plano(plano, estado["tarefa"])
    await ctx.emitir("plano.criado", {"plano": plano.model_dump()})
    await ctx.emitir(
        "agente.concluiu",
        {"agente": "supervisor", "resumo": f"Plano com {len(plano.perguntas)} perguntas e {len(plano.etapas)} etapas.", "duracao_ms": round((time.monotonic() - inicio) * 1000)},
    )
    return {
        "plano": plano.model_dump(),
        "passos": 0,
        "notas": [],
        "notas_compactas": "",
        "pesquisas": 0,
        "fontes": [],
        "rascunho": "",
        "versao": 0,
        "revisoes": [],
        "historico": [],
    }


async def aprovar(estado: EstadoEquipe, config: RunnableConfig) -> dict[str, Any]:
    if not estado.get("aprovar_plano"):
        return {}
    resposta = interrupt({"plano": estado["plano"]})
    ctx = _ctx(config)
    resposta = resposta or {}
    comentario = str(resposta.get("comentario") or "").strip()
    if not resposta.get("aprovado", True):
        return {"recusado": True, "orientacao": comentario}
    plano = normalizar_plano(Plano.model_validate(resposta.get("plano") or estado["plano"]), estado["tarefa"]).model_dump()
    await ctx.emitir("plano.aprovado", {"plano": plano, "comentario": comentario, "editado": plano != estado["plano"]})
    atualizacao: dict[str, Any] = {"plano": plano}
    if comentario:
        atualizacao["orientacao"] = "\n".join(p for p in [estado.get("orientacao", ""), comentario] if p)
    return atualizacao


async def supervisionar(estado: EstadoEquipe, config: RunnableConfig) -> dict[str, Any]:
    ctx = _ctx(config)
    passos = estado.get("passos", 0) + 1
    opcoes, canonico, regra = permitidos(estado, ctx.cfg)
    inicio = time.monotonic()
    if passos > ctx.cfg.max_passos:
        decisao = Decisao(proximo="finalizar", instrucao=instrucao_padrao("finalizar", estado), motivo="O limite de passos foi atingido.")
        ajustado, reserva = True, False
    else:
        await ctx.emitir("agente.iniciou", {"agente": "supervisor", "instrucao": "Decidir a próxima etapa."})
        ultima = (estado.get("revisoes") or [None])[-1]
        contexto, relatorio = montar_contexto(
            [
                Secao("tarefa", estado["tarefa"], 100, False),
                Secao("estado", texto_estado(estado, ctx.cfg), 99, False),
                Secao("plano", texto_plano(estado.get("plano", {})), 80),
                Secao("revisao", texto_revisao(ultima), 90),
                Secao("orientacao", estado.get("orientacao", ""), 95, False),
            ],
            ctx.cfg.limite_contexto,
        )
        mensagens = [sistema(ctx, "supervisor", estado), HumanMessage(content=prompts.DECIDIR.format(contexto=contexto))]
        await registrar_contexto(ctx, "supervisor", mensagens, relatorio)
        reserva_decisao = Decisao(proximo=canonico, instrucao=instrucao_padrao(canonico, estado), motivo=regra)
        decisao, reserva = await chamar_estruturado(ctx, "supervisor", mensagens, Decisao, reserva_decisao)
        ajustado = decisao.proximo not in opcoes
        if ajustado:
            decisao = Decisao(proximo=canonico, instrucao=instrucao_padrao(canonico, estado), motivo=regra)
    instrucao = decisao.instrucao.strip()[:800] or instrucao_padrao(decisao.proximo, estado)
    await ctx.emitir(
        "supervisor.decisao",
        {
            "proximo": decisao.proximo,
            "instrucao": instrucao,
            "motivo": decisao.motivo.strip()[:400],
            "ajustado": ajustado,
            "regra": regra if ajustado else None,
            "passo": passos,
        },
    )
    await ctx.emitir(
        "agente.concluiu",
        {"agente": "supervisor", "resumo": f"Próxima etapa: {decisao.proximo}.", "duracao_ms": round((time.monotonic() - inicio) * 1000)},
    )
    historico = [*estado.get("historico", []), {"passo": passos, "proximo": decisao.proximo, "motivo": decisao.motivo, "ajustado": ajustado}]
    return {"proximo": decisao.proximo, "instrucao": instrucao, "passos": passos, "historico": historico}


async def compactar_notas(ctx: ContextoExecucao, estado: EstadoEquipe, notas: str) -> str:
    limite_palavras = max(150, int(ctx.cfg.limite_notas * 0.45))
    mensagens = [
        SystemMessage(content=prompts.REGRAS_COMUNS.format(idioma=(estado.get("briefing") or {}).get("idioma", "português do Brasil"))),
        HumanMessage(content=prompts.COMPACTAR.format(limite=limite_palavras, notas=notas)),
    ]
    modelo = ctx.modelo("pesquisador", "compactador")
    resposta = await modelo.ainvoke(mensagens)
    ctx.contabilizar("pesquisador", mensagens, resposta)
    resumo = texto_da_resposta(resposta.content).strip()
    return resumo or truncar(notas, int(ctx.cfg.limite_notas * 4))


async def pesquisar(estado: EstadoEquipe, config: RunnableConfig) -> dict[str, Any]:
    ctx = _ctx(config)
    agente = ctx.agentes["pesquisador"]
    inicio = time.monotonic()
    await ctx.emitir("agente.iniciou", {"agente": "pesquisador", "instrucao": estado.get("instrucao", "")})
    coletor = ColetorFontes.de_lista(estado.get("fontes", []))
    ferramentas = Ferramentas(ctx.cfg, coletor, obter_briefing=lambda: estado.get("briefing", {})).selecionar(agente.ferramentas)
    ultima = (estado.get("revisoes") or [None])[-1]
    contexto, relatorio = montar_contexto(
        [
            Secao("tarefa", estado["tarefa"], 100, False),
            Secao("briefing", texto_briefing(estado.get("briefing", {})), 90, False),
            Secao("orientacao", estado.get("orientacao", ""), 95, False),
            Secao("plano", texto_plano(estado.get("plano", {})), 85),
            Secao("revisao", texto_revisao(ultima), 70),
            Secao("notas_existentes", texto_notas(estado), 40),
            Secao("fontes_conhecidas", texto_fontes(estado.get("fontes", [])), 30),
        ],
        ctx.cfg.limite_contexto,
    )
    mensagens: list[BaseMessage] = [
        sistema(ctx, "pesquisador", estado),
        HumanMessage(content=prompts.PESQUISAR.format(contexto=contexto, instrucao=estado.get("instrucao", ""))),
    ]
    saida, historico = await executar_com_ferramentas(ctx, agente, mensagens, ferramentas, relatorio)
    if not saida:
        brutos = [str(m.content) for m in historico if isinstance(m, ToolMessage)]
        saida = truncar("\n\n".join(brutos), ctx.cfg.limite_saida_ferramenta) or "Nenhuma informação encontrada."
    notas = [*estado.get("notas", []), saida]
    atualizacao: dict[str, Any] = {"notas": notas, "pesquisas": estado.get("pesquisas", 0) + 1, "fontes": coletor.lista()}
    completo = "\n\n".join(p for p in [estado.get("notas_compactas", ""), *notas] if p)
    if tokens_texto(completo) > ctx.cfg.limite_notas:
        antes = tokens_texto(completo)
        resumo = await compactar_notas(ctx, estado, completo)
        atualizacao["notas_compactas"] = resumo
        atualizacao["notas"] = []
        await ctx.emitir(
            "contexto.compactado",
            {"agente": "pesquisador", "antes": antes, "depois": tokens_texto(resumo), "motivo": "As notas passaram do limite e foram resumidas mantendo as citações."},
        )
        completo = resumo
    await ctx.emitir("notas.atualizadas", {"fatos": contar_fatos(completo), "tokens": tokens_texto(completo), "notas": truncar(completo, 6000)})
    await ctx.emitir("fontes.atualizadas", {"fontes": coletor.lista()})
    await ctx.emitir(
        "agente.concluiu",
        {
            "agente": "pesquisador",
            "resumo": f"{contar_fatos(saida)} fatos e {len(coletor.fontes)} fontes.",
            "duracao_ms": round((time.monotonic() - inicio) * 1000),
        },
    )
    return atualizacao


def limpar_rascunho(texto: str) -> str:
    texto = texto.strip()
    texto = re.sub(r"^```(?:markdown|md)?\s*\n", "", texto)
    texto = re.sub(r"\n```\s*$", "", texto)
    texto = re.split(r"\n#{1,3}\s*(?:Fontes|Referências|Referencias|Bibliografia)\s*\n", texto, maxsplit=1)[0]
    return texto.strip()


async def redigir(estado: EstadoEquipe, config: RunnableConfig) -> dict[str, Any]:
    ctx = _ctx(config)
    inicio = time.monotonic()
    versao = estado.get("versao", 0) + 1
    await ctx.emitir("agente.iniciou", {"agente": "redator", "instrucao": estado.get("instrucao", "")})
    ultima = (estado.get("revisoes") or [None])[-1]
    secoes = [
        Secao("tarefa", estado["tarefa"], 100, False),
        Secao("briefing", texto_briefing(estado.get("briefing", {})), 95, False),
        Secao("orientacao", estado.get("orientacao", ""), 95, False),
        Secao("plano", texto_plano(estado.get("plano", {})), 85),
        Secao("revisao", texto_revisao(ultima), 90),
        Secao("notas", texto_notas(estado), 70),
        Secao("fontes", texto_fontes(estado.get("fontes", [])), 60),
    ]
    if ultima and estado.get("rascunho"):
        secoes.append(Secao("rascunho_anterior", f"Versão {estado.get('versao', 0)}\n\n{estado['rascunho']}", 50))
    contexto, relatorio = montar_contexto(secoes, ctx.cfg.limite_contexto)
    mensagens = [
        sistema(ctx, "redator", estado),
        HumanMessage(content=prompts.REDIGIR.format(contexto=contexto, instrucao=estado.get("instrucao", ""))),
    ]
    await registrar_contexto(ctx, "redator", mensagens, relatorio)
    modelo = ctx.modelo("redator")
    partes: list[str] = []
    pendente = ""
    ultimo_envio = time.monotonic()
    meta: dict = {}
    async for pedaco in modelo.astream(mensagens):
        texto = texto_da_resposta(pedaco.content)
        if texto:
            partes.append(texto)
            pendente += texto
        if getattr(pedaco, "usage_metadata", None):
            meta = dict(pedaco.usage_metadata)
        if pendente and (time.monotonic() - ultimo_envio > 0.08 or len(pendente) > 160):
            await ctx.emitir("rascunho.delta", {"versao": versao, "texto": pendente}, persistir=False)
            pendente = ""
            ultimo_envio = time.monotonic()
    if pendente:
        await ctx.emitir("rascunho.delta", {"versao": versao, "texto": pendente}, persistir=False)
    rascunho = limpar_rascunho("".join(partes))
    if not rascunho:
        raise RuntimeError("O redator não devolveu nenhum texto.")
    ctx.contabilizar("redator", mensagens, AIMessage(content=rascunho, usage_metadata=meta or None))
    palavras = analisar_texto(rascunho)["palavras"]
    await ctx.emitir("rascunho.atualizado", {"versao": versao, "texto": rascunho, "palavras": palavras})
    await ctx.emitir(
        "agente.concluiu",
        {"agente": "redator", "resumo": f"Versão {versao} com {palavras} palavras.", "duracao_ms": round((time.monotonic() - inicio) * 1000)},
    )
    return {"rascunho": rascunho, "versao": versao}


def revisao_reserva(estado: EstadoEquipe, ids: set[int]) -> Revisao:
    rascunho = estado.get("rascunho", "")
    dados = analisar_texto(rascunho)
    citacoes = analisar_citacoes(rascunho, ids)
    alvo = int((estado.get("briefing") or {}).get("palavras", 700))
    problemas = []
    if citacoes["citacoes_invalidas"]:
        problemas.append(f"Citações para fontes inexistentes: {citacoes['citacoes_invalidas']}.")
    if abs(dados["palavras"] - alvo) > alvo * 0.35:
        problemas.append(f"O texto tem {dados['palavras']} palavras, longe das {alvo} pedidas.")
    if citacoes["paragrafos_sem_citacao"]:
        problemas.append("Há parágrafos longos sem nenhuma citação.")
    nota = max(4.0, 9.0 - 1.2 * len(problemas))
    return Revisao(
        nota=nota,
        aprovado=not problemas,
        pontos_fortes=["Rascunho completo e estruturado."],
        problemas=problemas,
        sugestoes=["Corrija os problemas listados mantendo a estrutura."] if problemas else [],
    )


async def revisar(estado: EstadoEquipe, config: RunnableConfig) -> dict[str, Any]:
    ctx = _ctx(config)
    agente = ctx.agentes["revisor"]
    inicio = time.monotonic()
    versao = estado.get("versao", 1)
    await ctx.emitir("agente.iniciou", {"agente": "revisor", "instrucao": estado.get("instrucao", "")})
    coletor = ColetorFontes.de_lista(estado.get("fontes", []))
    ferramentas = Ferramentas(
        ctx.cfg,
        coletor,
        obter_rascunho=lambda: estado.get("rascunho", ""),
        obter_briefing=lambda: estado.get("briefing", {}),
    ).selecionar(agente.ferramentas)
    anterior = (estado.get("revisoes") or [None])[-1]
    contexto, relatorio = montar_contexto(
        [
            Secao("tarefa", estado["tarefa"], 100, False),
            Secao("briefing", texto_briefing(estado.get("briefing", {})), 95, False),
            Secao("rascunho", f"Versão {versao}\n\n{estado.get('rascunho', '')}", 92),
            Secao("revisao_anterior", texto_revisao(anterior), 60),
            Secao("fontes", texto_fontes(estado.get("fontes", [])), 70),
            Secao("notas", texto_notas(estado), 40),
            Secao("plano", texto_plano(estado.get("plano", {})), 50),
        ],
        ctx.cfg.limite_contexto,
    )
    mensagens: list[BaseMessage] = [
        sistema(ctx, "revisor", estado),
        HumanMessage(content=prompts.REVISAR.format(contexto=contexto, instrucao=estado.get("instrucao", ""))),
    ]
    analise, _ = await executar_com_ferramentas(ctx, agente, mensagens, ferramentas, relatorio)
    curto, _ = montar_contexto(
        [
            Secao("briefing", texto_briefing(estado.get("briefing", {})), 95, False),
            Secao("rascunho", f"Versão {versao}\n\n{estado.get('rascunho', '')}", 90),
        ],
        ctx.cfg.limite_contexto // 2,
    )
    pedido = [
        sistema(ctx, "revisor", estado),
        HumanMessage(
            content=curto
            + "\n\n"
            + prompts.ESTRUTURAR_REVISAO.format(versao=versao, nota_minima=ctx.cfg.nota_minima, analise=truncar(analise, 6000))
        ),
    ]
    await registrar_contexto(ctx, "revisor", pedido)
    revisao, _ = await chamar_estruturado(ctx, "revisor", pedido, Revisao, revisao_reserva(estado, coletor.ids()))
    nota = round(max(0.0, min(10.0, float(revisao.nota))), 1)
    problemas = [p for p in revisao.problemas if p.strip()][:8]
    citacoes = analisar_citacoes(estado.get("rascunho", ""), coletor.ids())
    if citacoes["citacoes_invalidas"]:
        problemas.insert(0, f"Citações para fontes inexistentes: {citacoes['citacoes_invalidas']}.")
    aprovado = bool(revisao.aprovado) and nota >= ctx.cfg.nota_minima and not citacoes["citacoes_invalidas"]
    registro = {
        "versao": versao,
        "nota": nota,
        "aprovado": aprovado,
        "pontos_fortes": [p for p in revisao.pontos_fortes if p.strip()][:5],
        "problemas": problemas,
        "sugestoes": [s for s in revisao.sugestoes if s.strip()][:8],
    }
    await ctx.emitir("revisao.concluida", registro)
    await ctx.emitir(
        "agente.concluiu",
        {
            "agente": "revisor",
            "resumo": f"Nota {nota:.1f} na versão {versao}: {'aprovada' if aprovado else 'pediu correções'}.".replace(".", ",", 1),
            "duracao_ms": round((time.monotonic() - inicio) * 1000),
        },
    )
    return {"revisoes": [*estado.get("revisoes", []), registro]}


async def finalizar(estado: EstadoEquipe, config: RunnableConfig) -> dict[str, Any]:
    ctx = _ctx(config)
    inicio = time.monotonic()
    await ctx.emitir("agente.iniciou", {"agente": "supervisor", "instrucao": "Montar a versão final com as fontes."})
    texto = estado.get("rascunho", "").strip()
    fontes = estado.get("fontes", [])
    ids = {f["id"] for f in fontes}
    citadas = sorted({int(n) for n in re.findall(r"\[(\d+)\]", texto)} & ids)
    resultado = texto
    if citadas:
        mapa = {f["id"]: f for f in fontes}
        referencias = "\n".join(f"{n}. [{mapa[n]['titulo']}]({mapa[n]['url']})" for n in citadas)
        resultado = f"{texto}\n\n## Fontes\n\n{referencias}"
    revisoes = estado.get("revisoes", [])
    ultima = revisoes[-1] if revisoes else None
    tokens_entrada = sum(u["tokens_entrada"] for u in ctx.uso.values())
    tokens_saida = sum(u["tokens_saida"] for u in ctx.uso.values())
    metricas = {
        **analisar_texto(texto),
        "nota": ultima["nota"] if ultima else None,
        "aprovado": ultima["aprovado"] if ultima else False,
        "versoes": estado.get("versao", 0),
        "revisoes": len(revisoes),
        "pesquisas": estado.get("pesquisas", 0),
        "fontes_consultadas": len(fontes),
        "fontes_citadas": len(citadas),
        "passos": estado.get("passos", 0),
        "duracao_s": round(time.monotonic() - ctx.inicio, 1),
        "tokens_entrada": tokens_entrada,
        "tokens_saida": tokens_saida,
        "uso_por_agente": ctx.uso,
    }
    await ctx.emitir(
        "agente.concluiu",
        {"agente": "supervisor", "resumo": "Versão final pronta.", "duracao_ms": round((time.monotonic() - inicio) * 1000)},
    )
    return {"resultado": resultado, "metricas": metricas}


def construir_grafo(checkpointer=None):
    grafo = StateGraph(EstadoEquipe)
    grafo.add_node("planejar", planejar)
    grafo.add_node("aprovar", aprovar)
    grafo.add_node("supervisionar", supervisionar)
    grafo.add_node("pesquisar", pesquisar)
    grafo.add_node("redigir", redigir)
    grafo.add_node("revisar", revisar)
    grafo.add_node("finalizar", finalizar)
    grafo.add_edge(START, "planejar")
    grafo.add_edge("planejar", "aprovar")
    grafo.add_conditional_edges(
        "aprovar",
        lambda estado: "fim" if estado.get("recusado") else "supervisionar",
        {"fim": END, "supervisionar": "supervisionar"},
    )
    grafo.add_conditional_edges("supervisionar", lambda estado: ROTAS[estado["proximo"]], {v: v for v in ROTAS.values()})
    for no in ("pesquisar", "redigir", "revisar"):
        grafo.add_edge(no, "supervisionar")
    grafo.add_edge("finalizar", END)
    return grafo.compile(checkpointer=checkpointer)


def diagrama_mermaid() -> str:
    return construir_grafo().get_graph().draw_mermaid()
