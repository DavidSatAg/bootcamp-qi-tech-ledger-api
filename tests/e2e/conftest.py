"""O ponto de integração (remodelagem 08): o Ledger contra o Cadastro de
verdade, não contra o party-mock.

Nada aqui roda num `pytest` comum, que é a suíte contra os mocks. Para rodar:

    # o Ledger apontando para o Cadastro de verdade (01b §0.2)
    PARTY_API_URL=http://host.docker.internal:3001 PARTY_API_TIMEOUT=3 docker compose up -d

    E2E=1 PARTY_API_URL=http://host.docker.internal:3001 API_PORT=3003 SERVER_LOCALHOST=localhost \\
        pytest tests/e2e

O que é marcado `destrutivo` derruba um serviço de pé: só roda com
E2E_DESTRUTIVO=1 a mais, e sozinho (ver tests/e2e/test_party_api_down.py).
"""
from os import environ
from pathlib import Path

import pytest

from tests.utils.party_scenarios import seed_party_scenarios

E2E_DIR = Path(__file__).resolve().parent


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "destrutivo: derruba um serviço de pé; só roda com E2E_DESTRUTIVO=1, isolado do resto da bateria",
    )


def pytest_collection_modifyitems(config, items):
    skip_e2e = pytest.mark.skip(reason="ponto de integração: rode com E2E=1, contra o Cadastro de verdade")
    skip_destructive = pytest.mark.skip(reason="destrutivo: rode com E2E_DESTRUTIVO=1, isolado")

    for item in items:
        if E2E_DIR not in item.path.parents:
            continue

        if environ.get("E2E") != "1":
            item.add_marker(skip_e2e)
        elif "destrutivo" in item.keywords and environ.get("E2E_DESTRUTIVO") != "1":
            item.add_marker(skip_destructive)


@pytest.fixture(scope="session")
def party_scenarios() -> dict:
    """{papel: party_key real} para a sessão inteira: a semeadura roda uma
    vez por `pytest`. Os documentos são fixos (PAR-12): a primeira execução
    cria as partes, e as seguintes recuperam as mesmas chaves."""
    return seed_party_scenarios()
