from tests.conftest import ler_eventos

TAREFA = "Escreva um artigo sobre energia solar em residências brasileiras"


def criar(cliente, **extra):
    corpo = {"tarefa": TAREFA, "briefing": {"palavras": 400}, **extra}
    resposta = cliente.post("/api/execucoes", json=corpo)
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


def tipos(eventos):
    return [e["tipo"] for e in eventos]


def test_fluxo_completo_com_rodada_de_revisao(cliente):
    execucao = criar(cliente)
    eventos = ler_eventos(cliente, execucao["id"])
    sequencia = tipos(eventos)
    assert sequencia[0] == "execucao.criada"
    assert sequencia[-1] == "execucao.concluida"
    assert "plano.criado" in sequencia
    assert sequencia.count("rascunho.atualizado") == 2
    revisoes = [e["dados"] for e in eventos if e["tipo"] == "revisao.concluida"]
    assert [r["aprovado"] for r in revisoes] == [False, True]
    chamadas = [e["dados"]["ferramenta"] for e in eventos if e["tipo"] == "ferramenta.chamada"]
    assert {"buscar_web", "consultar_wikipedia", "ler_pagina", "metricas_do_rascunho", "verificar_citacoes"} <= set(chamadas)
    decisoes = [e["dados"]["proximo"] for e in eventos if e["tipo"] == "supervisor.decisao"]
    assert decisoes == ["pesquisador", "redator", "revisor", "redator", "revisor", "finalizar"]
    assert any(e["tipo"] == "contexto.uso" for e in eventos)
    assert any(e["tipo"] == "rascunho.delta" and e["seq"] is None for e in eventos)
    seqs = [e["seq"] for e in eventos if e["seq"] is not None]
    assert seqs == sorted(seqs) and len(seqs) == len(set(seqs))

    final = cliente.get(f"/api/execucoes/{execucao['id']}").json()
    assert final["status"] == "concluida"
    assert "## Fontes" in final["resultado"]
    assert final["metricas"]["aprovado"] is True
    assert final["metricas"]["versoes"] == 2
    assert final["metricas"]["fontes_citadas"] > 0
    assert set(final["metricas"]["uso_por_agente"]) >= {"supervisor", "pesquisador", "redator", "revisor"}


def test_sem_rodadas_de_revisao_finaliza_apos_primeira_revisao(cliente):
    execucao = criar(cliente, max_revisoes=0)
    eventos = ler_eventos(cliente, execucao["id"])
    assert tipos(eventos).count("rascunho.atualizado") == 1
    final = cliente.get(f"/api/execucoes/{execucao['id']}").json()
    assert final["status"] == "concluida"
    assert final["metricas"]["aprovado"] is False


def test_aprovacao_do_plano_com_edicao(cliente):
    execucao = criar(cliente, aprovar_plano=True)
    eventos = ler_eventos(cliente, execucao["id"])
    assert tipos(eventos)[-1] == "plano.aguardando"
    assert cliente.get(f"/api/execucoes/{execucao['id']}").json()["status"] == "aguardando_aprovacao"
    plano = eventos[-1]["dados"]["plano"]
    plano["titulo"] = "Energia solar em casa"
    resposta = cliente.post(
        f"/api/execucoes/{execucao['id']}/aprovacao",
        json={"aprovado": True, "plano": plano, "comentario": "Foque em custos e retorno do investimento."},
    )
    assert resposta.status_code == 200, resposta.text
    depois = ler_eventos(cliente, execucao["id"])
    aprovado = next(e for e in depois if e["tipo"] == "plano.aprovado")
    assert aprovado["dados"]["editado"] is True
    assert tipos(depois)[-1] == "execucao.concluida"
    final = cliente.get(f"/api/execucoes/{execucao['id']}").json()
    assert final["resultado"].startswith("# Energia solar em casa")


def test_recusar_plano(cliente):
    execucao = criar(cliente, aprovar_plano=True)
    ler_eventos(cliente, execucao["id"])
    resposta = cliente.post(f"/api/execucoes/{execucao['id']}/aprovacao", json={"aprovado": False, "comentario": "Outro tema."})
    assert resposta.status_code == 200
    eventos = ler_eventos(cliente, execucao["id"])
    assert tipos(eventos)[-1] == "plano.recusado"
    assert cliente.get(f"/api/execucoes/{execucao['id']}").json()["status"] == "recusada"


def test_aprovacao_fora_de_hora(cliente):
    execucao = criar(cliente)
    ler_eventos(cliente, execucao["id"])
    resposta = cliente.post(f"/api/execucoes/{execucao['id']}/aprovacao", json={"aprovado": True})
    assert resposta.status_code == 409


def test_cancelar_enquanto_aguarda_plano(cliente):
    execucao = criar(cliente, aprovar_plano=True)
    ler_eventos(cliente, execucao["id"])
    resposta = cliente.post(f"/api/execucoes/{execucao['id']}/cancelar")
    assert resposta.status_code == 200
    assert resposta.json()["status"] == "cancelada"


def test_exportar_e_excluir(cliente):
    execucao = criar(cliente)
    ler_eventos(cliente, execucao["id"])
    md = cliente.get(f"/api/execucoes/{execucao['id']}/exportar?formato=markdown")
    assert md.status_code == 200 and md.text.startswith("# ")
    js = cliente.get(f"/api/execucoes/{execucao['id']}/exportar?formato=json")
    assert js.status_code == 200 and js.json()["eventos"]
    assert cliente.get("/api/execucoes").json()[0]["id"] == execucao["id"]
    assert cliente.delete(f"/api/execucoes/{execucao['id']}").status_code == 204
    assert cliente.get(f"/api/execucoes/{execucao['id']}").status_code == 404


def test_validacao_da_tarefa(cliente):
    assert cliente.post("/api/execucoes", json={"tarefa": "curta"}).status_code == 422
    assert cliente.post("/api/execucoes", json={"tarefa": TAREFA, "briefing": {"palavras": 50}}).status_code == 422
