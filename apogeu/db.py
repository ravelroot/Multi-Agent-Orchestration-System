from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, create_engine, delete, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

STATUS_ATIVOS = ("na_fila", "em_andamento", "aguardando_aprovacao")
STATUS_FINAIS = ("concluida", "cancelada", "erro", "recusada", "interrompida")


def agora() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Execucao(Base):
    __tablename__ = "bt_execucao"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    titulo: Mapped[str] = mapped_column(String(200))
    tarefa: Mapped[str] = mapped_column(Text)
    briefing: Mapped[dict] = mapped_column(JSON, default=dict)
    opcoes: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(30), index=True)
    provedor: Mapped[str] = mapped_column(String(40), default="")
    modelo: Mapped[str] = mapped_column(String(120), default="")
    plano: Mapped[dict] = mapped_column(JSON, default=dict)
    resultado: Mapped[str | None] = mapped_column(Text, nullable=True)
    fontes: Mapped[list] = mapped_column(JSON, default=list)
    metricas: Mapped[dict] = mapped_column(JSON, default=dict)
    erro: Mapped[str | None] = mapped_column(Text, nullable=True)
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    atualizada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)

    def resumo(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "titulo": self.titulo,
            "status": self.status,
            "tipo": (self.briefing or {}).get("tipo", "artigo"),
            "criada_em": self.criada_em.isoformat(),
            "atualizada_em": self.atualizada_em.isoformat(),
        }

    def detalhe(self) -> dict[str, Any]:
        return {
            **self.resumo(),
            "tarefa": self.tarefa,
            "briefing": self.briefing or {},
            "opcoes": self.opcoes or {},
            "provedor": self.provedor,
            "modelo": self.modelo,
            "plano": self.plano or {},
            "resultado": self.resultado,
            "fontes": self.fontes or [],
            "metricas": self.metricas or {},
            "erro": self.erro,
        }


class Evento(Base):
    __tablename__ = "bt_evento"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    execucao_id: Mapped[str] = mapped_column(String(36), ForeignKey("bt_execucao.id", ondelete="CASCADE"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    tipo: Mapped[str] = mapped_column(String(60))
    dados: Mapped[dict] = mapped_column(JSON, default=dict)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)

    def como_dict(self) -> dict[str, Any]:
        return {"seq": self.seq, "tipo": self.tipo, "dados": self.dados, "criado_em": self.criado_em.isoformat()}


class AgenteConfig(Base):
    __tablename__ = "bt_agente"

    chave: Mapped[str] = mapped_column(String(40), primary_key=True)
    prompt_sistema: Mapped[str] = mapped_column(Text)
    temperatura: Mapped[float] = mapped_column(Float)
    modelo: Mapped[str] = mapped_column(String(120), default="")
    ferramentas: Mapped[list] = mapped_column(JSON, default=list)
    max_iteracoes: Mapped[int] = mapped_column(Integer)
    atualizado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)


class Repositorio:
    def __init__(self, url: str):
        argumentos = {"check_same_thread": False} if url.startswith("sqlite") else {}
        self.engine = create_engine(url, connect_args=argumentos, pool_pre_ping=True)
        self.sessao = sessionmaker(self.engine, expire_on_commit=False)
        Base.metadata.create_all(self.engine)

    def criar_execucao(self, **campos: Any) -> Execucao:
        with self.sessao.begin() as s:
            execucao = Execucao(**campos)
            s.add(execucao)
        return execucao

    def obter_execucao(self, execucao_id: str) -> Execucao | None:
        with self.sessao() as s:
            return s.get(Execucao, execucao_id)

    def listar_execucoes(self, limite: int = 50) -> list[Execucao]:
        with self.sessao() as s:
            consulta = select(Execucao).order_by(Execucao.criada_em.desc()).limit(limite)
            return list(s.scalars(consulta))

    def atualizar_execucao(self, execucao_id: str, **campos: Any) -> Execucao | None:
        with self.sessao.begin() as s:
            execucao = s.get(Execucao, execucao_id)
            if execucao is None:
                return None
            for chave, valor in campos.items():
                setattr(execucao, chave, valor)
            execucao.atualizada_em = agora()
        return execucao

    def excluir_execucao(self, execucao_id: str) -> bool:
        with self.sessao.begin() as s:
            s.execute(delete(Evento).where(Evento.execucao_id == execucao_id))
            resultado = s.execute(delete(Execucao).where(Execucao.id == execucao_id))
        return resultado.rowcount > 0

    def interromper_pendentes(self) -> int:
        with self.sessao.begin() as s:
            pendentes = list(s.scalars(select(Execucao).where(Execucao.status.in_(STATUS_ATIVOS))))
            for execucao in pendentes:
                execucao.status = "interrompida"
                execucao.erro = "O servidor foi reiniciado antes do fim desta tarefa."
                execucao.atualizada_em = agora()
        return len(pendentes)

    def ultimo_seq(self, execucao_id: str) -> int:
        with self.sessao() as s:
            valor = s.scalar(select(func.max(Evento.seq)).where(Evento.execucao_id == execucao_id))
            return int(valor or 0)

    def registrar_evento(self, execucao_id: str, seq: int, tipo: str, dados: dict) -> Evento:
        with self.sessao.begin() as s:
            evento = Evento(execucao_id=execucao_id, seq=seq, tipo=tipo, dados=dados)
            s.add(evento)
        return evento

    def eventos(self, execucao_id: str, desde: int = 0) -> list[Evento]:
        with self.sessao() as s:
            consulta = (
                select(Evento)
                .where(Evento.execucao_id == execucao_id, Evento.seq > desde)
                .order_by(Evento.seq)
            )
            return list(s.scalars(consulta))

    def agentes(self) -> dict[str, AgenteConfig]:
        with self.sessao() as s:
            return {a.chave: a for a in s.scalars(select(AgenteConfig))}

    def salvar_agente(self, chave: str, **campos: Any) -> AgenteConfig:
        with self.sessao.begin() as s:
            agente = s.get(AgenteConfig, chave)
            if agente is None:
                agente = AgenteConfig(chave=chave, **campos)
                s.add(agente)
            else:
                for nome, valor in campos.items():
                    setattr(agente, nome, valor)
            agente.atualizado_em = agora()
        return agente
