import json
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from tests.utils import ObjectGenerator, PayloadGenerator, RequestGenerator

ALFA_CLIENT = "c1c1c1c1-c1c1-4c1c-8c1c-c1c1c1c1c1c1"
CARLOS = "33333333-3333-4333-8333-333333333333"

# O relógio do container e o da máquina dos testes não andam juntos (hipótese).
SLACK = timedelta(seconds=60)


def provision_contract() -> tuple:
    """Provisiona um contrato novo e devolve (contract_key, chave da COLLECTION)."""
    status, contract_ledger = ObjectGenerator.create_contract_ledger()
    assert status == 201, contract_ledger

    collection = contract_ledger["accounts"][0]
    assert collection["purpose_code"] == "COLLECTION"

    return contract_ledger["contract_key"], collection["ledger_account_key"]


def balance(ledger_account_key: str) -> int:
    status, ledger_account = RequestGenerator.GET_ledger_account(ledger_account_key)
    assert status == 200, ledger_account

    return ledger_account["balance_in_cents"]


def external_key() -> str:
    """O `external/CASH` da Imobiliária Alfa: nasce com o primeiro livro do
    cliente, e por isso está na primeira página da listagem."""
    status, page = RequestGenerator.GET_ledger_accounts({"client_key": ALFA_CLIENT, "limit": "100"})
    assert status == 200, page

    for ledger_account in page["data"]:
        if ledger_account["purpose_code"] == "CASH":
            return ledger_account["ledger_account_key"]

    raise AssertionError(f"external/CASH ausente na listagem: {page}")


