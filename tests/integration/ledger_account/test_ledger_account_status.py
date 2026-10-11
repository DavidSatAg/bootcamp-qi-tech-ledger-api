from uuid import uuid4

from tests.utils import ObjectGenerator, PayloadGenerator, RequestGenerator


def provision_contract() -> dict:
    """Provisiona um contrato novo e devolve a chave de cada conta, pelo propósito."""
    status, contract_ledger = ObjectGenerator.create_contract_ledger()
    assert status == 201, contract_ledger

    keys = {account["purpose_code"]: account["ledger_account_key"] for account in contract_ledger["accounts"]}
    keys["contract_key"] = contract_ledger["contract_key"]

    return keys


def get_account(ledger_account_key: str) -> dict:
    status, ledger_account = RequestGenerator.GET_ledger_account(ledger_account_key)
    assert status == 200, ledger_account

    return ledger_account


def events(ledger_account: dict) -> list:
    """A trilha de status como multiconjunto: a ordem dos eventos não é garantida."""
    return sorted(event["status"] for event in ledger_account["status_events"])


def put_status(ledger_account_key: str, status: str) -> tuple:
    return RequestGenerator.PUT_ledger_account_status(
        ledger_account_key, PayloadGenerator.create_status_payload(status)
    )


class TestLedgerAccountStatus:
    def test_ledger_accounts_status_blocks_and_unblocks(self):
        keys = provision_contract()
        status, response, _payload = ObjectGenerator.create_inflow(keys["contract_key"])
        assert status == 201, response

        status, response = put_status(keys["COLLECTION"], "blocked")

        assert status == 200, response
        assert response["ledger_account_key"] == keys["COLLECTION"]
        assert response["status"] == "blocked"
        assert response["balance_in_cents"] == 640000
        assert events(response) == ["active", "blocked"]

        inflow_payload = PayloadGenerator.create_inflow_payload(keys["contract_key"])
        idempotency_key = inflow_payload["end_to_end_id"]
        for _ in range(2):
            status, response = RequestGenerator.POST_transfers_inflow(inflow_payload, idempotency_key=idempotency_key)

            assert status == 409, response
            assert response["code"] == "QIT001012"

        status, response = put_status(keys["COLLECTION"], "active")

        assert status == 200, response
        assert response["status"] == "active"
        assert events(response) == ["active", "active", "blocked"]

        status, response, _payload = ObjectGenerator.create_inflow(keys["contract_key"])

        assert status == 201, response
        assert get_account(keys["COLLECTION"])["balance_in_cents"] == 1280000

    def test_ledger_accounts_status_refuses_bad_request(self):
        keys = provision_contract()
        rent = keys["RENT"]
        valid = PayloadGenerator.create_status_payload("blocked")
        without_status = dict(valid)
        del without_status["status"]
        without_actor = dict(valid)
        del without_actor["actor"]
        cases = [
            without_status,
            PayloadGenerator.create_status_payload("frozen"),
            without_actor,
            PayloadGenerator.create_status_payload("blocked", actor=""),
            PayloadGenerator.create_status_payload("blocked", reason="r" * 256),
            dict(valid, balance_in_cents=0),
        ]

        for payload in cases:
            status, response = RequestGenerator.PUT_ledger_account_status(rent, payload)

            assert status == 400, (payload, response)
            assert response["code"] == "QIT000001", (payload, response)

        status, response = RequestGenerator.PUT_ledger_account_status(str(uuid4()), valid)

        assert status == 404, response
        assert response["code"] == "QIT001018"
        ledger_account = get_account(rent)
        assert ledger_account["status"] == "active"
        assert events(ledger_account) == ["active"]
