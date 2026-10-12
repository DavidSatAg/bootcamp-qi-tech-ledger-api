"""O caso `cccc…` do party-mock (Cadastro fora do ar), refeito contra o
Cadastro de verdade: o container da API dele é parado de fato.

NÃO RODE ESTE ARQUIVO JUNTO COM OUTROS TESTES QUE PRECISAM DO CADASTRO DE
PÉ. Durante o teste, o party-api fica fora do ar para TODO MUNDO: qualquer
outro teste rodando ao mesmo tempo (outro pytest, outro terminal, o roteiro
do Contrato) recebe conexão recusada e falha por um motivo que não é dele.
Por isso ele é `destrutivo`, só roda com E2E_DESTRUTIVO=1, e sozinho:

    E2E=1 E2E_DESTRUTIVO=1 PARTY_API_URL=http://host.docker.internal:3001 \\
        API_PORT=3003 SERVER_LOCALHOST=localhost \\
        pytest tests/e2e/test_party_api_down.py

O container volta a subir no `finally` do `party_api_stopped`, falhe a
asserção ou não, e o teste só termina quando o Cadastro responde de novo.
"""
import subprocess
import time
from contextlib import contextmanager
from os import environ
from pathlib import Path

import pytest
import requests

from tests.utils.party_scenarios import APROVADA, SEM_PIX, GET_party, party_api_base_url
from tests.utils.request_generator import RequestGenerator

# O compose do Cadastro, ao lado deste repositório (os três clonados na mesma
# pasta). PARTY_COMPOSE_DIR troca, se o clone estiver em outro lugar.
PARTY_COMPOSE_DIR = Path(environ.get("PARTY_COMPOSE_DIR", Path(__file__).resolve().parents[3] / "bootcampparty"))
PARTY_API_SERVICE = "api"
PARTY_API_STARTUP_TIMEOUT = 60


def docker_compose(*args):
    subprocess.run(["docker", "compose", *args], cwd=PARTY_COMPOSE_DIR, check=True, capture_output=True, text=True)


def wait_party_api_healthy():
    """Espera o `/health_check` do Cadastro responder 2xx (ele devolve 204):
    o container "subiu" antes de a API atender."""
    deadline = time.monotonic() + PARTY_API_STARTUP_TIMEOUT
    while time.monotonic() < deadline:
        try:
            if requests.get(f"{party_api_base_url()}/health_check", timeout=2).ok:
                return
        except requests.exceptions.ConnectionError:
            pass
        time.sleep(1)

    raise RuntimeError(f"o Cadastro não voltou em {PARTY_API_STARTUP_TIMEOUT}s; suba à mão em {PARTY_COMPOSE_DIR}")


@contextmanager
def party_api_stopped():
    """Para o container da API do Cadastro pelo tempo do `with`, e o sobe de
    volta SEMPRE na saída — com a asserção falhando, com exceção, com o
    `stop` dando erro no meio."""
    try:
        docker_compose("stop", PARTY_API_SERVICE)
        yield
    finally:
        docker_compose("start", PARTY_API_SERVICE)
        wait_party_api_healthy()


@pytest.mark.destrutivo
class TestPartyApiDown:
    def test_wallets_503_while_party_api_is_down(self, party_scenarios):
        """01b §0.5 e §1: Cadastro fora do ar numa leitura é `503 QIT001040`,
        e nada é gravado. Com o Cadastro de volta, a mesma parte abre a
        carteira com 201 — nasce agora, prova de que a falha não deixou nada
        para trás."""
        # Antes de derrubar: o Ledger fala com o Cadastro de verdade. Contra o
        # party-mock, esta parte daria 409 (o mock não a conhece), e o 503 de
        # baixo não provaria nada.
        status, response = RequestGenerator.POST_wallets({"party_key": party_scenarios[APROVADA], "actor": "ledger-e2e"})
        assert status == 201, response

        party_key = party_scenarios[SEM_PIX]

        with party_api_stopped():
            status, response = RequestGenerator.POST_wallets({"party_key": party_key, "actor": "ledger-e2e"})

            assert status == 503, response
            assert response["code"] == "QIT001040", response

            status, accounts = RequestGenerator.GET_ledger_accounts({"owner_party_key": party_key, "limit": "100"})
            assert status == 200, accounts
            assert accounts["data"] == [], accounts

        status, response = GET_party(party_key)
        assert status == 200, response
        assert response["status"] == "active", response

        status, response = RequestGenerator.POST_wallets({"party_key": party_key, "actor": "ledger-e2e"})
        assert status == 201, response