class TestInflowPix:
    def test_transfers_inflow_credits_collection(self):
        contract_key, collection_key = provision_contract()
        external_before = balance(external_key())

        status, response, payload = ObjectGenerator.create_inflow(contract_key)

        assert status == 201, response
        assert str(UUID(response["ledger_transaction_key"])) == response["ledger_transaction_key"]
        assert response["ledger_transaction_type"] == "inflow"
        assert response["contract_key"] == contract_key
        assert response["period_reference"] == "2026-09"
        assert response["payer_party_key"] == CARLOS
        assert response["end_to_end_id"] == payload["end_to_end_id"]
        assert balance(collection_key) == 640000
        assert balance(external_key()) - external_before == 640000

    def test_transfers_inflow_records_value_date(self):
        contract_key, _collection_key = provision_contract()

        status, response, _payload = ObjectGenerator.create_inflow(contract_key, value_date="2026-09-05T14:22:00Z")

        assert status == 201, response
        assert datetime.fromisoformat(response["value_date"]) == datetime(2026, 9, 5, 14, 22, tzinfo=timezone.utc)
        assert response["value_date"].endswith("Z")

        before = datetime.now(timezone.utc)
        status, response, _payload = ObjectGenerator.create_inflow(contract_key)
        after = datetime.now(timezone.utc)

        assert status == 201, response
        value_date = datetime.fromisoformat(response["value_date"])
        assert before - SLACK <= value_date <= after + SLACK
        assert response["value_date"].endswith("Z")

    def test_transfers_inflow_unknown_contract_returns_404(self):
        status, response, _payload = ObjectGenerator.create_inflow(str(uuid4()))

        assert status == 404, response
        assert response["code"] == "QIT001035"

    def test_transfers_inflow_requires_idempotency_key(self):
        contract_key, collection_key = provision_contract()
        payload = PayloadGenerator.create_inflow_payload(contract_key)

        for idempotency_key in [None, "k" * 256]:
            status, response = RequestGenerator.POST_transfers_inflow(payload, idempotency_key=idempotency_key)

            assert status == 400, (idempotency_key, response)
            assert response["code"] == "QIT000001"

        assert balance(collection_key) == 0

    def test_transfers_inflow_refuses_malformed_body(self):
        contract_key, _collection_key = provision_contract()

        def without(field: str) -> dict:
            payload = PayloadGenerator.create_inflow_payload(contract_key)
            del payload[field]
            return payload

        with_extra_field = PayloadGenerator.create_inflow_payload(contract_key)
        with_extra_field["currency"] = "BRL"

        malformed_payloads = [
            PayloadGenerator.create_inflow_payload(contract_key, amount_in_cents=0),
            PayloadGenerator.create_inflow_payload(contract_key, amount_in_cents=-1),
            PayloadGenerator.create_inflow_payload(contract_key, amount_in_cents="640000"),
            without("payer_party_key"),
            without("actor"),
            PayloadGenerator.create_inflow_payload(contract_key, period_reference="2026-9"),
            with_extra_field,
            PayloadGenerator.create_inflow_payload(contract_key, value_date="2026-02-30T00:00:00Z"),
        ]

        for payload in malformed_payloads:
            status, response = RequestGenerator.POST_transfers_inflow(payload, idempotency_key=str(uuid4()))

            assert status == 400, (payload, response)
            assert response["code"] == "QIT000001"

    def test_transfers_inflow_schema_failure_does_not_burn_key(self):
        contract_key, collection_key = provision_contract()
        idempotency_key = str(uuid4())

        payload = PayloadGenerator.create_inflow_payload(contract_key, amount_in_cents=0)
        status, response = RequestGenerator.POST_transfers_inflow(payload, idempotency_key=idempotency_key)

        assert status == 400, response
        assert response["code"] == "QIT000001"

        payload = PayloadGenerator.create_inflow_payload(contract_key)
        status, response = RequestGenerator.POST_transfers_inflow(payload, idempotency_key=idempotency_key)

        assert status == 201, response
        assert balance(collection_key) == 640000

    def test_transfers_inflow_replays_same_key(self):
        contract_key, collection_key = provision_contract()
        payload = PayloadGenerator.create_inflow_payload(contract_key)
        idempotency_key = payload["end_to_end_id"]

        first_status, first_response = RequestGenerator.POST_transfers_inflow(payload, idempotency_key=idempotency_key)
        second_status, second_response = RequestGenerator.POST_transfers_inflow(payload, idempotency_key=idempotency_key)

        assert first_status == 201, first_response
        assert second_status == 201, second_response
        assert second_response == first_response
        assert balance(collection_key) == 640000

    def test_transfers_inflow_same_key_other_body_conflicts(self):
        contract_key, collection_key = provision_contract()
        payload = PayloadGenerator.create_inflow_payload(contract_key)
        idempotency_key = payload["end_to_end_id"]
        raw_body = json.dumps(payload).encode()

        status, response = RequestGenerator.POST_transfers_inflow(idempotency_key=idempotency_key, raw_body=raw_body)
        assert status == 201, response

        other_amount = dict(payload, amount_in_cents=320000)
        other_bodies = [json.dumps(other_amount).encode(), raw_body + b" "]

        for other_body in other_bodies:
            status, response = RequestGenerator.POST_transfers_inflow(
                idempotency_key=idempotency_key, raw_body=other_body
            )

            assert status == 409, (other_body, response)
            assert response["code"] == "QIT001010"

        assert balance(collection_key) == 640000

    def test_transfers_inflow_repeated_end_to_end_id_conflicts(self):
        contract_key, collection_key = provision_contract()
        payload = PayloadGenerator.create_inflow_payload(contract_key)

        status, response = RequestGenerator.POST_transfers_inflow(payload, idempotency_key=str(uuid4()))
        assert status == 201, response

        other_key = str(uuid4())
        status, response = RequestGenerator.POST_transfers_inflow(payload, idempotency_key=other_key)

        assert status == 409, response
        assert response["code"] == "QIT001010"

        # O erro ficou gravado sob a segunda chave: outro corpo com ela é conflito.
        other_payload = PayloadGenerator.create_inflow_payload(contract_key)
        status, response = RequestGenerator.POST_transfers_inflow(other_payload, idempotency_key=other_key)

        assert status == 409, response
        assert response["code"] == "QIT001010"
        assert balance(collection_key) == 640000
