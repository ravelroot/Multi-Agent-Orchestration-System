import math
from dataclasses import dataclass

from langchain_core.messages import BaseMessage, ToolMessage
from langchain_core.messages.utils import count_tokens_approximately

CARACTERES_POR_TOKEN = 4.0


def tokens_texto(texto: str) -> int:
    return math.ceil(len(texto or "") / CARACTERES_POR_TOKEN)


def tokens_mensagens(mensagens: list[BaseMessage]) -> int:
    return count_tokens_approximately(mensagens, chars_per_token=CARACTERES_POR_TOKEN)


def truncar(texto: str, max_caracteres: int) -> str:
    texto = texto or ""
    if len(texto) <= max_caracteres:
        return texto
    corte = max(0, max_caracteres - 60)
    fim = texto.rfind("\n", 0, corte)
    if fim < corte * 0.6:
        fim = corte
    return f"{texto[:fim].rstrip()}\n[... {len(texto) - fim} caracteres omitidos]"


@dataclass
class Secao:
    chave: str
    conteudo: str
    prioridade: int
    compactavel: bool = True

    @property
    def tokens(self) -> int:
        return tokens_texto(self.conteudo) + tokens_texto(self.chave) * 2 + 4

    def render(self) -> str:
        return f"<{self.chave}>\n{self.conteudo.strip()}\n</{self.chave}>"


@dataclass
class RelatorioContexto:
    tokens_antes: int
    tokens_depois: int
    limite: int
    secoes_cortadas: list[str]

    @property
    def compactado(self) -> bool:
        return bool(self.secoes_cortadas)


def montar_contexto(secoes: list[Secao], limite_tokens: int) -> tuple[str, RelatorioContexto]:
    secoes = [s for s in secoes if s.conteudo and s.conteudo.strip()]
    antes = sum(s.tokens for s in secoes)
    cortadas: list[str] = []
    excesso = antes - limite_tokens
    if excesso > 0:
        candidatas = sorted((s for s in secoes if s.compactavel), key=lambda s: s.prioridade)
        for secao in candidatas:
            if excesso <= 0:
                break
            disponivel = secao.tokens - 80
            if disponivel <= 0:
                continue
            reduzir = min(disponivel, excesso)
            novo_limite = max(320, int((secao.tokens - reduzir) * CARACTERES_POR_TOKEN))
            original = secao.tokens
            secao.conteudo = truncar(secao.conteudo, novo_limite)
            excesso -= original - secao.tokens
            cortadas.append(secao.chave)
    ordenadas = sorted(secoes, key=lambda s: -s.prioridade)
    texto = "\n\n".join(s.render() for s in ordenadas)
    depois = sum(s.tokens for s in secoes)
    return texto, RelatorioContexto(antes, depois, limite_tokens, cortadas)


def compactar_resultados_antigos(mensagens: list[BaseMessage], limite_tokens: int, preservar: int = 2) -> tuple[list[BaseMessage], int]:
    total = tokens_mensagens(mensagens)
    if total <= limite_tokens:
        return mensagens, 0
    indices = [i for i, m in enumerate(mensagens) if isinstance(m, ToolMessage)]
    antigos = indices[:-preservar] if preservar else indices
    compactadas = 0
    resultado = list(mensagens)
    for i in antigos:
        if total <= limite_tokens:
            break
        mensagem = resultado[i]
        conteudo = str(mensagem.content)
        if len(conteudo) <= 400:
            continue
        resumo = truncar(conteudo, 400) + "\n(resultado antigo compactado para caber no contexto)"
        resultado[i] = ToolMessage(content=resumo, tool_call_id=mensagem.tool_call_id, name=mensagem.name)
        total = tokens_mensagens(resultado)
        compactadas += 1
    return resultado, compactadas


def texto_da_resposta(conteudo) -> str:
    if isinstance(conteudo, str):
        return conteudo
    if isinstance(conteudo, list):
        partes = []
        for bloco in conteudo:
            if isinstance(bloco, str):
                partes.append(bloco)
            elif isinstance(bloco, dict) and bloco.get("type") == "text":
                partes.append(bloco.get("text", ""))
        return "".join(partes)
    return str(conteudo or "")
