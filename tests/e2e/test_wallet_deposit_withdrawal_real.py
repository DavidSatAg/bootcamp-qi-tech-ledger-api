"""Cópia de tests/integration/wallet/test_wallet_deposit_withdrawal.py contra o
Cadastro de verdade. O original continua intacto, contra o party-mock.

A mudança é a origem dos dados da pessoa: a Ana (2222…) vira a "aprovada"
criada pela fixture `party_scenarios`, inclusive no `create_funded_wallet`,
que sem argumento cairia no 2222… do valor padrão. A pix_key esperada no
despacho ao provedor deixa de ser o literal do party-mock e passa a ser a que
o seed cadastrou para a "aprovada" (`SCENARIOS`). O provedor continua mock no
ponto de integração (01b §0.2), e por isso o diário dele segue valendo.
"""
from uuid import uuid4

from tests.utils import ObjectGenerator, RequestGenerator
from tests.utils.party_scenarios import APROVADA, SCENARIOS

PLATFORM_CLIENT = "9c9c9c9c-9c9c-49c9-89c9-9c9c9c9c9c9c"
OTHER_AMOUNT = 80000

# A pix_key com que o seed cadastra a "aprovada": (final, pix_key, status).
APROVADA_PIX_KEY = SCENARIOS[APROVADA][1]


def balance(ledger_account_key: str) -> int:
    status, ledger_account = RequestGenerator.GET_ledger_account(ledger_account_key)
    assert status == 200, ledger_account

    return ledger_account["balance_in_cents"]


def entries_of(ledger_transaction_key: str) -> list:
    status, response = RequestGenerator.GET_transfer_trace(ledger_transaction_key)
    assert status == 200, response

    return response["entries"]


class TestWalletDepositWithdrawal:
    def test_transfers_inflow_wallet_deposit_credits_wallet(self, party_scenarios):
        ANA = party_scenarios[APROVADA]

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

    def test_transfers_payout_pix_from_wallet_withdraws(self, party_scenarios):
        """O saque é o repasse Pix com origem na carteira, sem código novo
        (remodelagem/10 :130): o dinheiro vai para a TRANSIT da plataforma
        e o provedor recebe um Pix para a chave da Ana."""
        ANA = party_scenarios[APROVADA]

        wallet_key = ObjectGenerator.create_funded_wallet(ANA)
        platform_transit = ObjectGenerator.get_client_account_key(PLATFORM_CLIENT, "TRANSIT")
        wallet_before = balance(wallet_key)
        platform_transit_before = balance(platform_transit)

        status, response, _payload = ObjectGenerator.create_payout(wallet_key, amount_in_cents=wallet_before)

        assert status == 202, response
        outbox = response["outbox"]
        assert outbox["outbox_status"] == "sent", outbox
        assert outbox["beneficiary_party_key"] == ANA
        assert balance(wallet_key) == 0
        assert balance(platform_transit) == platform_transit_before + wallet_before

        dispatches = [
            body
            for _headers, body in RequestGenerator.GET_mock_requests("provider-mock", "/pix")
            if body is not None and body.get("dispatch_idempotency_key") == outbox["dispatch_idempotency_key"]
        ]
        assert len(dispatches) == 1, dispatches
        assert dispatches[0]["pix_key"] == APROVADA_PIX_KEY
        assert dispatches[0]["amount_in_cents"] == wallet_before
