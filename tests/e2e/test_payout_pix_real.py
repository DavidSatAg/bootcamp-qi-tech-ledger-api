"""Cópia de tests/integration/payout/test_payout_pix.py contra o Cadastro de
verdade. O original continua intacto, contra o party-mock.

A mudança é a origem das chaves: as mágicas do party-mock viram partes
criadas de verdade pela fixture `party_scenarios` (2222… → aprovada,
aaaa… → pendente, dddd… → sem_pix, eeee… → pix_timeout, ffff… → pix_erro),
e a inexistente (bbbb…) vira um UUID novo, nunca cadastrado. A pix_key
esperada no despacho ao provedor deixa de ser o literal do party-mock e passa
a ser a que o seed cadastrou para a "aprovada" (`SCENARIOS`). O provedor
continua mock no ponto de integração (01b §0.2), e por isso o diário dele
segue valendo. O "ana.locadora@example.com" do corpo inválido fica: é só
entrada de um 400.

Dois testes do original NÃO estão aqui:

- `test_transfers_payout_party_unavailable_records_nothing` (cccc…, Cadastro
  fora do ar): contra o real ele só existe parando o container, e isso é o
  tests/e2e/test_party_api_down.py, que roda isolado;
- `test_transfers_payout_replay_skips_party`: ele conta as leituras no diário
  do party-mock (`GET_mock_requests("party-mock", ...)`). Contra o real o
  party-mock não recebe nada, e a contagem seria 0 == 0 com ou sem a consulta
  ao Cadastro: a asserção passaria sem provar nada. O Cadastro real não tem
  diário de requisições para pôr no lugar. Fica só contra o mock.
"""
from uuid import uuid4

from tests.utils import ObjectGenerator, PayloadGenerator, RequestGenerator
from tests.utils.party_scenarios import (
    APROVADA,
    PENDENTE as PAPEL_PENDENTE,
    PIX_ERRO as PAPEL_PIX_ERRO,
    PIX_TIMEOUT as PAPEL_PIX_TIMEOUT,
    SCENARIOS,
    SEM_PIX as PAPEL_SEM_PIX,
)

ALFA_CLIENT = "c1c1c1c1-c1c1-4c1c-8c1c-c1c1c1c1c1c1"
OTHER_AMOUNT = 80000

# A pix_key com que o seed cadastra a "aprovada": (final, pix_key, status).
APROVADA_PIX_KEY = SCENARIOS[APROVADA][1]


def provision_contract() -> dict:
    """Provisiona um contrato novo e devolve a chave de cada conta, pelo propósito."""
    status, contract_ledger = ObjectGenerator.create_contract_ledger()
    assert status == 201, contract_ledger

    keys = {account["purpose_code"]: account["ledger_account_key"] for account in contract_ledger["accounts"]}
    keys["contract_key"] = contract_ledger["contract_key"]

    return keys


def rent_key(contract_ledger: dict) -> str:
    """A chave da RENT no corpo do provisionamento."""
    for account in contract_ledger["accounts"]:
        if account["purpose_code"] == "RENT":
            return account["ledger_account_key"]

    raise AssertionError(contract_ledger)


def balance(ledger_account_key: str) -> int:
    status, ledger_account = RequestGenerator.GET_ledger_account(ledger_account_key)
    assert status == 200, ledger_account

    return ledger_account["balance_in_cents"]


def clearing_key() -> str:
    """A `clearing/TRANSIT` da Imobiliária Alfa: o destino de todo repasse dela."""
    return ObjectGenerator.get_client_account_key(ALFA_CLIENT, "TRANSIT")


def trace(ledger_transaction_key: str) -> dict:
    status, response = RequestGenerator.GET_transfer_trace(ledger_transaction_key)
    assert status == 200, response

    return response


def pix_dispatches(dispatch_idempotency_key: str) -> list:
    """As chamadas `POST /pix` que o provedor recebeu com esta chave de despacho."""
    return [
        (headers, body)
        for headers, body in RequestGenerator.GET_mock_requests("provider-mock", "/pix")
        if body is not None and body.get("dispatch_idempotency_key") == dispatch_idempotency_key
    ]


