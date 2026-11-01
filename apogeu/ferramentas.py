import ast
import asyncio
import ipaddress
import operator
import re
import socket
from dataclasses import dataclass, field
from datetime import datetime
from html.parser import HTMLParser
from typing import Callable
from urllib.parse import quote, urljoin, urlparse

import httpx
from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, Field

from . import __version__
from .config import Configuracao
from .contexto import truncar

AGENTE_HTTP = f"Apogeu/{__version__} (orquestrador de agentes; uso educacional)"
TAMANHO_MAXIMO_PAGINA = 2_000_000

DESCRICOES = {
    "buscar_web": "Busca na web e devolve títulos, links e resumos, cada um com o número [n] da fonte.",
    "consultar_wikipedia": "Consulta a Wikipédia e devolve o resumo do verbete mais relevante, com o número [n] da fonte.",
    "ler_pagina": "Lê uma página pública (http ou https) e devolve o texto principal, com o número [n] da fonte.",
    "calcular": "Calcula uma expressão matemática com + - * / // % ** e parênteses. Use para qualquer conta.",
    "data_atual": "Informa a data e a hora atuais. Use para calcular idades, prazos ou intervalos.",
    "contar_palavras": "Conta palavras, frases e parágrafos de um texto e estima o tempo de leitura.",
    "metricas_do_rascunho": "Mede o rascunho atual: palavras, parágrafos, seções, legibilidade e distância do tamanho pedido.",
    "verificar_citacoes": "Confere as citações [n] do rascunho atual: números inválidos, fontes não citadas e parágrafos sem citação.",
}


@dataclass
class Fonte:
    id: int
    titulo: str
    url: str
    trecho: str = ""
    origem: str = "web"

    def como_dict(self) -> dict:
        return {"id": self.id, "titulo": self.titulo, "url": self.url, "trecho": self.trecho, "origem": self.origem}


@dataclass
class ColetorFontes:
    fontes: list[Fonte] = field(default_factory=list)

    @classmethod
    def de_lista(cls, itens: list[dict]) -> "ColetorFontes":
        return cls([Fonte(**i) for i in itens])

    def registrar(self, titulo: str, url: str, trecho: str = "", origem: str = "web") -> Fonte:
        normalizada = url.rstrip("/")
        for fonte in self.fontes:
            if fonte.url.rstrip("/") == normalizada:
                if trecho and len(trecho) > len(fonte.trecho):
                    fonte.trecho = trecho[:600]
                return fonte
        fonte = Fonte(len(self.fontes) + 1, (titulo or url)[:200], url, trecho[:600], origem)
        self.fontes.append(fonte)
        return fonte

    def ids(self) -> set[int]:
        return {f.id for f in self.fontes}

    def lista(self) -> list[dict]:
        return [f.como_dict() for f in self.fontes]


