import json

import pytest
from fastapi.testclient import TestClient

from apogeu.api import criar_app
from apogeu.config import Configuracao


@pytest.fixture
def cfg(tmp_path):
    return Configuracao(
        data_dir=tmp_path,
        provedor="demonstracao",
        ferramentas="simuladas",
        atraso_demonstracao=0,
        token="",
    )


@pytest.fixture
def cliente(cfg):
    with TestClient(criar_app(cfg, pasta_interface=None)) as c:
        yield c


def ler_eventos(cliente, execucao_id: str) -> list[dict]:
    eventos = []
    with cliente.stream("GET", f"/api/execucoes/{execucao_id}/eventos") as resposta:
        assert resposta.status_code == 200
        for linha in resposta.iter_lines():
            if linha.startswith("data: ") and linha != "data: {}":
                eventos.append(json.loads(linha[6:]))
    return eventos


@pytest.fixture
def eventos():
    return ler_eventos
