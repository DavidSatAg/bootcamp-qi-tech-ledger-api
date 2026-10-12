from uuid import uuid4

from tests.utils import DbUtils, ObjectGenerator, PayloadGenerator, RequestGenerator

ALFA_CLIENT = "c1c1c1c1-c1c1-4c1c-8c1c-c1c1c1c1c1c1"


def divided_contract() -> dict:
    """Contrato provisionado com a TX1 (640000, 2026-09) e a TX2 (a divisão):
    COLLECTION 0, e a `own` da Alfa com +45000. Devolve a chave de cada
    conta, pelo propósito."""
    status, contract_ledger = ObjectGenerator.create_contract_ledger()
    assert status == 201, contract_ledger

    keys = {account["purpose_code"]: account["ledger_account_key"] for account in contract_ledger["accounts"]}
    keys["contract_key"] = contract_ledger["contract_key"]

    status, response, _payload = ObjectGenerator.create_inflow(keys["contract_key"])
    assert status == 201, response

    status, response, _payload = ObjectGenerator.create_split(keys["contract_key"])
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


class TestInternalConflicts:
    def test_transfers_internal_closed_target_conflicts(self):
        """A COLLECTION, zerada pela divisão, encerrada (PUT status): a
        devolução de taxa para ela dá 409 QIT001012 no passo 2, e a `own`
        não se move."""
        keys = divided_contract()
        status, response = RequestGenerator.PUT_ledger_account_status(
            keys["COLLECTION"], PayloadGenerator.create_status_payload("closed")
        )
        assert status == 200, response
        own_before = balance(keys["OWN"])

        status, response, _payload = ObjectGenerator.create_internal(
            keys["OWN"], keys["COLLECTION"], gross_amount_in_cents=45000
        )

        assert status == 409, response
        assert response["code"] == "QIT001012"
        assert balance(keys["OWN"]) == own_before
        assert balance(keys["COLLECTION"]) == 0
        assert_integrity()

    def test_transfers_internal_lock_timeout_conflicts(self):
        """A `own` da Alfa (a origem, débito) travada por fora além do
        lock_timeout: 409 QIT001011, gravado sob a chave; nada se move. Com
        chave nova, depois, a transferência passa."""
        keys = divided_contract()
        payload = PayloadGenerator.create_internal_payload(keys["OWN"], keys["COLLECTION"], gross_amount_in_cents=45000)
        idempotency_key = str(uuid4())
        own_before = balance(keys["OWN"])

        with DbUtils.hold_row_lock(keys["OWN"]):
            status, response = RequestGenerator.POST_transfers_internal(payload, idempotency_key=idempotency_key)

        assert status == 409, response
        assert response["code"] == "QIT001011"
        assert balance(keys["OWN"]) == own_before
        assert balance(keys["COLLECTION"]) == 0
        assert_integrity()

        status, response = RequestGenerator.POST_transfers_internal(payload, idempotency_key=idempotency_key)

        assert status == 409, response
        assert response["code"] == "QIT001011"

        status, response = RequestGenerator.POST_transfers_internal(payload, idempotency_key=str(uuid4()))

        assert status == 201, response
        assert balance(keys["OWN"]) == own_before - 45000
        assert balance(keys["COLLECTION"]) == 45000