class ExtratorTexto(HTMLParser):
    IGNORAR = {"script", "style", "noscript", "svg", "nav", "footer", "header", "form", "aside", "iframe"}
    BLOCOS = {"p", "div", "section", "article", "li", "h1", "h2", "h3", "h4", "h5", "h6", "br", "tr", "blockquote", "pre"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.partes: list[str] = []
        self.titulo = ""
        self._ignorando = 0
        self._no_titulo = False

    def handle_starttag(self, tag, attrs):
        if tag in self.IGNORAR:
            self._ignorando += 1
        elif tag == "title":
            self._no_titulo = True
        elif tag in self.BLOCOS:
            self.partes.append("\n")

    def handle_endtag(self, tag):
        if tag in self.IGNORAR and self._ignorando:
            self._ignorando -= 1
        elif tag == "title":
            self._no_titulo = False
        elif tag in self.BLOCOS:
            self.partes.append("\n")

    def handle_data(self, data):
        if self._no_titulo:
            self.titulo += data
        elif not self._ignorando:
            self.partes.append(data)

    def texto(self) -> str:
        bruto = "".join(self.partes)
        linhas = [re.sub(r"\s+", " ", linha).strip() for linha in bruto.splitlines()]
        linhas = [linha for linha in linhas if len(linha) > 2]
        return "\n".join(linhas)


def endereco_publico(host: str) -> bool | None:
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return None
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            return False
    return True


def validar_url(url: str, resolver: bool = True) -> str | None:
    try:
        partes = urlparse(url)
        porta = partes.port
    except ValueError:
        return "Endereço inválido."
    if partes.scheme not in {"http", "https"}:
        return "Use um endereço http ou https."
    if not partes.hostname:
        return "Endereço sem domínio."
    if porta and porta not in {80, 443}:
        return "Só são permitidas as portas 80 e 443."
    if partes.username or partes.password:
        return "Endereços com usuário ou senha não são aceitos."
    if not resolver:
        return None
    publico = endereco_publico(partes.hostname)
    if publico is None:
        return "Domínio não encontrado."
    if not publico:
        return "Endereços internos, locais ou privados não podem ser acessados."
    return None


OPERADORES_BINARIOS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
OPERADORES_UNARIOS = {ast.UAdd: operator.pos, ast.USub: operator.neg}


def avaliar_expressao(expressao: str) -> float:
    if len(expressao) > 200:
        raise ValueError("Expressão longa demais.")
    arvore = ast.parse(expressao.replace(",", ".").replace("^", "**"), mode="eval")

    def visitar(no):
        if isinstance(no, ast.Expression):
            return visitar(no.body)
        if isinstance(no, ast.Constant) and isinstance(no.value, (int, float)) and not isinstance(no.value, bool):
            return no.value
        if isinstance(no, ast.BinOp) and type(no.op) in OPERADORES_BINARIOS:
            esquerda, direita = visitar(no.left), visitar(no.right)
            if isinstance(no.op, ast.Pow) and (abs(direita) > 64 or abs(esquerda) > 1e6):
                raise ValueError("Potência grande demais.")
            return OPERADORES_BINARIOS[type(no.op)](esquerda, direita)
        if isinstance(no, ast.UnaryOp) and type(no.op) in OPERADORES_UNARIOS:
            return OPERADORES_UNARIOS[type(no.op)](visitar(no.operand))
        raise ValueError("Use apenas números, parênteses e + - * / // % **.")

    return visitar(arvore)


VOGAIS = "aeiouáéíóúâêôãõàüy"


def silabas(palavra: str) -> int:
    palavra = palavra.lower()
    grupos = re.findall(rf"[{VOGAIS}]+", palavra)
    return max(1, len(grupos))


def analisar_texto(texto: str) -> dict:
    limpo = re.sub(r"\[(\d+)\]", "", texto or "")
    limpo = re.sub(r"[#*_>`]", "", limpo)
    palavras = re.findall(r"[A-Za-zÀ-ÿ0-9]+(?:[-'][A-Za-zÀ-ÿ0-9]+)*", limpo)
    frases = [f for f in re.split(r"(?<=[.!?])\s+|\n+", limpo) if re.search(r"[A-Za-zÀ-ÿ]", f)]
    paragrafos = [p for p in re.split(r"\n\s*\n", texto or "") if p.strip() and not p.strip().startswith("#")]
    n_palavras = len(palavras)
    n_frases = max(1, len(frases))
    n_silabas = sum(silabas(p) for p in palavras) or 1
    flesch = 248.835 - 1.015 * (n_palavras / n_frases) - 84.6 * (n_silabas / max(1, n_palavras))
    flesch = round(max(0.0, min(100.0, flesch)), 1)
    if flesch >= 75:
        faixa = "muito fácil"
    elif flesch >= 50:
        faixa = "fácil"
    elif flesch >= 25:
        faixa = "difícil"
    else:
        faixa = "muito difícil"
    return {
        "palavras": n_palavras,
        "frases": len(frases),
        "paragrafos": len(paragrafos),
        "palavras_por_frase": round(n_palavras / n_frases, 1),
        "legibilidade": flesch,
        "faixa_legibilidade": faixa,
        "minutos_leitura": max(1, round(n_palavras / 200)),
    }


def analisar_citacoes(texto: str, ids_validos: set[int]) -> dict:
    citadas = [int(n) for n in re.findall(r"\[(\d+)\]", texto or "")]
    unicas = sorted(set(citadas))
    invalidas = [n for n in unicas if n not in ids_validos]
    nao_citadas = sorted(ids_validos - set(unicas))
    paragrafos = [
        p.strip() for p in re.split(r"\n\s*\n", texto or "")
        if p.strip() and not p.strip().startswith("#") and len(p.split()) > 25
    ]
    sem_citacao = [p[:90] + "..." for p in paragrafos if not re.search(r"\[\d+\]", p)]
    return {
        "total_citacoes": len(citadas),
        "fontes_citadas": unicas,
        "citacoes_invalidas": invalidas,
        "fontes_nao_citadas": nao_citadas,
        "paragrafos_sem_citacao": sem_citacao[:5],
    }


class ArgsBusca(BaseModel):
    consulta: str = Field(description="Termos de busca, de 2 a 12 palavras")
    max_resultados: int = Field(5, description="Quantidade de resultados, de 1 a 8")


class ArgsWikipedia(BaseModel):
    termo: str = Field(description="Assunto do verbete")
    idioma: str = Field("pt", description="Código do idioma da Wikipédia, como pt ou en")


class ArgsPagina(BaseModel):
    url: str = Field(description="Endereço completo da página, começando com http ou https")


class ArgsCalculo(BaseModel):
    expressao: str = Field(description="Expressão matemática, por exemplo (1250 - 980) / 980 * 100")


class ArgsTexto(BaseModel):
    texto: str = Field(description="Texto a analisar")


class ArgsVazio(BaseModel):
    pass


class Ferramentas:
    def __init__(
        self,
        cfg: Configuracao,
        coletor: ColetorFontes,
        obter_rascunho: Callable[[], str] = lambda: "",
        obter_briefing: Callable[[], dict] = lambda: {},
    ):
        self.cfg = cfg
        self.coletor = coletor
        self.obter_rascunho = obter_rascunho
        self.obter_briefing = obter_briefing

    def _cliente(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=self.cfg.timeout_ferramentas,
            headers={"User-Agent": AGENTE_HTTP, "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.6"},
            follow_redirects=False,
        )

    def _formatar_resultados(self, itens: list[tuple[str, str, str]], origem: str) -> str:
        if not itens:
            return "Nenhum resultado encontrado. Tente termos diferentes."
        linhas = []
        for titulo, url, resumo in itens:
            fonte = self.coletor.registrar(titulo, url, resumo, origem)
            linhas.append(f"[{fonte.id}] {fonte.titulo}\n{url}\n{resumo.strip()}")
        return "\n\n".join(linhas)

    async def buscar_web(self, consulta: str, max_resultados: int = 5) -> str:
        consulta = consulta.strip()[:200]
        quantidade = max(1, min(8, int(max_resultados or 5)))
        if self.cfg.ferramentas_simuladas:
            return self._formatar_resultados(simular_busca(consulta, quantidade), "web")
        if self.cfg.busca == "tavily" and self.cfg.tavily_api_key:
            itens = await self._buscar_tavily(consulta, quantidade)
        else:
            itens = await asyncio.to_thread(self._buscar_ddgs, consulta, quantidade)
        return self._formatar_resultados(itens, "web")

    def _buscar_ddgs(self, consulta: str, quantidade: int) -> list[tuple[str, str, str]]:
        from ddgs import DDGS

        resultados = DDGS(timeout=self.cfg.timeout_ferramentas).text(
            consulta, region=self.cfg.regiao_busca, max_results=quantidade
        )
        return [(r.get("title", ""), r.get("href", ""), r.get("body", "")) for r in resultados if r.get("href")]

    async def _buscar_tavily(self, consulta: str, quantidade: int) -> list[tuple[str, str, str]]:
        async with self._cliente() as cliente:
            resposta = await cliente.post(
                "https://api.tavily.com/search",
                headers={"Authorization": f"Bearer {self.cfg.tavily_api_key}"},
                json={"query": consulta, "max_results": quantidade, "search_depth": "basic"},
            )
            resposta.raise_for_status()
            dados = resposta.json()
        return [(r.get("title", ""), r.get("url", ""), r.get("content", "")) for r in dados.get("results", [])]

    async def consultar_wikipedia(self, termo: str, idioma: str = "pt") -> str:
        termo = termo.strip()[:150]
        idioma = idioma if re.fullmatch(r"[a-z]{2,3}", idioma or "") else "pt"
        if self.cfg.ferramentas_simuladas:
            titulo, url, resumo = simular_wikipedia(termo, idioma)
            return self._formatar_resultados([(titulo, url, resumo)], "wikipedia")
        base = f"https://{idioma}.wikipedia.org"
        async with self._cliente() as cliente:
            busca = await cliente.get(
                f"{base}/w/api.php",
                params={"action": "query", "list": "search", "srsearch": termo, "format": "json", "srlimit": 1},
            )
            busca.raise_for_status()
            achados = busca.json().get("query", {}).get("search", [])
            if not achados:
                return f"Nenhum verbete encontrado para '{termo}' na Wikipédia ({idioma})."
            titulo = achados[0]["title"]
            resumo = await cliente.get(f"{base}/api/rest_v1/page/summary/{quote(titulo.replace(' ', '_'))}")
            resumo.raise_for_status()
            dados = resumo.json()
        url = dados.get("content_urls", {}).get("desktop", {}).get("page") or f"{base}/wiki/{quote(titulo)}"
        return self._formatar_resultados([(f"{titulo} (Wikipédia)", url, dados.get("extract", ""))], "wikipedia")

    async def ler_pagina(self, url: str) -> str:
        url = url.strip()
        erro = await asyncio.to_thread(validar_url, url, not self.cfg.ferramentas_simuladas)
        if erro:
            return f"Não foi possível ler {url}: {erro}"
        if self.cfg.ferramentas_simuladas:
            titulo, texto = simular_pagina(url)
            fonte = self.coletor.registrar(titulo, url, texto[:300])
            return f"[{fonte.id}] {titulo}\n{url}\n\n{truncar(texto, self.cfg.limite_saida_ferramenta)}"
        async with self._cliente() as cliente:
            atual = url
            for _ in range(4):
                async with cliente.stream("GET", atual) as resposta:
                    if resposta.is_redirect:
                        proximo = urljoin(atual, resposta.headers.get("location", ""))
                        erro = await asyncio.to_thread(validar_url, proximo)
                        if erro:
                            return f"Redirecionamento bloqueado para {proximo}: {erro}"
                        atual = proximo
                        continue
                    resposta.raise_for_status()
                    tipo = resposta.headers.get("content-type", "")
                    if "html" not in tipo and "text/plain" not in tipo:
                        return f"O conteúdo de {atual} não é texto ({tipo or 'tipo desconhecido'})."
                    corpo = bytearray()
                    async for pedaco in resposta.aiter_bytes():
                        corpo.extend(pedaco)
                        if len(corpo) > TAMANHO_MAXIMO_PAGINA:
                            break
                    codificacao = resposta.encoding or "utf-8"
                    html = corpo.decode(codificacao, errors="replace")
                    break
            else:
                return f"Redirecionamentos demais em {url}."
        if "html" in tipo:
            extrator = ExtratorTexto()
            extrator.feed(html)
            titulo = extrator.titulo.strip() or atual
            texto = extrator.texto()
        else:
            titulo, texto = atual, html
        if not texto.strip():
            return f"A página {atual} não tem texto legível."
        fonte = self.coletor.registrar(titulo, atual, texto[:300])
        return f"[{fonte.id}] {fonte.titulo}\n{atual}\n\n{truncar(texto, self.cfg.limite_saida_ferramenta)}"

    async def calcular(self, expressao: str) -> str:
        try:
            valor = avaliar_expressao(expressao)
        except (ValueError, SyntaxError, ZeroDivisionError, OverflowError) as erro:
            return f"Não foi possível calcular '{expressao}': {erro}"
        if isinstance(valor, float):
            valor = round(valor, 6)
        return f"{expressao} = {valor}"

    async def data_atual(self) -> str:
        momento = datetime.now().astimezone()
        dias = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]
        return f"{dias[momento.weekday()]}, {momento:%d/%m/%Y %H:%M} (UTC{momento:%z})"

    async def contar_palavras(self, texto: str) -> str:
        dados = analisar_texto(texto)
        return (
            f"{dados['palavras']} palavras, {dados['frases']} frases, {dados['paragrafos']} parágrafos, "
            f"{dados['palavras_por_frase']} palavras por frase, cerca de {dados['minutos_leitura']} min de leitura."
        )

    async def metricas_do_rascunho(self) -> str:
        rascunho = self.obter_rascunho()
        if not rascunho.strip():
            return "Ainda não existe rascunho."
        dados = analisar_texto(rascunho)
        alvo = int(self.obter_briefing().get("palavras", 0) or 0)
        secoes = len(re.findall(r"^##\s", rascunho, flags=re.M))
        linhas = [
            f"Palavras: {dados['palavras']}" + (f" (pedido: {alvo}, diferença de {round((dados['palavras'] - alvo) / alvo * 100)}%)" if alvo else ""),
            f"Frases: {dados['frases']} | Palavras por frase: {dados['palavras_por_frase']}",
            f"Parágrafos: {dados['paragrafos']} | Seções (##): {secoes}",
            f"Legibilidade (Flesch adaptado ao português): {dados['legibilidade']} ({dados['faixa_legibilidade']})",
            f"Tempo de leitura: cerca de {dados['minutos_leitura']} min",
        ]
        return "\n".join(linhas)

    async def verificar_citacoes(self) -> str:
        rascunho = self.obter_rascunho()
        if not rascunho.strip():
            return "Ainda não existe rascunho."
        dados = analisar_citacoes(rascunho, self.coletor.ids())
        linhas = [
            f"Citações no texto: {dados['total_citacoes']}",
            f"Fontes citadas: {dados['fontes_citadas'] or 'nenhuma'}",
            f"Citações para fontes inexistentes: {dados['citacoes_invalidas'] or 'nenhuma'}",
            f"Fontes disponíveis que não foram citadas: {dados['fontes_nao_citadas'] or 'nenhuma'}",
        ]
        if dados["paragrafos_sem_citacao"]:
            linhas.append("Parágrafos longos sem citação:")
            linhas.extend(f"- {p}" for p in dados["paragrafos_sem_citacao"])
        return "\n".join(linhas)

    def todas(self) -> dict[str, BaseTool]:
        mapa = {
            "buscar_web": (self.buscar_web, ArgsBusca),
            "consultar_wikipedia": (self.consultar_wikipedia, ArgsWikipedia),
            "ler_pagina": (self.ler_pagina, ArgsPagina),
            "calcular": (self.calcular, ArgsCalculo),
            "data_atual": (self.data_atual, ArgsVazio),
            "contar_palavras": (self.contar_palavras, ArgsTexto),
            "metricas_do_rascunho": (self.metricas_do_rascunho, ArgsVazio),
            "verificar_citacoes": (self.verificar_citacoes, ArgsVazio),
        }
        return {
            nome: StructuredTool.from_function(
                coroutine=funcao, name=nome, description=DESCRICOES[nome], args_schema=esquema
            )
            for nome, (funcao, esquema) in mapa.items()
        }

    def selecionar(self, nomes: list[str]) -> list[BaseTool]:
        todas = self.todas()
        return [todas[n] for n in nomes if n in todas]


