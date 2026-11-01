from dataclasses import dataclass

import httpx
from langchain_core.language_models.chat_models import BaseChatModel

from .config import Configuracao
from .demonstracao import ModeloDemonstracao

MODELOS_PADRAO = {
    "openai": "gpt-4.1-mini",
    "anthropic": "claude-sonnet-5-5",
    "ollama": "qwen2.5:7b",
    "demonstracao": "roteiro-local",
}

PROVEDORES = tuple(MODELOS_PADRAO)


@dataclass
class Provedor:
    nome: str
    modelo: str
    motivo: str

    def como_dict(self) -> dict:
        return {"nome": self.nome, "modelo": self.modelo, "motivo": self.motivo}


def ollama_disponivel(url: str) -> bool:
    try:
        resposta = httpx.get(f"{url.rstrip('/')}/api/tags", timeout=1.5)
        return resposta.status_code == 200
    except httpx.HTTPError:
        return False


def resolver_provedor(cfg: Configuracao) -> Provedor:
    escolhido = cfg.provedor.lower().strip()
    if escolhido != "auto":
        if escolhido not in PROVEDORES:
            raise ValueError(f"Provedor desconhecido: {cfg.provedor}. Use auto, {', '.join(PROVEDORES)}.")
        return Provedor(escolhido, cfg.modelo or MODELOS_PADRAO[escolhido], "definido em APOGEU_PROVEDOR")
    if cfg.openai_api_key:
        return Provedor("openai", cfg.modelo or MODELOS_PADRAO["openai"], "OPENAI_API_KEY encontrada")
    if cfg.anthropic_api_key:
        return Provedor("anthropic", cfg.modelo or MODELOS_PADRAO["anthropic"], "ANTHROPIC_API_KEY encontrada")
    if ollama_disponivel(cfg.ollama_url):
        return Provedor("ollama", cfg.modelo or MODELOS_PADRAO["ollama"], "Ollama respondendo em " + cfg.ollama_url)
    return Provedor("demonstracao", MODELOS_PADRAO["demonstracao"], "nenhuma chave nem Ollama encontrados")


def criar_modelo(
    cfg: Configuracao,
    provedor: Provedor,
    papel: str,
    modelo: str = "",
    temperatura: float | None = None,
) -> BaseChatModel:
    nome = modelo or provedor.modelo
    temp = cfg.temperatura if temperatura is None else temperatura
    if provedor.nome == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=nome,
            temperature=temp,
            api_key=cfg.openai_api_key or None,
            base_url=cfg.openai_base_url or None,
            timeout=cfg.timeout_llm,
            max_retries=2,
            max_tokens=cfg.max_tokens_resposta,
        )
    if provedor.nome == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=nome,
            temperature=min(temp, 1.0),
            api_key=cfg.anthropic_api_key or None,
            timeout=cfg.timeout_llm,
            max_retries=2,
            max_tokens=cfg.max_tokens_resposta,
        )
    if provedor.nome == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(model=nome, temperature=temp, base_url=cfg.ollama_url, num_predict=cfg.max_tokens_resposta)
    return ModeloDemonstracao(papel=papel, atraso=cfg.atraso_demonstracao)


def estruturado(modelo: BaseChatModel, esquema, provedor: Provedor):
    if provedor.nome in {"openai", "ollama"}:
        return modelo.with_structured_output(esquema, method="function_calling")
    return modelo.with_structured_output(esquema)
