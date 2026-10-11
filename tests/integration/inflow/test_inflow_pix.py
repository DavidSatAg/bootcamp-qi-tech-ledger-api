from uuid import uuid4

from tests.utils import ObjectGenerator, PayloadGenerator, RequestGenerator


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


class TestInflowPix:
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
