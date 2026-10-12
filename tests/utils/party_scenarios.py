from os import environ
from urllib.parse import urlparse
from uuid import uuid4

import requests


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


def GET_parties_by_document(document_number: str) -> tuple:
    """`GET /parties?document_number=` do Cadastro (party-api 07):
    `200 {"data": [{"party_key", "status"}]}`, com zero ou um item."""
    return send_to_party_api("GET", f"/parties?document_number={document_number}")


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

# papel -> documento fixo (PAR-12). CPFs válidos, só dígitos, com o prefixo
# 523000 para não esbarrar nos documentos sorteados por outros testes. O
# final decide o bureau mockado do Cadastro (guia 00 §2): os quatro
# primeiros fogem dos finais reservados (00, 97, 98, 99); o da pendente
# termina em 99 (bureau fora do ar, a parte nasce pending). É o `ending`
# de SCENARIOS, fixado.
DOCUMENTS = {
    APROVADA: "52300000075",
    PENDENTE: "52300018799",
    SEM_PIX: "52300000156",
    PIX_TIMEOUT: "52300000237",
    PIX_ERRO: "52300000318",
}

PARTY_DOCUMENT_TAKEN = "QIT002003"

SEEDED_PARTY_CHANGED = (
    "A parte do papel {role} (documento {document_number}) já existia no Cadastro, mas não está como o "
    "cenário pede: esperava status {expected_status!r} e pix_key {pix_key!r}, veio {response}. "
    "Alguém mudou a parte ou cadastrou o documento com outros dados."
)


def recover_party_by_document(role: str, document_number: str) -> str:
    """A `party_key` de uma parte que já existe, pela busca por documento
    (party-api 07), conferida pelo `GET /parties/{chave}` contra o cenário:
    status e pix_key iguais aos da criação."""
    _ending, pix_key, expected_status = SCENARIOS[role]

    status, response = GET_parties_by_document(document_number)
    assert status == 200, (role, response)
    assert len(response["data"]) == 1, (role, response)
    party_key = response["data"][0]["party_key"]

    status, response = GET_party(party_key)
    assert status == 200, (role, response)
    if response["status"] != expected_status or response["pix_key"] != pix_key:
        raise RuntimeError(
            SEEDED_PARTY_CHANGED.format(
                role=role,
                document_number=document_number,
                expected_status=expected_status,
                pix_key=pix_key,
                response=response,
            )
        )

    return party_key


def seed_party_scenarios() -> dict:
    """Recria no Cadastro de verdade cada situação que uma chave mágica do
    party-mock representava, e devolve {papel: party_key real}.

    Idempotente (PAR-12): cada papel tem um documento FIXO (DOCUMENTS).
    Na primeira vez, o `POST /parties` cria a parte (`201`). Nas seguintes,
    a UNIQUE do Cadastro recusa o mesmo documento com `409 QIT002003`, e a
    chave é recuperada pela busca por documento (`GET
    /parties?document_number=`, party-api 07). Rodar duas vezes devolve as
    mesmas chaves, e o banco do Cadastro não ganha cinco partes por rodada.

    A parte recuperada é conferida contra o cenário (status e pix_key): se
    alguém a mudou desde a criação, o erro aparece aqui, na preparação, e
    não no meio do roteiro. O mesmo vale para o `201`: o status que ele
    traz já é o de depois do bureau.

    O "pendente" depende do bureau mockado do Cadastro: documento final 99
    fica fora do ar, e a parte nasce pending (01b §6, guia 00 §2).

    O caso `cccc…` (Cadastro fora do ar) NÃO está aqui: ele é simulado
    parando o container, em tests/e2e/test_party_api_down.py.
    """
    party_keys = {}

    for role, (_ending, pix_key, expected_status) in SCENARIOS.items():
        document_number = DOCUMENTS[role]
        status, response = POST_party(create_party_payload(document_number, pix_key))

        if status == 409 and response.get("code") == PARTY_DOCUMENT_TAKEN:
            party_keys[role] = recover_party_by_document(role, document_number)
            continue

        assert status == 201, (role, response)
        assert response["status"] == expected_status, (role, response)

        party_keys[role] = response["party_key"]

    return party_keys
