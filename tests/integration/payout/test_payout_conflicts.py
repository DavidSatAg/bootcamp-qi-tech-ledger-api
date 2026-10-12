from uuid import uuid4

from tests.utils import DbUtils, ObjectGenerator, PayloadGenerator, RequestGenerator

ALFA_CLIENT = "c1c1c1c1-c1c1-4c1c-8c1c-c1c1c1c1c1c1"
ANA = "22222222-2222-4222-8222-222222222222"


def rent_key(contract_ledger: dict) -> str:
    """A chave da RENT no corpo do provisionamento."""
    for account in contract_ledger["accounts"]:
        if account["purpose_code"] == "RENT":
            return account["ledger_account_key"]

    raise AssertionError(contract_ledger)


def balance(ledger_account_key: str) -> int:
    status, ledger_account = RequestGenerator.GET_ledger_account(ledger_account_key)
    assert status == 200, ledger_account

    return ledger_account["balance_in_cents"]


def assert_integrity() -> None:
    status, integrity = RequestGenerator.GET_integrity({"client_key": ALFA_CLIENT})
    assert status == 200, integrity
    assert integrity["difference_in_cents"] == 0, integrity


class TestPayoutConflicts:
    def test_transfers_payout_blocked_source_conflicts(self):
        """A RENT bloqueada (PUT status): o repasse dá 409 QIT001012 no
        passo 2, sem pernas; desbloqueada, o mesmo corpo repassa."""
        rent = rent_key(ObjectGenerator.create_divided_contract(ANA))
        status, response = RequestGenerator.PUT_ledger_account_status(
            rent, PayloadGenerator.create_status_payload("blocked")
        )
        assert status == 200, response

        status, response, payload = ObjectGenerator.create_payout(rent)

        assert status == 409, response
        assert response["code"] == "QIT001012"
        assert balance(rent) == 450000
        assert_integrity()

        status, response = RequestGenerator.PUT_ledger_account_status(
            rent, PayloadGenerator.create_status_payload("active")
        )
        assert status == 200, response

        status, response = RequestGenerator.POST_transfers_payout(payload, idempotency_key=str(uuid4()))

        assert status == 202, response
        assert balance(rent) == 0

    def test_transfers_payout_lock_timeout_conflicts(self):
        """A RENT travada por fora além do lock_timeout: 409 QIT001011,
        gravado sob a chave; nada se move. Com chave nova, depois, o repasse
        passa."""
        rent = rent_key(ObjectGenerator.create_divided_contract(ANA))
        payload = PayloadGenerator.create_payout_payload(rent)
        idempotency_key = str(uuid4())

        with DbUtils.hold_row_lock(rent):
            status, response = RequestGenerator.POST_transfers_payout(payload, idempotency_key=idempotency_key)

        assert status == 409, response
        assert response["code"] == "QIT001011"
        assert balance(rent) == 450000
        assert_integrity()

        status, response = RequestGenerator.POST_transfers_payout(payload, idempotency_key=idempotency_key)

        assert status == 409, response
        assert response["code"] == "QIT001011"

        status, response = RequestGenerator.POST_transfers_payout(payload, idempotency_key=str(uuid4()))

        assert status == 202, response
        assert balance(rent) == 0
