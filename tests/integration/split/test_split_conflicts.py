from uuid import uuid4

from tests.utils import ObjectGenerator, PayloadGenerator, RequestGenerator

ALFA_CLIENT = "c1c1c1c1-c1c1-4c1c-8c1c-c1c1c1c1c1c1"


def provision_contract() -> dict:
    """Provisiona um contrato novo, recebe a TX1 (640000, 2026-09) e devolve
    a chave de cada conta, pelo propósito, e a do contrato."""
    status, contract_ledger = ObjectGenerator.create_contract_ledger()
    assert status == 201, contract_ledger

    keys = {account["purpose_code"]: account["ledger_account_key"] for account in contract_ledger["accounts"]}
    keys["contract_key"] = contract_ledger["contract_key"]

    status, response, _payload = ObjectGenerator.create_inflow(keys["contract_key"])
    assert status == 201, response

    return keys


def balance(ledger_account_key: str) -> int:
    status, ledger_account = RequestGenerator.GET_ledger_account(ledger_account_key)
    assert status == 200, ledger_account

    return ledger_account["balance_in_cents"]


def assert_integrity() -> None:
    status, integrity = RequestGenerator.GET_integrity({"client_key": ALFA_CLIENT})
    assert status == 200, integrity
    assert integrity["difference_in_cents"] == 0, integrity


class TestSplitConflicts:
    def test_transfers_split_blocked_destination_conflicts(self):
        """Um destino da divisão bloqueado (PUT status): 409 QIT001012 no
        passo 2, nada se move; desbloqueado, a mesma competência divide."""
        keys = provision_contract()
        status, response = RequestGenerator.PUT_ledger_account_status(
            keys["RENT"], PayloadGenerator.create_status_payload("blocked")
        )
        assert status == 200, response

        status, response, payload = ObjectGenerator.create_split(keys["contract_key"])

        assert status == 409, response
        assert response["code"] == "QIT001012"
        assert balance(keys["COLLECTION"]) == 640000
        assert balance(keys["RENT"]) == 0
        assert_integrity()

        status, response = RequestGenerator.PUT_ledger_account_status(
            keys["RENT"], PayloadGenerator.create_status_payload("active")
        )
        assert status == 200, response

        status, response = RequestGenerator.POST_transfers_split(payload, idempotency_key=str(uuid4()))

        assert status == 201, response
        assert balance(keys["COLLECTION"]) == 0
        assert balance(keys["RENT"]) == 450000

    def test_transfers_split_same_key_other_body_conflicts(self):
        """A mesma `Idempotency-Key` com outro corpo: 409 QIT001010, sem
        segunda divisão; com o corpo de antes, o replay devolve a mesma."""
        keys = provision_contract()
        idempotency_key = str(uuid4())

        status, first, payload = ObjectGenerator.create_split(keys["contract_key"], idempotency_key=idempotency_key)
        assert status == 201, first

        other_body = dict(payload, reason="outra divisão do aluguel 09/2026")
        status, response = RequestGenerator.POST_transfers_split(other_body, idempotency_key=idempotency_key)

        assert status == 409, response
        assert response["code"] == "QIT001010"

        status, replay = RequestGenerator.POST_transfers_split(payload, idempotency_key=idempotency_key)

        assert status == 201, replay
        assert replay["ledger_transaction_key"] == first["ledger_transaction_key"]
        assert balance(keys["COLLECTION"]) == 0
        assert balance(keys["RENT"]) == 450000
        assert_integrity()
