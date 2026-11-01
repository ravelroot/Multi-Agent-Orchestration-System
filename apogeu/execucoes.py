import asyncio
import json
import logging
import uuid
from collections import defaultdict
from typing import Any, AsyncIterator

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from .agentes import carregar_agentes
from .config import Configuracao
from .db import STATUS_FINAIS, Repositorio
from .esquemas import AprovacaoPlano, NovaExecucao
from .grafo import ContextoExecucao, construir_grafo
from .llm import Provedor

log = logging.getLogger("apogeu")

EVENTOS_FINAIS = {"execucao.concluida", "execucao.cancelada", "execucao.erro", "plano.recusado", "plano.aguardando"}


class ExecucaoNaoEncontrada(Exception):
    pass


class EstadoInvalido(Exception):
    pass


def titulo_da_tarefa(tarefa: str) -> str:
    linha = " ".join(tarefa.split())
    return linha if len(linha) <= 90 else linha[:87].rstrip() + "..."


class ServicoExecucoes:
    def __init__(self, repo: Repositorio, cfg: Configuracao, provedor: Provedor):
        self.repo = repo
        self.cfg = cfg
        self.provedor = provedor
        self.grafo = construir_grafo(InMemorySaver())
        self.tarefas: dict[str, asyncio.Task] = {}
        self.contextos: dict[str, ContextoExecucao] = {}
        self.assinantes: dict[str, set[asyncio.Queue]] = defaultdict(set)
        self.sequencias: dict[str, int] = {}
        self.travas: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self.semaforo = asyncio.Semaphore(max(1, cfg.max_execucoes))

    def _config(self, execucao_id: str) -> dict[str, Any]:
        return {
            "configurable": {"thread_id": execucao_id, "contexto": self.contextos[execucao_id]},
            "recursion_limit": self.cfg.max_passos * 2 + 12,
        }

    async def emitir(self, execucao_id: str, tipo: str, dados: dict, persistir: bool = True) -> None:
        evento: dict[str, Any] = {"tipo": tipo, "dados": dados, "seq": None}
        if persistir:
            async with self.travas[execucao_id]:
                seq = self.sequencias.get(execucao_id)
                if seq is None:
                    seq = await asyncio.to_thread(self.repo.ultimo_seq, execucao_id)
                seq += 1
                self.sequencias[execucao_id] = seq
                registro = await asyncio.to_thread(self.repo.registrar_evento, execucao_id, seq, tipo, dados)
            evento = registro.como_dict()
        for fila in list(self.assinantes.get(execucao_id, ())):
            fila.put_nowait(evento)

    def _contexto(self, execucao_id: str) -> ContextoExecucao:
        async def emitir(tipo: str, dados: dict, persistir: bool = True) -> None:
            await self.emitir(execucao_id, tipo, dados, persistir)

        return ContextoExecucao(cfg=self.cfg, provedor=self.provedor, agentes=carregar_agentes(self.repo), emitir=emitir)

    async def criar(self, pedido: NovaExecucao) -> dict:
        execucao_id = str(uuid.uuid4())
        max_revisoes = self.cfg.max_revisoes if pedido.max_revisoes is None else pedido.max_revisoes
        execucao = await asyncio.to_thread(
            self.repo.criar_execucao,
            id=execucao_id,
            titulo=titulo_da_tarefa(pedido.tarefa),
            tarefa=pedido.tarefa.strip(),
            briefing=pedido.briefing.model_dump(),
            opcoes={"aprovar_plano": pedido.aprovar_plano, "max_revisoes": max_revisoes},
            status="na_fila",
            provedor=self.provedor.nome,
            modelo=self.provedor.modelo,
        )
        self.contextos[execucao_id] = self._contexto(execucao_id)
        await self.emitir(
            execucao_id,
            "execucao.criada",
            {"tarefa": execucao.tarefa, "briefing": execucao.briefing, "opcoes": execucao.opcoes, "provedor": self.provedor.como_dict()},
        )
        entrada = {
            "tarefa": execucao.tarefa,
            "briefing": execucao.briefing,
            "aprovar_plano": pedido.aprovar_plano,
            "max_revisoes": max_revisoes,
            "orientacao": "",
        }
        self._iniciar(execucao_id, entrada)
        return execucao.detalhe()

    def _iniciar(self, execucao_id: str, entrada: Any) -> None:
        tarefa = asyncio.create_task(self._rodar(execucao_id, entrada), name=f"execucao-{execucao_id}")
        self.tarefas[execucao_id] = tarefa
        tarefa.add_done_callback(lambda _: self.tarefas.pop(execucao_id, None))

    async def _rodar(self, execucao_id: str, entrada: Any) -> None:
        config = self._config(execucao_id)
        try:
            async with self.semaforo:
                await asyncio.to_thread(self.repo.atualizar_execucao, execucao_id, status="em_andamento")
                await self.emitir(execucao_id, "execucao.iniciada", {"provedor": self.provedor.como_dict()})
                async for _ in self.grafo.astream(entrada, config, stream_mode="updates"):
                    pass
                estado = await self.grafo.aget_state(config)
                valores = estado.values
                if estado.next:
                    plano = valores.get("plano", {})
                    await asyncio.to_thread(self.repo.atualizar_execucao, execucao_id, status="aguardando_aprovacao", plano=plano)
                    await self.emitir(execucao_id, "plano.aguardando", {"plano": plano})
                    return
                if valores.get("recusado"):
                    await asyncio.to_thread(self.repo.atualizar_execucao, execucao_id, status="recusada", plano=valores.get("plano", {}))
                    await self.emitir(execucao_id, "plano.recusado", {"comentario": valores.get("orientacao", "")})
                    self._limpar(execucao_id)
                    return
                await asyncio.to_thread(
                    self.repo.atualizar_execucao,
                    execucao_id,
                    status="concluida",
                    plano=valores.get("plano", {}),
                    resultado=valores.get("resultado", ""),
                    fontes=valores.get("fontes", []),
                    metricas=valores.get("metricas", {}),
                )
                await self.emitir(
                    execucao_id,
                    "execucao.concluida",
                    {"resultado": valores.get("resultado", ""), "metricas": valores.get("metricas", {}), "fontes": valores.get("fontes", [])},
                )
                self._limpar(execucao_id)
        except asyncio.CancelledError:
            await asyncio.to_thread(self.repo.atualizar_execucao, execucao_id, status="cancelada")
            await self.emitir(execucao_id, "execucao.cancelada", {})
            self._limpar(execucao_id)
        except Exception as erro:
            log.exception("Falha na execução %s", execucao_id)
            mensagem = f"{type(erro).__name__}: {str(erro)[:500]}"
            await asyncio.to_thread(self.repo.atualizar_execucao, execucao_id, status="erro", erro=mensagem)
            await self.emitir(execucao_id, "execucao.erro", {"mensagem": mensagem})
            self._limpar(execucao_id)

    def _limpar(self, execucao_id: str) -> None:
        self.contextos.pop(execucao_id, None)
        self.sequencias.pop(execucao_id, None)
        self.travas.pop(execucao_id, None)

    def obter(self, execucao_id: str) -> dict:
        execucao = self.repo.obter_execucao(execucao_id)
        if execucao is None:
            raise ExecucaoNaoEncontrada(execucao_id)
        return execucao.detalhe()

    async def responder_plano(self, execucao_id: str, aprovacao: AprovacaoPlano) -> dict:
        execucao = self.repo.obter_execucao(execucao_id)
        if execucao is None:
            raise ExecucaoNaoEncontrada(execucao_id)
        if execucao.status != "aguardando_aprovacao" or execucao_id not in self.contextos:
            raise EstadoInvalido("Esta tarefa não está aguardando aprovação do plano.")
        anterior = self.tarefas.get(execucao_id)
        if anterior is not None and not anterior.done():
            raise EstadoInvalido("A resposta a este plano já está sendo processada.")
        resposta = {
            "aprovado": aprovacao.aprovado,
            "plano": aprovacao.plano.model_dump() if aprovacao.plano else None,
            "comentario": aprovacao.comentario,
        }
        await asyncio.to_thread(self.repo.atualizar_execucao, execucao_id, status="na_fila")
        self._iniciar(execucao_id, Command(resume=resposta))
        return self.obter(execucao_id)

    async def cancelar(self, execucao_id: str) -> dict:
        execucao = self.repo.obter_execucao(execucao_id)
        if execucao is None:
            raise ExecucaoNaoEncontrada(execucao_id)
        tarefa = self.tarefas.get(execucao_id)
        if tarefa:
            tarefa.cancel()
            try:
                await tarefa
            except asyncio.CancelledError:
                pass
        elif execucao.status == "aguardando_aprovacao":
            await asyncio.to_thread(self.repo.atualizar_execucao, execucao_id, status="cancelada")
            await self.emitir(execucao_id, "execucao.cancelada", {})
            self._limpar(execucao_id)
        else:
            raise EstadoInvalido("Esta tarefa já terminou.")
        return self.obter(execucao_id)

    async def excluir(self, execucao_id: str) -> None:
        if self.repo.obter_execucao(execucao_id) is None:
            raise ExecucaoNaoEncontrada(execucao_id)
        tarefa = self.tarefas.get(execucao_id)
        if tarefa:
            tarefa.cancel()
            try:
                await tarefa
            except asyncio.CancelledError:
                pass
        self._limpar(execucao_id)
        await asyncio.to_thread(self.repo.excluir_execucao, execucao_id)

    async def acompanhar(self, execucao_id: str, desde: int = 0) -> AsyncIterator[dict | None]:
        if self.repo.obter_execucao(execucao_id) is None:
            raise ExecucaoNaoEncontrada(execucao_id)
        fila: asyncio.Queue = asyncio.Queue()
        self.assinantes[execucao_id].add(fila)
        try:
            ultimo = desde
            for evento in await asyncio.to_thread(self.repo.eventos, execucao_id, desde):
                ultimo = evento.seq
                yield evento.como_dict()
            execucao = self.repo.obter_execucao(execucao_id)
            parada = STATUS_FINAIS + ("aguardando_aprovacao",)
            if execucao is None or (execucao.status in parada and execucao_id not in self.tarefas):
                for evento in await asyncio.to_thread(self.repo.eventos, execucao_id, ultimo):
                    yield evento.como_dict()
                return
            while True:
                try:
                    evento = await asyncio.wait_for(fila.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield None
                    continue
                if evento.get("seq") is not None and evento["seq"] <= ultimo:
                    continue
                if evento.get("seq") is not None:
                    ultimo = evento["seq"]
                yield evento
                if evento["tipo"] in EVENTOS_FINAIS:
                    return
        finally:
            self.assinantes[execucao_id].discard(fila)
            if not self.assinantes[execucao_id]:
                self.assinantes.pop(execucao_id, None)

    def exportar(self, execucao_id: str, formato: str) -> tuple[str, str, str]:
        execucao = self.repo.obter_execucao(execucao_id)
        if execucao is None:
            raise ExecucaoNaoEncontrada(execucao_id)
        if formato == "json":
            dados = {**execucao.detalhe(), "eventos": [e.como_dict() for e in self.repo.eventos(execucao_id)]}
            return json.dumps(dados, ensure_ascii=False, indent=2), "application/json", "json"
        if not execucao.resultado:
            raise EstadoInvalido("Esta tarefa ainda não tem texto final.")
        return execucao.resultado, "text/markdown; charset=utf-8", "md"

    async def encerrar(self) -> None:
        for tarefa in list(self.tarefas.values()):
            tarefa.cancel()
        await asyncio.gather(*self.tarefas.values(), return_exceptions=True)
