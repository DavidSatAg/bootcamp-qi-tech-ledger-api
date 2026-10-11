from tests.utils import ObjectGenerator, RequestGenerator

PLATFORM_CLIENT = "9c9c9c9c-9c9c-49c9-89c9-9c9c9c9c9c9c"


def balance(ledger_account_key: str) -> int:
    status, ledger_account = RequestGenerator.GET_ledger_account(ledger_account_key)
    assert status == 200, ledger_account

    return ledger_account["balance_in_cents"]


class TestWalletWithdrawalSettlement:
    def test_webhooks_provider_settles_wallet_withdrawal(self):
        """A metade "liquidação" do saque (W9; remodelagem/10 :130): o aviso
        do provedor leva o saque da TRANSIT da plataforma para o CASH dela."""
        wallet_key = ObjectGenerator.create_funded_wallet()
        withdrawn = balance(wallet_key)
        platform_transit = ObjectGenerator.get_client_account_key(PLATFORM_CLIENT, "TRANSIT")
        platform_cash = ObjectGenerator.get_client_account_key(PLATFORM_CLIENT, "CASH")
        platform_transit_before = balance(platform_transit)
        platform_cash_before = balance(platform_cash)

        status, payout, _payload = ObjectGenerator.create_payout(wallet_key, amount_in_cents=withdrawn)
        assert status == 202, payout
        assert payout["outbox"]["outbox_status"] == "sent", payout

        status, response, _payload = ObjectGenerator.create_settlement(payout["outbox"])

        assert status == 204, response
        assert balance(wallet_key) == 0
        assert balance(platform_transit) - platform_transit_before == 0
        assert balance(platform_cash) - platform_cash_before == -withdrawn

        status, integrity = RequestGenerator.GET_integrity({"client_key": PLATFORM_CLIENT})
        assert status == 200, integrity
        assert integrity["difference_in_cents"] == 0
