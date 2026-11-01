from fastapi.testclient import TestClient

from apogeu.api import criar_app
from apogeu.config import Configuracao


def test_saude(cliente):
    dados = cliente.get("/api/saude").json()
    assert dados["provedor"]["nome"] == "demonstracao"
    assert dados["ferramentas"] == "simuladas"
    assert cliente.get("/api/saude").headers["x-content-type-options"] == "nosniff"


def test_agentes_editar_e_restaurar(cliente):
    agentes = cliente.get("/api/agentes").json()
    assert [a["chave"] for a in agentes] == ["supervisor", "pesquisador", "redator", "revisor"]
    novo = cliente.put(
        "/api/agentes/pesquisador",
        json={"prompt_sistema": "Você pesquisa apenas fontes oficiais e cita cada fato com [n].", "temperatura": 0.5, "ferramentas": ["buscar_web"]},
    )
    assert novo.status_code == 200
    assert novo.json()["personalizado"] is True and novo.json()["ferramentas"] == ["buscar_web"]
    invalido = cliente.put("/api/agentes/redator", json={"ferramentas": ["buscar_web"]})
    assert invalido.status_code == 422
    restaurado = cliente.post("/api/agentes/pesquisador/restaurar").json()
    assert restaurado["personalizado"] is False
    assert cliente.put("/api/agentes/nenhum", json={}).status_code == 404


def test_ferramentas_e_grafo(cliente):
    nomes = {f["nome"] for f in cliente.get("/api/ferramentas").json()}
    assert {"buscar_web", "ler_pagina", "verificar_citacoes"} <= nomes
    assert "supervisionar" in cliente.get("/api/grafo").json()["mermaid"]


def test_token_obrigatorio(tmp_path):
    cfg = Configuracao(data_dir=tmp_path, provedor="demonstracao", ferramentas="simuladas", token="segredo-local")
    with TestClient(criar_app(cfg, pasta_interface=None)) as c:
        assert c.get("/api/execucoes").status_code == 401
        assert c.get("/api/execucoes", headers={"Authorization": "Bearer segredo-local"}).status_code == 200
        assert c.get("/api/saude").status_code == 200
