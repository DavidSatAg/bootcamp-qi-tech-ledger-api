from uuid import uuid4

from tests.utils import ObjectGenerator, RequestGenerator

PLATFORM_CLIENT = "9c9c9c9c-9c9c-49c9-89c9-9c9c9c9c9c9c"
ANA = "22222222-2222-4222-8222-222222222222"
OTHER_AMOUNT = 80000


def balance(ledger_account_key: str) -> int:
    status, ledger_account = RequestGenerator.GET_ledger_account(ledger_account_key)
    assert status == 200, ledger_account

    return ledger_account["balance_in_cents"]


def entries_of(ledger_transaction_key: str) -> list:
    status, response = RequestGenerator.GET_transfer_trace(ledger_transaction_key)
    assert status == 200, response

    return response["entries"]


class TestWalletDepositWithdrawal:
    def test_transfers_inflow_wallet_deposit_credits_wallet(self):
        status, wallet = ObjectGenerator.open_wallet(ANA)
        assert status in (200, 201), wallet
        wallet_key = wallet["ledger_account_key"]
        platform_cash = ObjectGenerator.get_client_account_key(PLATFORM_CLIENT, "CASH")
        wallet_before = balance(wallet_key)
        platform_cash_before = balance(platform_cash)

        status, response, payload = ObjectGenerator.create_deposit(wallet_key, amount_in_cents=450000)

        assert status == 201, response
        assert response["ledger_transaction_type"] == "inflow"
        assert response["payer_party_key"] == ANA
        assert response["contract_key"] is None
        assert response["period_reference"] is None
        assert response["end_to_end_id"] == payload["end_to_end_id"]
        assert balance(wallet_key) == wallet_before + 450000
        assert balance(platform_cash) == platform_cash_before + 450000

        entries = entries_of(response["ledger_transaction_key"])
        assert [
            (entry["direction"], entry["purpose_code"], entry["amount_in_cents"], entry["ledger_account_key"])
            for entry in entries
        ] == [
            ("D", "CASH", 450000, platform_cash),
            ("C", "WALLET", 450000, wallet_key),
        ]

        unknown_wallet_key = str(uuid4())
        end_to_end_id = "E00000000202609051422" + uuid4().hex[:11]
        status, response, _payload = ObjectGenerator.create_deposit(unknown_wallet_key, end_to_end_id=end_to_end_id)

        assert status == 404, response
        assert response["code"] == "QIT001018"

        status, response, _payload = ObjectGenerator.create_deposit(
            unknown_wallet_key, end_to_end_id=end_to_end_id, amount_in_cents=OTHER_AMOUNT
        )

        assert status == 409, response
        assert response["code"] == "QIT001010"
