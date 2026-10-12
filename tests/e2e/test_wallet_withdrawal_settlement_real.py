"""Cópia de tests/integration/wallet/test_wallet_withdrawal_settlement.py
contra o Cadastro de verdade. O original continua intacto, contra o
party-mock.

A única mudança é a dona da carteira: o `create_funded_wallet()`, que sem
argumento cairia no 2222… do valor padrão, recebe a "aprovada" criada pela
fixture `party_scenarios`. A abertura e o saque por Pix consultam o Cadastro
real.
"""
from tests.utils import ObjectGenerator, RequestGenerator
from tests.utils.party_scenarios import APROVADA

PLATFORM_CLIENT = "9c9c9c9c-9c9c-49c9-89c9-9c9c9c9c9c9c"


def balance(ledger_account_key: str) -> int:
    status, ledger_account = RequestGenerator.GET_ledger_account(ledger_account_key)
    assert status == 200, ledger_account

    return ledger_account["balance_in_cents"]


class TestWalletWithdrawalSettlement:
    def test_webhooks_provider_settles_wallet_withdrawal(self, party_scenarios):
        """A metade "liquidação" do saque (W9; remodelagem/10 :130): o aviso
        do provedor leva o saque da TRANSIT da plataforma para o CASH dela."""
        ANA = party_scenarios[APROVADA]

        wallet_key = ObjectGenerator.create_funded_wallet(ANA)
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
