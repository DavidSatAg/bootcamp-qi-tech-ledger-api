import threading
import time
from uuid import uuid4

from tests.utils import DbUtils, ObjectGenerator, PayloadGenerator, RequestGenerator

ALFA_CLIENT = "c1c1c1c1-c1c1-4c1c-8c1c-c1c1c1c1c1c1"


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


def assert_integrity() -> None:
    status, integrity = RequestGenerator.GET_integrity({"client_key": ALFA_CLIENT})
    assert status == 200, integrity
    assert integrity["difference_in_cents"] == 0, integrity


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

    def test_ledger_accounts_status_closes_and_refuses_invalid_transitions(self):
        keys = provision_contract()

        status, response = put_status(keys["IPTU"], "closed")

        assert status == 200, response
        assert response["status"] == "closed"
        assert response["balance_in_cents"] == 0

        for to_status in ["active", "blocked", "closed"]:
            status, response = put_status(keys["IPTU"], to_status)

            assert status == 409, (to_status, response)
            assert response["code"] == "QIT001043", (to_status, response)

        status, response = put_status(keys["CONDO"], "active")

        assert status == 409, response
        assert response["code"] == "QIT001043"

        status, response = put_status(keys["WATER"], "blocked")

        assert status == 200, response

        status, response = put_status(keys["WATER"], "closed")

        assert status == 200, response
        assert response["status"] == "closed"
        assert events(get_account(keys["IPTU"])) == ["active", "closed"]

    def test_ledger_accounts_status_close_with_balance_conflicts(self):
        keys = provision_contract()
        status, response, _payload = ObjectGenerator.create_inflow(keys["contract_key"])
        assert status == 201, response

        status, response = put_status(keys["COLLECTION"], "closed")

        assert status == 409, response
        assert response["code"] == "QIT001037"
        ledger_account = get_account(keys["COLLECTION"])
        assert ledger_account["status"] == "active"
        assert events(ledger_account) == ["active"]

        status, response = put_status(keys["COLLECTION"], "blocked")

        assert status == 200, response

        status, response = put_status(keys["COLLECTION"], "closed")

        assert status == 409, response
        assert response["code"] == "QIT001037"
        ledger_account = get_account(keys["COLLECTION"])
        assert ledger_account["status"] == "blocked"
        assert ledger_account["balance_in_cents"] == 640000

    def test_ledger_accounts_status_lock_timeout_conflicts(self):
        keys = provision_contract()

        with DbUtils.hold_row_lock(keys["RENT"]):
            status, response = put_status(keys["RENT"], "blocked")

            assert status == 409, response
            assert response["code"] == "QIT001011"

        status, response = put_status(keys["RENT"], "blocked")

        assert status == 200, response
        assert response["status"] == "blocked"

    def test_ledger_accounts_status_refuses_bad_request(self):
        keys = provision_contract()
        rent = keys["RENT"]
        valid = PayloadGenerator.create_status_payload("blocked")
        without_status = dict(valid)
        del without_status["status"]
        without_actor = dict(valid)
        del without_actor["actor"]
        without_reason = dict(valid)
        del without_reason["reason"]
        cases = [
            without_status,
            PayloadGenerator.create_status_payload("frozen"),
            without_actor,
            PayloadGenerator.create_status_payload("blocked", actor=""),
            without_reason,
            PayloadGenerator.create_status_payload("blocked", reason=""),
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

    def test_ledger_accounts_status_reversal_accepts_blocked(self):
        keys = provision_contract()
        status, tx1, inflow_payload = ObjectGenerator.create_inflow(keys["contract_key"])
        assert status == 201, tx1
        status, response = put_status(keys["COLLECTION"], "blocked")
        assert status == 200, response

        status, response, _payload = ObjectGenerator.create_med_return(
            inflow_payload["end_to_end_id"], amount_in_cents=450000
        )

        assert status == 204, response

        status, response, _payload = ObjectGenerator.create_reversal(tx1["ledger_transaction_key"], amount_in_cents=190000)

        assert status == 201, response
        ledger_account = get_account(keys["COLLECTION"])
        assert ledger_account["balance_in_cents"] == 0
        assert ledger_account["status"] == "blocked"

        status, response, _payload = ObjectGenerator.create_inflow(keys["contract_key"])

        assert status == 409, response
        assert response["code"] == "QIT001012"
        assert_integrity()

    def test_ledger_accounts_status_reversal_accepts_blocked_after_lock(self):
        """O estorno passa o passo 2 com a COLLECTION ativa, espera a trava da
        RENT, e só a releitura vê o `blocked`: ela também aceita o estorno."""
        keys = provision_contract()
        status, response, _payload = ObjectGenerator.create_inflow(keys["contract_key"])
        assert status == 201, response
        status, tx2, _payload = ObjectGenerator.create_split(keys["contract_key"])
        assert status == 201, tx2
        results = []

        def reverse_split() -> None:
            results.append(ObjectGenerator.create_reversal(tx2["ledger_transaction_key"]))

        with DbUtils.hold_row_lock(keys["RENT"]):
            reversal_thread = threading.Thread(target=reverse_split)
            reversal_thread.start()
            time.sleep(0.5)
            assert reversal_thread.is_alive()

            status, response = put_status(keys["COLLECTION"], "blocked")

            assert status == 200, response

        reversal_thread.join()
        status, response, _payload = results[0]

        assert status == 201, response
        ledger_account = get_account(keys["COLLECTION"])
        assert ledger_account["balance_in_cents"] == 640000
        assert ledger_account["status"] == "blocked"
        assert get_account(keys["RENT"])["balance_in_cents"] == 0
