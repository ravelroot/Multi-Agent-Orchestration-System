import asyncio

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from apogeu.config import Configuracao
from apogeu.contexto import Secao, compactar_resultados_antigos, montar_contexto, tokens_mensagens, truncar
from apogeu.ferramentas import ColetorFontes, Ferramentas, analisar_citacoes, analisar_texto, avaliar_expressao, validar_url
from apogeu.grafo import limpar_rascunho, permitidos


def test_calculadora_segura():
    assert avaliar_expressao("(1250 - 980) / 980 * 100") == pytest.approx(27.5510204)
    assert avaliar_expressao("2^10") == 1024
    for perigosa in ["__import__('os')", "open('x')", "9**9**9", "[1]*10"]:
        with pytest.raises((ValueError, SyntaxError)):
            avaliar_expressao(perigosa)


def test_bloqueio_de_enderecos_internos():
    assert validar_url("http://127.0.0.1/admin") is not None
    assert validar_url("http://localhost:8000") is not None
    assert validar_url("http://169.254.169.254/latest/meta-data") is not None
    assert validar_url("file:///etc/passwd") is not None
    assert validar_url("ftp://exemplo.org") is not None
    assert validar_url("https://usuario:senha@exemplo.org") is not None
    assert validar_url("https://exemplo.org/pagina", resolver=False) is None


def test_truncar_preserva_limite():
    texto = "linha\n" * 500
    cortado = truncar(texto, 300)
    assert len(cortado) < 360
    assert "omitidos" in cortado
    assert truncar("curto", 300) == "curto"


def test_montar_contexto_corta_secoes_de_menor_prioridade():
    secoes = [
        Secao("tarefa", "Tarefa importante", 100, False),
        Secao("notas", "fato relevante [1]\n" * 800, 40),
        Secao("plano", "Título: X\n" * 10, 80),
    ]
    texto, relatorio = montar_contexto(secoes, 1200)
    assert relatorio.compactado
    assert relatorio.secoes_cortadas == ["notas"]
    assert relatorio.tokens_depois <= 1300
    assert texto.index("<tarefa>") < texto.index("<plano>") < texto.index("<notas>")


def test_compactar_resultados_antigos_de_ferramentas():
    mensagens = [SystemMessage("s"), HumanMessage("h")]
    for i in range(5):
        mensagens.append(AIMessage("", tool_calls=[{"name": "buscar_web", "args": {}, "id": f"c{i}"}]))
        mensagens.append(ToolMessage("x" * 4000, tool_call_id=f"c{i}", name="buscar_web"))
    antes = tokens_mensagens(mensagens)
    resultado, compactadas = compactar_resultados_antigos(mensagens, 3000)
    assert compactadas >= 1
    assert tokens_mensagens(resultado) < antes
    assert [m.tool_call_id for m in resultado if isinstance(m, ToolMessage)] == [f"c{i}" for i in range(5)]
    assert len(resultado[-1].content) == 4000


def test_coletor_de_fontes_deduplica():
    coletor = ColetorFontes()
    a = coletor.registrar("A", "https://a.org/x")
    b = coletor.registrar("A de novo", "https://a.org/x/")
    c = coletor.registrar("C", "https://c.org")
    assert a.id == b.id == 1 and c.id == 2


def test_analise_de_texto_e_citacoes():
    texto = "# Título\n\nO sol é uma estrela [1]. Ele tem 4,6 bilhões de anos [3].\n\n" + "palavra " * 40
    dados = analisar_texto(texto)
    assert dados["palavras"] > 40 and 0 <= dados["legibilidade"] <= 100
    citacoes = analisar_citacoes(texto, {1, 2})
    assert citacoes["citacoes_invalidas"] == [3]
    assert citacoes["fontes_nao_citadas"] == [2]
    assert citacoes["paragrafos_sem_citacao"]


def test_ferramentas_simuladas_registram_fontes():
    cfg = Configuracao(ferramentas="simuladas")
    coletor = ColetorFontes()
    ferramentas = Ferramentas(cfg, coletor).todas()
    saida = asyncio.run(ferramentas["buscar_web"].ainvoke({"consulta": "energia solar", "max_resultados": 3}))
    assert "[1]" in saida and len(coletor.fontes) == 3
    wiki = asyncio.run(ferramentas["consultar_wikipedia"].ainvoke({"termo": "energia solar"}))
    assert "[4]" in wiki
    bloqueada = asyncio.run(ferramentas["ler_pagina"].ainvoke({"url": "file:///etc/passwd"}))
    assert "Não foi possível" in bloqueada


def test_guardrails_do_supervisor():
    cfg = Configuracao()
    assert permitidos({}, cfg)[1] == "pesquisador"
    com_notas = {"notas": ["fato [1]"], "pesquisas": 1, "versao": 0}
    opcoes, canonico, _ = permitidos(com_notas, cfg)
    assert canonico == "redator" and "pesquisador" in opcoes
    sem_revisao = {**com_notas, "versao": 1, "revisoes": []}
    assert permitidos(sem_revisao, cfg)[0] == {"revisor"}
    reprovado = {**sem_revisao, "revisoes": [{"versao": 1, "aprovado": False, "nota": 6}], "max_revisoes": 2}
    assert permitidos(reprovado, cfg)[1] == "redator"
    esgotado = {**reprovado, "max_revisoes": 0}
    assert permitidos(esgotado, cfg)[0] == {"finalizar"}
    aprovado = {**sem_revisao, "revisoes": [{"versao": 1, "aprovado": True, "nota": 9}]}
    assert permitidos(aprovado, cfg)[0] == {"finalizar"}


def test_limpar_rascunho_remove_cercas_e_referencias():
    bruto = "```markdown\n# Título\n\nTexto [1].\n\n## Referências\n\n1. Fonte\n```"
    assert limpar_rascunho(bruto) == "# Título\n\nTexto [1]."
