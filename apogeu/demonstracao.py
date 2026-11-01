import asyncio
import re
import time
import uuid
from typing import Any, AsyncIterator, Iterator

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_core.runnables import RunnableLambda

from .contexto import texto_da_resposta, tokens_mensagens, tokens_texto
from .esquemas import Decisao, Etapa, Plano, Revisao


def secoes(texto: str) -> dict[str, str]:
    return {m.group(1): m.group(2).strip() for m in re.finditer(r"<(\w+)>\n(.*?)\n</\1>", texto, flags=re.S)}


def conteudo_humano(mensagens: list[BaseMessage]) -> str:
    return "\n\n".join(texto_da_resposta(m.content) for m in mensagens if isinstance(m, HumanMessage))


def estado(texto: str) -> dict[str, str]:
    linhas = secoes(texto).get("estado", "")
    return {a.strip(): b.strip() for a, b in (l.split(":", 1) for l in linhas.splitlines() if ":" in l)}


def tema_da_tarefa(tarefa: str) -> str:
    primeira = re.split(r"(?<=[.!?])\s|\n", tarefa.strip())[0]
    primeira = re.sub(
        r"^(escreva|crie|produza|faça|elabore|redija|prepare|gere|monte)\s+(um|uma|o|a)?\s*"
        r"(artigo|texto|post|relatório|resumo|matéria)?\s*(de blog|técnico|executivo)?\s*(sobre|a respeito de|acerca de|explicando)?\s*",
        "",
        primeira,
        flags=re.I,
    )
    return primeira.strip(" .:") or tarefa.strip()[:60]


def titulo(tema: str) -> str:
    tema = tema[:90].rstrip(" ,;")
    return tema[:1].upper() + tema[1:]


def fatos(notas: str) -> list[tuple[str, str]]:
    achados = []
    for linha in notas.splitlines():
        linha = linha.strip(" -•\t")
        m = re.search(r"(.+?)\s*\[(\d+)\]\.?$", linha)
        if m and len(m.group(1)) > 20:
            achados.append((m.group(1).rstrip(". "), m.group(2)))
    return achados


