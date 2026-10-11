from uuid import UUID

from tests.utils import ObjectGenerator, PayloadGenerator, RequestGenerator

ALFA_CLIENT = "c1c1c1c1-c1c1-4c1c-8c1c-c1c1c1c1c1c1"
UNKNOWN_CLIENT = "c404c404-c404-4c40-8c40-c404c404c404"
CARLOS = "33333333-3333-4333-8333-333333333333"


def provision_contract() -> dict:
    """O cenário: um contrato novo da Imobiliária Alfa, que garante os cinco
    livros do cliente c1c1… (S04)."""
    status, contract_ledger = ObjectGenerator.create_contract_ledger()
    assert status == 201, contract_ledger

    return contract_ledger


def collection_key(contract_ledger: dict) -> str:
    collection = contract_ledger["accounts"][0]
    assert collection["purpose_code"] == "COLLECTION"

    return collection["ledger_account_key"]


def balance(ledger_account_key: str) -> int:
    status, ledger_account = RequestGenerator.GET_ledger_account(ledger_account_key)
    assert status == 200, ledger_account

    return ledger_account["balance_in_cents"]


def book_balance(purpose_code: str) -> int:
    """O saldo de um livro do cliente c1c1…, que é de todas as suítes:
    quem o lê mede por diferença."""
    return balance(ObjectGenerator.get_client_account_key(ALFA_CLIENT, purpose_code))


class TestInflowSuspense:
    def test_transfers_inflow_suspense_credits_suspense(self):
        contract_ledger = provision_contract()
        suspense_before = book_balance("UNALLOCATED")
        external_before = book_balance("CASH")

        status, response, payload = ObjectGenerator.create_suspense_inflow()

        assert status == 201, response
        assert str(UUID(response["ledger_transaction_key"])) == response["ledger_transaction_key"]
        assert response["ledger_transaction_type"] == "inflow"
        assert response["end_to_end_id"] == payload["end_to_end_id"]
        for field in ["contract_key", "period_reference", "payer_party_key"]:
            assert response[field] in ("", None), (field, response)
        assert book_balance("UNALLOCATED") - suspense_before == 640000
        assert book_balance("CASH") - external_before == 640000
        assert balance(collection_key(contract_ledger)) == 0

    def test_transfers_inflow_suspense_replays_same_key(self):
        contract_ledger = provision_contract()
        suspense_before = book_balance("UNALLOCATED")
        payload = PayloadGenerator.create_suspense_inflow_payload()
        idempotency_key = payload["end_to_end_id"]

        first_status, first = RequestGenerator.POST_transfers_inflow(payload, idempotency_key=idempotency_key)
        second_status, second = RequestGenerator.POST_transfers_inflow(payload, idempotency_key=idempotency_key)

        assert first_status == 201, first
        assert second_status == 201, second
        assert second["ledger_transaction_key"] == first["ledger_transaction_key"]
        assert book_balance("UNALLOCATED") - suspense_before == 640000

        contract_payload = PayloadGenerator.create_inflow_payload(
            contract_ledger["contract_key"], end_to_end_id=payload["end_to_end_id"]
        )
        status, response = RequestGenerator.POST_transfers_inflow(contract_payload, idempotency_key=idempotency_key)

        assert status == 409, response
        assert response["code"] == "QIT001010"
        assert balance(collection_key(contract_ledger)) == 0

    def test_transfers_inflow_suspense_unknown_client_returns_404(self):
        status, response, _payload = ObjectGenerator.create_suspense_inflow(UNKNOWN_CLIENT)

        assert status == 404, response
        assert response["code"] == "QIT001019"

    def test_transfers_inflow_suspense_refuses_mixed_destination(self):
        contract_key = provision_contract()["contract_key"]

        def suspense_with(**fields) -> dict:
            payload = PayloadGenerator.create_suspense_inflow_payload()
            payload.update(fields)
            return payload

        without_destination = PayloadGenerator.create_suspense_inflow_payload()
        del without_destination["client_key"]

        malformed_payloads = [
            suspense_with(contract_key=contract_key, period_reference="2026-09", payer_party_key=CARLOS),
            suspense_with(period_reference="2026-09"),
            suspense_with(payer_party_key=CARLOS),
            without_destination,
            PayloadGenerator.create_suspense_inflow_payload(client_key="c1c1"),
        ]

        for payload in malformed_payloads:
            status, response = RequestGenerator.POST_transfers_inflow(
                payload, idempotency_key=payload["end_to_end_id"]
            )

            assert status == 400, (payload, response)
            assert response["code"] == "QIT000001"
