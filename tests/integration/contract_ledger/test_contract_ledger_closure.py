from uuid import uuid4

from tests.utils import ObjectGenerator, PayloadGenerator, RequestGenerator


def contract_statuses(contract_key: str) -> list:
    """O status de cada conta do contrato, pela listagem."""
    status, response = RequestGenerator.GET_ledger_accounts({"contract_key": contract_key})
    assert status == 200

    return [account["status"] for account in response["data"]]


def keys_by_purpose(contract_ledger: dict) -> dict:
    keys = dict()
    for account in contract_ledger["accounts"]:
        keys[account["purpose_code"]] = account["ledger_account_key"]

    return keys


def account_of(ledger_account_key: str) -> dict:
    status, response = RequestGenerator.GET_ledger_account(ledger_account_key)
    assert status == 200

    return response


def event_statuses(ledger_account: dict) -> list:
    """Os status da trilha, como multiconjunto: os eventos saem sem ordem."""
    return sorted(status_event["status"] for status_event in ledger_account["status_events"])


CONTRACT_PURPOSES = ["COLLECTION", "RENT", "IPTU", "CONDO", "WATER", "ELECTRICITY"]


class TestContractLedgerClosure:
    def test_contract_ledgers_closure_unknown_contract_returns_404(self):
        status, response = ObjectGenerator.close_contract_ledger(str(uuid4()))

        assert status == 404
        assert response["code"] == "QIT001035"

    def test_contract_ledgers_closure_refuses_malformed_body(self):
        status, contract_ledger = ObjectGenerator.create_contract_ledger()
        assert status == 201
        contract_key = contract_ledger["contract_key"]

        without_actor = PayloadGenerator.create_closure_payload()
        del without_actor["actor"]
        extra_field = PayloadGenerator.create_closure_payload()
        extra_field["status"] = "closed"

        malformed_bodies = [
            without_actor,
            PayloadGenerator.create_closure_payload(actor=""),
            PayloadGenerator.create_closure_payload(reason="x" * 256),
            extra_field,
        ]

        for malformed_body in malformed_bodies:
            status, response = RequestGenerator.POST_contract_ledgers_closure(contract_key, malformed_body)

            assert status == 400, malformed_body
            assert response["code"] == "QIT000001"

        assert contract_statuses(contract_key) == ["active"] * 6

    def test_contract_ledgers_closure_closes_contract_accounts(self):
        status, contract_ledger = ObjectGenerator.create_contract_ledger()
        assert status == 201
        contract_key = contract_ledger["contract_key"]
        keys = keys_by_purpose(contract_ledger)

        status, response = ObjectGenerator.close_contract_ledger(contract_key)

        assert status == 200
        assert response == {"contract_key": contract_key, "closed_accounts": 6}
        for purpose_code in CONTRACT_PURPOSES:
            ledger_account = account_of(keys[purpose_code])
            assert ledger_account["status"] == "closed", purpose_code
            assert event_statuses(ledger_account) == ["active", "closed"], purpose_code
        for purpose_code in ["OWN", "PLATFORM_FEE"]:
            assert account_of(keys[purpose_code])["status"] == "active", purpose_code

    def test_contract_ledgers_closure_is_idempotent(self):
        status, contract_ledger = ObjectGenerator.create_contract_ledger()
        assert status == 201
        contract_key = contract_ledger["contract_key"]
        status, first_response = ObjectGenerator.close_contract_ledger(contract_key)
        assert status == 200

        status, response = ObjectGenerator.close_contract_ledger(contract_key)

        assert status == 200
        assert response == first_response
        rent = account_of(keys_by_purpose(contract_ledger)["RENT"])
        assert event_statuses(rent) == ["active", "closed"]