class ModeloDemonstracao(BaseChatModel):
    papel: str = "geral"
    atraso: float = 0.02
    ferramentas: list[str] = []

    @property
    def _llm_type(self) -> str:
        return "demonstracao"

    def bind_tools(self, tools, **kwargs: Any):
        nomes = [getattr(t, "name", None) or t.get("name") for t in tools]
        return self.model_copy(update={"ferramentas": nomes})

    def with_structured_output(self, schema, **kwargs: Any):
        return RunnableLambda(lambda entrada: self._estruturar(schema, entrada))

    def _mensagens(self, entrada) -> list[BaseMessage]:
        if isinstance(entrada, list):
            return entrada
        if hasattr(entrada, "to_messages"):
            return entrada.to_messages()
        return [HumanMessage(content=str(entrada))]

    def _estruturar(self, schema, entrada):
        texto = conteudo_humano(self._mensagens(entrada))
        if schema is Plano:
            return self._plano(texto)
        if schema is Decisao:
            return self._decisao(texto)
        if schema is Revisao:
            return self._revisao(texto)
        raise ValueError(f"Esquema não suportado no modo demonstração: {schema}")

    def _plano(self, texto: str) -> Plano:
        tarefa = secoes(texto).get("tarefa", texto)
        tema = tema_da_tarefa(tarefa)
        return Plano(
            titulo=titulo(tema),
            abordagem=f"Explicar {tema} do básico ao prático: contexto, dados, aplicações e cuidados, com fontes em cada afirmação.",
            perguntas=[
                f"O que é {tema} e de onde surgiu?",
                f"Quais dados recentes mostram a relevância de {tema}?",
                f"Como {tema} é aplicado na prática?",
                f"Quais riscos e limites de {tema} o leitor precisa conhecer?",
            ],
            etapas=[
                Etapa(agente="pesquisador", objetivo="Reunir fatos e números com fontes para cada pergunta."),
                Etapa(agente="redator", objetivo="Escrever o texto completo no tom e no tamanho pedidos."),
                Etapa(agente="revisor", objetivo="Medir o rascunho, conferir citações e apontar correções."),
            ],
        )

    def _decisao(self, texto: str) -> Decisao:
        e = estado(texto)
        notas = int(e.get("notas", "0") or 0)
        versao = int(e.get("versao_rascunho", "0") or 0)
        revisada = int(e.get("versao_revisada", "0") or 0)
        aprovada = e.get("ultima_revisao", "") == "aprovada"
        if notas == 0:
            return Decisao(proximo="pesquisador", instrucao="Pesquise as perguntas do plano e traga fatos com fontes numeradas.", motivo="Ainda não há notas de pesquisa.")
        if versao == 0:
            return Decisao(proximo="redator", instrucao="Escreva o texto completo seguindo o plano e citando as fontes.", motivo="As notas já cobrem o plano.")
        if revisada < versao:
            return Decisao(proximo="revisor", instrucao=f"Revise a versão {versao}: briefing, citações, estrutura e legibilidade.", motivo="Há uma versão que ainda não foi revisada.")
        if aprovada:
            return Decisao(proximo="finalizar", instrucao="Publicar a versão aprovada.", motivo="A revisão aprovou o texto.")
        return Decisao(proximo="redator", instrucao="Reescreva aplicando todas as sugestões da última revisão.", motivo="A revisão pediu correções.")

    def _revisao(self, texto: str) -> Revisao:
        m = re.search(r"versão (\d+)", texto)
        versao = int(m.group(1)) if m else 1
        if versao <= 1:
            return Revisao(
                nota=7.1,
                aprovado=False,
                pontos_fortes=["Estrutura clara, com introdução, desenvolvimento e conclusão.", "Afirmações factuais acompanhadas de citação."],
                problemas=["Faltam exemplos práticos para o público pedido.", "Algumas fontes da pesquisa não foram aproveitadas."],
                sugestoes=["Inclua uma seção com aplicações práticas e um exemplo concreto.", "Use as fontes ainda não citadas para sustentar os dados."],
            )
        return Revisao(
            nota=8.8,
            aprovado=True,
            pontos_fortes=["Exemplos práticos bem escolhidos.", "Todas as fontes relevantes citadas.", "Leitura fluida."],
            problemas=[],
            sugestoes=[],
        )

    def _uso(self, mensagens: list[BaseMessage], saida: str) -> dict:
        entrada = tokens_mensagens(mensagens)
        gerados = tokens_texto(saida)
        return {"input_tokens": entrada, "output_tokens": gerados, "total_tokens": entrada + gerados}

    def _chamada(self, nome: str, args: dict) -> dict:
        return {"name": nome, "args": args, "id": f"call_{uuid.uuid4().hex[:12]}", "type": "tool_call"}

    def _resposta(self, mensagens: list[BaseMessage]) -> AIMessage:
        texto = conteudo_humano(mensagens)
        ferramentas_usadas = [m for m in mensagens if isinstance(m, ToolMessage)]
        if self.papel == "pesquisador":
            return self._pesquisar(mensagens, texto, ferramentas_usadas)
        if self.papel == "revisor":
            return self._revisar(mensagens, ferramentas_usadas)
        if self.papel == "compactador":
            linhas = [l for l in texto.splitlines() if re.search(r"\[\d+\]", l)]
            saida = "\n".join(linhas[:12])
            return AIMessage(content=saida, usage_metadata=self._uso(mensagens, saida))
        if self.papel == "redator":
            saida = self._escrever(texto)
            return AIMessage(content=saida, usage_metadata=self._uso(mensagens, saida))
        saida = "Pronto."
        return AIMessage(content=saida, usage_metadata=self._uso(mensagens, saida))

    def _pesquisar(self, mensagens, texto, usadas) -> AIMessage:
        tema = tema_da_tarefa(secoes(texto).get("tarefa", texto))
        if not usadas:
            chamadas = []
            if "buscar_web" in self.ferramentas:
                chamadas.append(self._chamada("buscar_web", {"consulta": tema, "max_resultados": 4}))
            if "consultar_wikipedia" in self.ferramentas:
                chamadas.append(self._chamada("consultar_wikipedia", {"termo": tema, "idioma": "pt"}))
            if chamadas:
                return AIMessage(content="", tool_calls=chamadas, usage_metadata=self._uso(mensagens, str(chamadas)))
        leu = any(m.name == "ler_pagina" for m in usadas)
        urls = re.findall(r"https?://\S+", "\n".join(str(m.content) for m in usadas))
        if not leu and urls and "ler_pagina" in self.ferramentas:
            chamada = self._chamada("ler_pagina", {"url": urls[0]})
            return AIMessage(content="", tool_calls=[chamada], usage_metadata=self._uso(mensagens, str(chamada)))
        notas = []
        for m in usadas:
            for bloco in re.split(r"\n\s*\n", str(m.content)):
                cab = re.match(r"\[(\d+)\]\s*(.+)", bloco.strip())
                if not cab:
                    continue
                linhas = [l for l in bloco.strip().splitlines()[2:] if l.strip()]
                for linha in linhas[:3]:
                    frase = linha.strip().rstrip(".")
                    if len(frase) > 25:
                        notas.append(f"- {frase} [{cab.group(1)}].")
        notas.append("Lacunas: os números são indicativos e devem ser confirmados em fontes primárias.")
        saida = "\n".join(notas)
        return AIMessage(content=saida, usage_metadata=self._uso(mensagens, saida))

    def _revisar(self, mensagens, usadas) -> AIMessage:
        if not usadas:
            chamadas = [self._chamada(n, {}) for n in ("metricas_do_rascunho", "verificar_citacoes") if n in self.ferramentas]
            if chamadas:
                return AIMessage(content="", tool_calls=chamadas, usage_metadata=self._uso(mensagens, str(chamadas)))
        resultados = "\n".join(str(m.content) for m in usadas)
        saida = (
            "Análise do rascunho com base nas ferramentas:\n"
            f"{resultados}\n\n"
            "Avaliação: o texto está bem estruturado e cita as fontes. "
            "Verifiquei se há exemplos práticos suficientes e se todas as fontes úteis foram aproveitadas."
        )
        return AIMessage(content=saida, usage_metadata=self._uso(mensagens, saida))

    def _escrever(self, texto: str) -> str:
        partes = secoes(texto)
        plano = partes.get("plano", "")
        m = re.search(r"Título:\s*(.+)", plano)
        tema = tema_da_tarefa(partes.get("tarefa", "o tema"))
        cabecalho = m.group(1).strip() if m else titulo(tema)
        lista = fatos(partes.get("notas", ""))
        if not lista:
            lista = [(f"Há pouca informação verificada sobre {tema}", "1")]
        corrigir = "revisao" in partes
        blocos = [f"# {cabecalho}", ""]
        f0 = lista[0]
        blocos.append(
            f"{titulo(tema)} deixou de ser assunto de especialistas e passou a fazer parte das decisões do dia a dia. "
            f"Para entender por quê, vale começar pelo básico: {f0[0].lower()} [{f0[1]}]."
        )
        blocos += ["", "## O que está em jogo", ""]
        for texto_fato, n in lista[1:3]:
            blocos.append(f"{texto_fato} [{n}]. Esse dado ajuda a dimensionar o tema e mostra por que ele merece atenção.")
            blocos.append("")
        blocos += ["## Riscos e cuidados", ""]
        for texto_fato, n in lista[3:5] or lista[:1]:
            blocos.append(f"Nem tudo são vantagens: {texto_fato[0].lower() + texto_fato[1:]} [{n}].")
            blocos.append("")
        if corrigir:
            blocos += ["## Na prática", ""]
            usados = {n for _, n in lista[:5]}
            extras = [(t, n) for t, n in lista if n not in usados] or lista[-2:]
            blocos.append(
                "Um exemplo ajuda a tirar a ideia do papel. Imagine uma equipe pequena que decide adotar o tema em um projeto piloto "
                "de três meses, com metas medidas desde a primeira semana."
            )
            blocos.append("")
            for texto_fato, n in extras[:3]:
                blocos.append(f"- {texto_fato} [{n}].")
            blocos.append("")
        blocos += ["## Conclusão", ""]
        ultimo = lista[-1]
        blocos.append(
            f"O caminho mais seguro é começar pequeno, medir resultados e ajustar. {ultimo[0]} [{ultimo[1]}], "
            "e quem acompanha esses sinais com atenção toma decisões melhores."
        )
        return "\n".join(blocos).strip()

    def _generate(self, messages: list[BaseMessage], stop=None, run_manager=None, **kwargs: Any) -> ChatResult:
        time.sleep(self.atraso * 5)
        return ChatResult(generations=[ChatGeneration(message=self._resposta(messages))])

    async def _agenerate(self, messages: list[BaseMessage], stop=None, run_manager=None, **kwargs: Any) -> ChatResult:
        await asyncio.sleep(self.atraso * 5)
        return ChatResult(generations=[ChatGeneration(message=self._resposta(messages))])

    def _pedacos(self, mensagem: AIMessage) -> list[str]:
        return re.findall(r"\S+\s*|\s+", texto_da_resposta(mensagem.content))

    def _stream(self, messages: list[BaseMessage], stop=None, run_manager=None, **kwargs: Any) -> Iterator[ChatGenerationChunk]:
        mensagem = self._resposta(messages)
        if mensagem.tool_calls:
            yield ChatGenerationChunk(message=AIMessageChunk(content="", tool_calls=mensagem.tool_calls))
            return
        for pedaco in self._pedacos(mensagem):
            time.sleep(self.atraso)
            yield ChatGenerationChunk(message=AIMessageChunk(content=pedaco))
        yield ChatGenerationChunk(message=AIMessageChunk(content="", usage_metadata=mensagem.usage_metadata))

    async def _astream(self, messages: list[BaseMessage], stop=None, run_manager=None, **kwargs: Any) -> AsyncIterator[ChatGenerationChunk]:
        mensagem = self._resposta(messages)
        if mensagem.tool_calls:
            yield ChatGenerationChunk(message=AIMessageChunk(content="", tool_calls=mensagem.tool_calls))
            return
        for pedaco in self._pedacos(mensagem):
            await asyncio.sleep(self.atraso)
            yield ChatGenerationChunk(message=AIMessageChunk(content=pedaco))
        yield ChatGenerationChunk(message=AIMessageChunk(content="", usage_metadata=mensagem.usage_metadata))