def catalogo() -> list[dict]:
    ferramentas = Ferramentas(Configuracao(ferramentas="simuladas"), ColetorFontes()).todas()
    return [
        {"nome": nome, "descricao": f.description, "parametros": f.args_schema.model_json_schema().get("properties", {})}
        for nome, f in ferramentas.items()
    ]


def _palavras_chave(texto: str) -> list[str]:
    palavras = re.findall(r"[A-Za-zÀ-ÿ]{4,}", texto.lower())
    vazias = {"sobre", "para", "como", "quais", "qual", "pelo", "pela", "entre", "desde", "mais", "isso", "esta", "este"}
    return [p for p in palavras if p not in vazias][:4] or ["tema"]


def simular_busca(consulta: str, quantidade: int) -> list[tuple[str, str, str]]:
    chave = "-".join(_palavras_chave(consulta))
    tema = consulta.strip().rstrip("?.")
    modelos = [
        ("Panorama", "uma visão geral com definição, origem e principais marcos"),
        ("Dados recentes", "números de adoção, crescimento anual e comparação entre regiões"),
        ("Guia prático", "passos de aplicação, boas práticas e erros comuns"),
        ("Riscos e limites", "limitações conhecidas, críticas e cuidados recomendados"),
        ("Perspectivas", "tendências para os próximos anos segundo especialistas"),
        ("Estudo de caso", "um exemplo concreto de aplicação e os resultados obtidos"),
        ("Glossário", "os termos técnicos mais usados e o que significam"),
        ("Histórico", "a evolução do assunto desde as primeiras iniciativas"),
    ]
    itens = []
    for i, (rotulo, descricao) in enumerate(modelos[:quantidade], start=1):
        itens.append(
            (
                f"{rotulo}: {tema} (resultado simulado)",
                f"https://exemplo.org/{chave}/{rotulo.lower().replace(' ', '-')}",
                f"Conteúdo simulado com {descricao} sobre {tema}. Indicador de referência: {12 + i * 7}% ao ano.",
            )
        )
    return itens


def simular_wikipedia(termo: str, idioma: str) -> tuple[str, str, str]:
    return (
        f"{termo} (Wikipédia, simulado)",
        f"https://{idioma}.wikipedia.org/wiki/{quote(termo.replace(' ', '_'))}",
        f"Verbete simulado: {termo} é um assunto estudado desde o fim do século XX, com aplicações em educação, "
        f"indústria e serviços públicos. As primeiras referências acadêmicas datam de 1998.",
    )


def simular_pagina(url: str) -> tuple[str, str]:
    caminho = urlparse(url).path.strip("/").replace("-", " ").replace("/", ", ") or "página"
    texto = (
        f"Página simulada sobre {caminho}.\n"
        "Primeiro achado: a adoção cresceu de forma consistente nos últimos cinco anos.\n"
        "Segundo achado: equipes que medem resultados desde o início têm o dobro de chance de sucesso.\n"
        "Terceiro achado: os principais obstáculos são custo inicial, falta de capacitação e qualidade dos dados."
    )
    return f"Leitura simulada de {caminho}", texto
