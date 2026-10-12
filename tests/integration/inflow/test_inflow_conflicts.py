from uuid import uuid4

from tests.utils import DbUtils, ObjectGenerator, PayloadGenerator, RequestGenerator

PLATFORM_CLIENT = "9c9c9c9c-9c9c-49c9-89c9-9c9c9c9c9c9c"


def balance(ledger_account_key: str) -> int:
    status, ledger_account = RequestGenerator.GET_ledger_account(ledger_account_key)
    assert status == 200, ledger_account

    return ledger_account["balance_in_cents"]


def collection_key(contract_ledger: dict) -> str:
    collection = contract_ledger["accounts"][0]
    assert collection["purpose_code"] == "COLLECTION"

    return collection["ledger_account_key"]


class TestInflowConflicts:
    def test_transfers_inflow_wallet_lock_timeout_conflicts(self):
        """O pagamento pela carteira debita a carteira, que é a conta que o
        motor trava (passo 4). Travada por fora além do lock_timeout: 409
        QIT001011, gravado sob a chave; nada se move. Com chave nova, depois,
        o pagamento passa."""
        wallet_key = ObjectGenerator.create_funded_wallet()
        status, contract_ledger = ObjectGenerator.create_contract_ledger()
        assert status == 201, contract_ledger
        collection = collection_key(contract_ledger)
        payload = PayloadGenerator.create_wallet_inflow_payload(contract_ledger["contract_key"], wallet_key)
        idempotency_key = str(uuid4())
        wallet_before = balance(wallet_key)

        with DbUtils.hold_row_lock(wallet_key):
            status, response = RequestGenerator.POST_transfers_inflow(payload, idempotency_key=idempotency_key)

        assert status == 409, response
        assert response["code"] == "QIT001011"
        assert balance(wallet_key) == wallet_before
        assert balance(collection) == 0
        status, integrity = RequestGenerator.GET_integrity({"client_key": PLATFORM_CLIENT})
        assert status == 200, integrity
        assert integrity["difference_in_cents"] == 0

        status, response = RequestGenerator.POST_transfers_inflow(payload, idempotency_key=idempotency_key)

        assert status == 409, response
        assert response["code"] == "QIT001011"

        status, response = RequestGenerator.POST_transfers_inflow(payload, idempotency_key=str(uuid4()))

        assert status == 201, response
        assert balance(wallet_key) == wallet_before - payload["amount_in_cents"]
        assert balance(collection) == payload["amount_in_cents"]
