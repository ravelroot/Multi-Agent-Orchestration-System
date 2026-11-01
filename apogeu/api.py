import asyncio
import hmac
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import RAIZ, __version__
from .agentes import PADROES, carregar_agentes, garantir_padroes, restaurar_padrao
from .config import Configuracao, obter_configuracao
from .db import Repositorio
from .esquemas import AprovacaoPlano, AtualizacaoAgente, NovaExecucao
from .execucoes import EstadoInvalido, ExecucaoNaoEncontrada, ServicoExecucoes
from .ferramentas import catalogo
from .grafo import diagrama_mermaid
from .llm import resolver_provedor

PASTA_INTERFACE = RAIZ / "frontend" / "out"


def criar_app(cfg: Configuracao | None = None, pasta_interface: Path | None = PASTA_INTERFACE) -> FastAPI:
    cfg = cfg or obter_configuracao()

    @asynccontextmanager
    async def ciclo(app: FastAPI):
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
        repo = Repositorio(cfg.url_banco)
        garantir_padroes(repo)
        repo.interromper_pendentes()
        provedor = await asyncio.to_thread(resolver_provedor, cfg)
        logging.getLogger("apogeu").info("Provedor: %s (%s), %s", provedor.nome, provedor.modelo, provedor.motivo)
        app.state.repo = repo
        app.state.provedor = provedor
        app.state.servico = ServicoExecucoes(repo, cfg, provedor)
        yield
        await app.state.servico.encerrar()
        repo.engine.dispose()

    app = FastAPI(
        title="Apogeu",
        version=__version__,
        description="Orquestrador de agentes de IA: supervisor, pesquisador, redator e revisor.",
        lifespan=ciclo,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.origens,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "Last-Event-ID"],
    )

    @app.middleware("http")
    async def cabecalhos_seguros(request: Request, chamar_proximo):
        resposta = await chamar_proximo(request)
        resposta.headers.setdefault("X-Content-Type-Options", "nosniff")
        resposta.headers.setdefault("X-Frame-Options", "DENY")
        resposta.headers.setdefault("Referrer-Policy", "no-referrer")
        return resposta

    def autenticar(request: Request) -> None:
        if not cfg.token:
            return
        cabecalho = request.headers.get("authorization", "")
        enviado = cabecalho[7:] if cabecalho.lower().startswith("bearer ") else request.query_params.get("token", "")
        if not hmac.compare_digest(enviado.encode(), cfg.token.encode()):
            raise HTTPException(401, "Token inválido ou ausente.")

    def servico(request: Request) -> ServicoExecucoes:
        return request.app.state.servico

    @app.exception_handler(ExecucaoNaoEncontrada)
    async def nao_encontrada(_: Request, __: ExecucaoNaoEncontrada):
        return JSONResponse({"detail": "Tarefa não encontrada."}, status_code=404)

    @app.exception_handler(EstadoInvalido)
    async def estado_invalido(_: Request, erro: EstadoInvalido):
        return JSONResponse({"detail": str(erro)}, status_code=409)

    protegido = [Depends(autenticar)]

    @app.get("/api/saude")
    async def saude(request: Request):
        provedor = request.app.state.provedor
        return {
            "versao": __version__,
            "provedor": provedor.como_dict(),
            "ferramentas": "simuladas" if cfg.ferramentas_simuladas else cfg.busca,
            "autenticacao": bool(cfg.token),
            "limites": {
                "contexto": cfg.limite_contexto,
                "notas": cfg.limite_notas,
                "passos": cfg.max_passos,
                "revisoes": cfg.max_revisoes,
                "nota_minima": cfg.nota_minima,
            },
        }

    @app.get("/api/agentes", dependencies=protegido)
    async def listar_agentes(request: Request):
        return [a.publico() for a in carregar_agentes(request.app.state.repo).values()]

    @app.put("/api/agentes/{chave}", dependencies=protegido)
    async def atualizar_agente(chave: str, dados: AtualizacaoAgente, request: Request):
        if chave not in PADROES:
            raise HTTPException(404, "Agente não encontrado.")
        repo: Repositorio = request.app.state.repo
        atual = carregar_agentes(repo)[chave]
        ferramentas = atual.ferramentas if dados.ferramentas is None else dados.ferramentas
        invalidas = [f for f in ferramentas if f not in atual.permitidas]
        if invalidas:
            raise HTTPException(422, f"Ferramentas não permitidas para {atual.nome}: {', '.join(invalidas)}.")
        repo.salvar_agente(
            chave,
            prompt_sistema=dados.prompt_sistema if dados.prompt_sistema is not None else atual.prompt_sistema,
            temperatura=dados.temperatura if dados.temperatura is not None else atual.temperatura,
            modelo=(dados.modelo if dados.modelo is not None else atual.modelo).strip(),
            ferramentas=list(dict.fromkeys(ferramentas)),
            max_iteracoes=dados.max_iteracoes if dados.max_iteracoes is not None else atual.max_iteracoes,
        )
        return carregar_agentes(repo)[chave].publico()

    @app.post("/api/agentes/{chave}/restaurar", dependencies=protegido)
    async def restaurar_agente(chave: str, request: Request):
        if chave not in PADROES:
            raise HTTPException(404, "Agente não encontrado.")
        restaurar_padrao(request.app.state.repo, chave)
        return carregar_agentes(request.app.state.repo)[chave].publico()

    @app.get("/api/ferramentas", dependencies=protegido)
    async def listar_ferramentas():
        return catalogo()

    @app.get("/api/grafo", dependencies=protegido)
    async def grafo():
        return {"mermaid": diagrama_mermaid()}

    @app.get("/api/execucoes", dependencies=protegido)
    async def listar_execucoes(request: Request, limite: int = Query(50, ge=1, le=200)):
        return [e.resumo() for e in request.app.state.repo.listar_execucoes(limite)]

    @app.post("/api/execucoes", status_code=201, dependencies=protegido)
    async def criar_execucao(pedido: NovaExecucao, s: ServicoExecucoes = Depends(servico)):
        return await s.criar(pedido)

    @app.get("/api/execucoes/{execucao_id}", dependencies=protegido)
    async def obter_execucao(execucao_id: str, s: ServicoExecucoes = Depends(servico)):
        return s.obter(execucao_id)

    @app.delete("/api/execucoes/{execucao_id}", status_code=204, dependencies=protegido)
    async def excluir_execucao(execucao_id: str, s: ServicoExecucoes = Depends(servico)):
        await s.excluir(execucao_id)
        return Response(status_code=204)

    @app.post("/api/execucoes/{execucao_id}/aprovacao", dependencies=protegido)
    async def responder_plano(execucao_id: str, aprovacao: AprovacaoPlano, s: ServicoExecucoes = Depends(servico)):
        return await s.responder_plano(execucao_id, aprovacao)

    @app.post("/api/execucoes/{execucao_id}/cancelar", dependencies=protegido)
    async def cancelar_execucao(execucao_id: str, s: ServicoExecucoes = Depends(servico)):
        return await s.cancelar(execucao_id)

    @app.get("/api/execucoes/{execucao_id}/exportar", dependencies=protegido)
    async def exportar(execucao_id: str, formato: str = Query("markdown", pattern="^(markdown|json)$"), s: ServicoExecucoes = Depends(servico)):
        conteudo, tipo, extensao = s.exportar(execucao_id, formato)
        nome = f"apogeu-{execucao_id[:8]}.{extensao}"
        return Response(conteudo, media_type=tipo, headers={"Content-Disposition": f'attachment; filename="{nome}"'})

    @app.get("/api/execucoes/{execucao_id}/eventos", dependencies=protegido)
    async def eventos(execucao_id: str, request: Request, desde: int = Query(0, ge=0), s: ServicoExecucoes = Depends(servico)):
        ultimo = request.headers.get("last-event-id", "")
        inicio = int(ultimo) if ultimo.isdigit() else desde
        fluxo = s.acompanhar(execucao_id, inicio)
        primeiro = await anext(fluxo, StopAsyncIteration)

        async def gerar():
            atual = primeiro
            try:
                while atual is not StopAsyncIteration:
                    if await request.is_disconnected():
                        break
                    if atual is None:
                        yield "event: ping\ndata: {}\n\n"
                    else:
                        linhas = f"data: {json.dumps(atual, ensure_ascii=False)}\n\n"
                        if atual.get("seq") is not None:
                            linhas = f"id: {atual['seq']}\n" + linhas
                        yield linhas
                    atual = await anext(fluxo, StopAsyncIteration)
            finally:
                await fluxo.aclose()

        return StreamingResponse(
            gerar(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
        )

    if pasta_interface and pasta_interface.exists():
        app.mount("/", StaticFiles(directory=pasta_interface, html=True), name="interface")
    else:

        @app.get("/", include_in_schema=False)
        async def sem_interface():
            return JSONResponse(
                {"mensagem": "A API está no ar. Compile a interface com 'cd frontend && npm install && npm run build' ou use /api/docs."}
            )

    return app
