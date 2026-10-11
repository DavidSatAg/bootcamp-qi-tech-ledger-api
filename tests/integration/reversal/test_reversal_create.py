from uuid import uuid4

from tests.utils import ObjectGenerator, PayloadGenerator, RequestGenerator

ALFA_CLIENT = "c1c1c1c1-c1c1-4c1c-8c1c-c1c1c1c1c1c1"


def provision_contract(**kwargs) -> dict:
    """Provisiona um contrato novo e devolve a chave de cada conta, pelo
    propósito, e a do contrato."""
    status, contract_ledger = ObjectGenerator.create_contract_ledger(**kwargs)
    assert status == 201, contract_ledger

    keys = {account["purpose_code"]: account["ledger_account_key"] for account in contract_ledger["accounts"]}
    keys["contract_key"] = contract_ledger["contract_key"]

    return keys


def balance(ledger_account_key: str) -> int:
    status, ledger_account = RequestGenerator.GET_ledger_account(ledger_account_key)
    assert status == 200, ledger_account

    return ledger_account["balance_in_cents"]


def inflow(contract_key: str, **kwargs) -> dict:
    """A TX1: a entrada de 640000 na competência 2026-09."""
    status, response, _payload = ObjectGenerator.create_inflow(contract_key, **kwargs)
    assert status == 201, response

    return response


class TestReversalCreate:
    def test_transfers_reversal_unknown_transaction_returns_404(self):
        payload = PayloadGenerator.create_reversal_payload()
        unknown_key = str(uuid4())

        for _attempt in range(2):
            status, response = RequestGenerator.POST_transfers_reversal(
                unknown_key, payload, idempotency_key=str(uuid4())
            )

            assert status == 404, response
            assert response["code"] == "QIT001020"

    def test_transfers_reversal_refuses_malformed_body(self):
        keys = provision_contract()
        tx1 = inflow(keys["contract_key"])
        valid = PayloadGenerator.create_reversal_payload()
        without_actor = dict(valid)
        del without_actor["actor"]
        cases = [
            (valid, None),
            (valid, "k" * 256),
            (without_actor, str(uuid4())),
            (dict(valid, amount_in_cents=0), str(uuid4())),
            (dict(valid, amount_in_cents="450000"), str(uuid4())),
            (dict(valid, value_date="2026-09-06T10:00:00Z"), str(uuid4())),
        ]

        for payload, idempotency_key in cases:
            status, response = RequestGenerator.POST_transfers_reversal(
                tx1["ledger_transaction_key"], payload, idempotency_key=idempotency_key
            )

            assert status == 400, (payload, idempotency_key, response)
            assert response["code"] == "QIT000001", (payload, idempotency_key, response)

        assert balance(keys["COLLECTION"]) == 640000
