from os import environ
from urllib.parse import urlparse
from uuid import uuid4

import requests

from tests.utils.random_generator import RandomGenerator


# Os papéis que o roteiro do ponto de integração usa no lugar das chaves
# mágicas do party-mock (guia 00 §2). A chave mágica substituída está ao lado.
APROVADA = "aprovada"  # 2222…: active, com pix_key qualquer
PENDENTE = "pendente"  # aaaa…: status pending
SEM_PIX = "sem_pix"  # dddd…: active, pix_key null
PIX_TIMEOUT = "pix_timeout"  # eeee…: active, pix_key "timeout@mock"
PIX_ERRO = "pix_erro"  # ffff…: active, pix_key "erro@mock"

PARTY_API_OFFLINE = (
    "Não consegui falar com o Cadastro em {base_url}.\n"
    "No ponto de integração ele precisa estar de pé. Suba com, de dentro de bootcampparty/:  docker compose up"
)

PARTY_API_IS_MOCK = (
    "PARTY_API_URL aponta para o party-mock ({party_api_url}). O ponto de integração roda contra o Cadastro "
    "de verdade: PARTY_API_URL=http://host.docker.internal:3001 (01b §0.2)."
)


def party_api_base_url() -> str:
    """Onde o Cadastro de verdade atende, visto da máquina que roda o pytest.

    Lê a mesma PARTY_API_URL que o container do Ledger usa (01b §0.2). Lá
    dentro o Cadastro atende por `host.docker.internal`; aqui fora, pela
    mesma porta em `localhost`. Sem a variável, vale a porta do 01b: 3001.
    """
    party_api_url = environ.get("PARTY_API_URL", "http://localhost:3001")
    parsed = urlparse(party_api_url)

    if parsed.hostname == "party-mock":
        raise RuntimeError(PARTY_API_IS_MOCK.format(party_api_url=party_api_url))

    if parsed.hostname == "host.docker.internal":
        parsed = parsed._replace(netloc=f"localhost:{parsed.port}")

    return parsed.geturl().rstrip("/")


def send_to_party_api(method: str, endpoint: str, payload: dict = None) -> tuple:
    """Uma chamada ao Cadastro de verdade, com o token DELE (01b §0.1).

    Vai direto pelo `requests`, como o `GET_mock_requests`: o
    `ClientRequisition` só monta a URL da API do Ledger.
    """
    base_url = party_api_base_url()
    headers = {
        "INTERNAL-TOKEN": environ.get("PARTY_API_INTERNAL_TOKEN", "default_token"),
        "X-Request-ID": f"e2e-{uuid4()}",
    }

    try:
        response = requests.request(method, f"{base_url}{endpoint}", json=payload, headers=headers, timeout=10)
    except requests.exceptions.ConnectionError:
        raise RuntimeError(PARTY_API_OFFLINE.format(base_url=base_url)) from None

    return response.status_code, response.json()


def POST_party(payload: dict) -> tuple:
    return send_to_party_api("POST", "/parties", payload)


def GET_party(party_key: str) -> tuple:
    return send_to_party_api("GET", f"/parties/{party_key}")


def create_party_payload(document_number: str, pix_key: str = None) -> dict:
    """O corpo do `POST /parties`, no formato exato que o Cadastro aceita
    (bootcampparty, PayloadGenerator.create_party_payload). Sem `pix_key`, a
    chave não vai no corpo, em vez de ir como null."""
    payload = {
        "name": "Parte do ponto de integração",
        "document_number": document_number,
        "actor": "ledger-e2e",
    }

    if pix_key is not None:
        payload["pix_key"] = pix_key

    return payload


# papel -> (final do documento, pix_key no corpo, status esperado no 201)
SCENARIOS = {
    APROVADA: (None, "ledger.e2e@example.com", "active"),
    PENDENTE: ("99", "ledger.e2e@example.com", "pending"),
    SEM_PIX: (None, None, "active"),
    PIX_TIMEOUT: (None, "timeout@mock", "active"),
    PIX_ERRO: (None, "erro@mock", "active"),
}


def seed_party_scenarios() -> dict:
    """Recria no Cadastro de verdade cada situação que uma chave mágica do
    party-mock representava, e devolve {papel: party_key real}.

    ATENÇÃO — cada chamada cria pessoas NOVAS. Os documentos são sorteados
    a cada chamada (a UNIQUE do Cadastro não deixa repetir), então cada
    rodada deixa cinco partes a mais no banco do Cadastro. Não é
    idempotente por reaproveitamento: não procura nem reusa partes de
    execuções anteriores, de propósito. Uma parte reaproveitada pode ter
    mudado de estado desde a última rodada (a pendente pode ter sido
    repescada), e o roteiro passaria a depender de um histórico que um
    clone do zero não tem.

    O "pendente" depende do bureau mockado do Cadastro: documento final 99
    fica fora do ar, e a parte nasce pending (01b §6, guia 00 §2). O
    `201` do Cadastro já traz o status depois do bureau, por isso cada
    papel é conferido aqui mesmo: se o ambiente não reproduz o cenário, o
    erro aparece na preparação, e não no meio do roteiro.

    O caso `cccc…` (Cadastro fora do ar) NÃO está aqui: ele é simulado
    parando o container, em tests/e2e/test_party_api_down.py.
    """
    party_keys = {}

    for role, (ending, pix_key, expected_status) in SCENARIOS.items():
        payload = create_party_payload(RandomGenerator.generate_cpf_digits(ending=ending), pix_key)

        status, response = POST_party(payload)

        assert status == 201, (role, response)
        assert response["status"] == expected_status, (role, response)

        party_keys[role] = response["party_key"]

    return party_keys