class TestPayoutPix:
    def test_transfers_payout_unknown_source_returns_404(self):
        status, response, _payload = ObjectGenerator.create_payout(str(uuid4()))

        assert status == 404, response
        assert response["code"] == "QIT001018"

    def test_transfers_payout_refuses_malformed_body(self):
        keys = provision_contract()
        rent_key = keys["RENT"]
        valid = PayloadGenerator.create_payout_payload(rent_key)
        without_actor = dict(valid)
        del without_actor["actor"]
        without_reason = dict(valid)
        del without_reason["reason"]
        without_period = dict(valid)
        del without_period["period_reference"]
        cases = [
            (valid, None),
            (valid, "k" * 256),
            (PayloadGenerator.create_payout_payload(rent_key, amount_in_cents=0), str(uuid4())),
            (PayloadGenerator.create_payout_payload(rent_key, amount_in_cents="450000"), str(uuid4())),
            (PayloadGenerator.create_payout_payload(rent_key, destination="ted"), str(uuid4())),
            (without_actor, str(uuid4())),
            (without_reason, str(uuid4())),
            (dict(valid, reason=""), str(uuid4())),
            (without_period, str(uuid4())),
            (PayloadGenerator.create_payout_payload(rent_key, period_reference="2026-9"), str(uuid4())),
            (dict(valid, pix_key="ana.locadora@example.com"), str(uuid4())),
        ]

        for payload, idempotency_key in cases:
            status, response = RequestGenerator.POST_transfers_payout(payload, idempotency_key=idempotency_key)

            assert status == 400, (payload, idempotency_key, response)
            assert response["code"] == "QIT000001", (payload, idempotency_key, response)

    def test_transfers_payout_from_collection_refused(self):
        keys = provision_contract()
        status, response, _payload = ObjectGenerator.create_inflow(keys["contract_key"])
        assert status == 201, response
        clearing_before = balance(clearing_key())

        status, response, _payload = ObjectGenerator.create_payout(keys["COLLECTION"], amount_in_cents=640000)

        assert status == 422, response
        assert response["code"] == "QIT001008"
        assert balance(keys["COLLECTION"]) == 640000
        assert balance(clearing_key()) == clearing_before

    def test_transfers_payout_forbidden_pair_before_balance(self):
        """COLLECTION vazia: o par proibido sai antes da trava e do saldo,
        e a mesma chave repete o 008 gravado."""
        keys = provision_contract()
        idempotency_key = str(uuid4())

        status, response, _payload = ObjectGenerator.create_payout(keys["COLLECTION"], idempotency_key=idempotency_key)

        assert status == 422, response
        assert response["code"] == "QIT001008"

        status, response, _payload = ObjectGenerator.create_payout(keys["COLLECTION"], idempotency_key=idempotency_key)

        assert status == 422, response
        assert response["code"] == "QIT001008"

    def test_transfers_payout_insufficient_balance(self, party_scenarios):
        ANA = party_scenarios[APROVADA]

        rent = rent_key(ObjectGenerator.create_divided_contract(ANA))
        clearing_before = balance(clearing_key())

        status, response, _payload = ObjectGenerator.create_payout(rent, amount_in_cents=640000)

        assert status == 422, response
        assert response["code"] == "QIT001009"
        assert balance(rent) == 450000
        assert balance(clearing_key()) == clearing_before

    # test_transfers_payout_party_unavailable_records_nothing (cccc…, Cadastro
    # fora do ar) não está aqui: ver o topo do arquivo.

    def test_transfers_payout_owner_not_active(self, party_scenarios):
        """Dono pendente ou desconhecido: 038 gravado (D1); a mesma chave
        repete o 038, e com outro corpo dá 010."""
        PENDING_PARTY = party_scenarios[PAPEL_PENDENTE]
        UNKNOWN_PARTY = str(uuid4())

        for party_key in [PENDING_PARTY, UNKNOWN_PARTY]:
            rent = rent_key(ObjectGenerator.create_divided_contract(party_key))
            idempotency_key = str(uuid4())

            status, response, _payload = ObjectGenerator.create_payout(rent, idempotency_key=idempotency_key)

            assert status == 409, (party_key, response)
            assert response["code"] == "QIT001038", (party_key, response)

            status, response, _payload = ObjectGenerator.create_payout(rent, idempotency_key=idempotency_key)

            assert status == 409, (party_key, response)
            assert response["code"] == "QIT001038", (party_key, response)

            status, response, _payload = ObjectGenerator.create_payout(
                rent, idempotency_key=idempotency_key, amount_in_cents=OTHER_AMOUNT
            )

            assert status == 409, (party_key, response)
            assert response["code"] == "QIT001010", (party_key, response)
            assert balance(rent) == 450000

    def test_transfers_payout_owner_without_pix_key(self, party_scenarios):
        WITHOUT_PIX_KEY = party_scenarios[PAPEL_SEM_PIX]

        rent = rent_key(ObjectGenerator.create_divided_contract(WITHOUT_PIX_KEY))

        status, response, _payload = ObjectGenerator.create_payout(rent)

        assert status == 422, response
        assert response["code"] == "QIT001039"
        assert balance(rent) == 450000

    def test_transfers_payout_pix_debits_to_clearing(self, party_scenarios):
        ANA = party_scenarios[APROVADA]

        rent = rent_key(ObjectGenerator.create_divided_contract(ANA))
        clearing_before = balance(clearing_key())

        status, response, _payload = ObjectGenerator.create_payout(rent)

        assert status == 202, response
        assert response["ledger_transaction_type"] == "payout"
        assert response["period_reference"] == "2026-09"
        assert response["outbox"]["beneficiary_party_key"] == ANA
        assert balance(rent) == 0
        assert balance(clearing_key()) == clearing_before + 450000
        entries = trace(response["ledger_transaction_key"])["entries"]
        assert [
            (entry["direction"], entry["purpose_code"], entry["amount_in_cents"], entry["ledger_account_type"])
            for entry in entries
        ] == [("D", "RENT", 450000, "earmark"), ("C", "TRANSIT", 450000, "clearing")]
        assert (entries[0]["owner_party_key"], entries[0]["owner_role"]) == (ANA, "landlord")
        assert entries[1]["owner_party_key"] is None

    def test_transfers_payout_dispatches_once(self, party_scenarios):
        ANA = party_scenarios[APROVADA]

        rent = rent_key(ObjectGenerator.create_divided_contract(ANA))

        status, response, _payload = ObjectGenerator.create_payout(rent)

        assert status == 202, response
        outbox = response["outbox"]
        assert outbox["outbox_status"] == "sent"
        assert outbox["attempt_count"] == 0
        payout_trace = trace(response["ledger_transaction_key"])
        dispatches = pix_dispatches(outbox["dispatch_idempotency_key"])
        assert len(dispatches) == 1, dispatches
        headers, body = dispatches[0]
        assert body["pix_key"] == APROVADA_PIX_KEY
        assert body["amount_in_cents"] == 450000
        assert headers["x-request-id"] == payout_trace["transaction"]["trace_id"]
        chain = payout_trace["chain"]
        assert [link["ledger_transaction_type"] for link in chain] == ["inflow", "split", "payout"]
        assert chain[2]["outbox_key"] == outbox["outbox_key"]
        assert chain[2]["outbox_status"] == "sent"

    def test_transfers_payout_provider_failure_stays_pending(self, party_scenarios):
        """Provedor em timeout ou com erro: o débito fica, a outbox volta a
        `pending` com uma tentativa, e ninguém tenta de novo nesta requisição."""
        PIX_TIMEOUT = party_scenarios[PAPEL_PIX_TIMEOUT]
        PIX_ERROR = party_scenarios[PAPEL_PIX_ERRO]

        for party_key in [PIX_TIMEOUT, PIX_ERROR]:
            rent = rent_key(ObjectGenerator.create_divided_contract(party_key))
            clearing_before = balance(clearing_key())

            status, response, _payload = ObjectGenerator.create_payout(rent)

            assert status == 202, (party_key, response)
            outbox = response["outbox"]
            assert outbox["outbox_status"] == "pending", (party_key, outbox)
            assert outbox["attempt_count"] == 1, (party_key, outbox)
            assert balance(rent) == 0
            assert balance(clearing_key()) == clearing_before + 450000
            assert len(pix_dispatches(outbox["dispatch_idempotency_key"])) == 1
            assert trace(response["ledger_transaction_key"])["chain"][-1]["outbox_status"] == "pending"

    def test_transfers_payout_replays_same_key(self, party_scenarios):
        ANA = party_scenarios[APROVADA]

        rent = rent_key(ObjectGenerator.create_divided_contract(ANA))
        idempotency_key = str(uuid4())

        status_first, first, _payload = ObjectGenerator.create_payout(rent, idempotency_key=idempotency_key)
        status_second, second, _payload = ObjectGenerator.create_payout(rent, idempotency_key=idempotency_key)

        assert (status_first, status_second) == (202, 202), (first, second)
        assert second["ledger_transaction_key"] == first["ledger_transaction_key"]
        assert second["outbox"]["outbox_key"] == first["outbox"]["outbox_key"]
        assert balance(rent) == 0
        assert len(pix_dispatches(first["outbox"]["dispatch_idempotency_key"])) == 1

    # test_transfers_payout_replay_skips_party (o replay não pergunta ao
    # Cadastro) não está aqui: ver o topo do arquivo.
