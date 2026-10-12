from tests.utils import ObjectGenerator, RequestGenerator

PLATFORM_CLIENT = "9c9c9c9c-9c9c-49c9-89c9-9c9c9c9c9c9c"
ANA = "22222222-2222-4222-8222-222222222222"
ALFA_CLIENT = "c1c1c1c1-c1c1-4c1c-8c1c-c1c1c1c1c1c1"


def rent_key(contract_ledger: dict) -> str:
    """A chave da RENT no corpo do provisionamento."""
    for account in contract_ledger["accounts"]:
        if account["purpose_code"] == "RENT":
            return account["ledger_account_key"]

    raise AssertionError(contract_ledger)


def platform_book() -> dict:
    """A conferência do livro da plataforma (9c9c…), onde moram as carteiras."""
    status, integrity = RequestGenerator.GET_integrity({"client_key": PLATFORM_CLIENT})
    assert status == 200, integrity
    assert integrity["client_key"] == PLATFORM_CLIENT

    return integrity


def moved(before: dict, after: dict) -> dict:
    """Quanto o ativo, o passivo e o patrimônio do livro andaram."""
    return {side: after[side] - before[side] for side in ["asset_in_cents", "liability_in_cents", "equity_in_cents"]}


class TestWalletIntegrity:
    def test_integrity_platform_book_closes_after_wallet_flow(self):
        """CU-W10: o livro da plataforma fecha em zero depois de cada passo
        da carteira: o repasse para ela, o depósito e o saque."""
        status, wallet = ObjectGenerator.open_wallet(ANA)
        assert status in (200, 201), wallet
        wallet_key = wallet["ledger_account_key"]
        rent = rent_key(ObjectGenerator.create_divided_contract(ANA))
        before = platform_book()
        assert before["difference_in_cents"] == 0, before

        status, response, _payload = ObjectGenerator.create_payout(rent, destination="wallet")

        assert status == 201, response
        after_payout = platform_book()
        assert after_payout["difference_in_cents"] == 0, after_payout
        assert moved(before, after_payout) == {
            "asset_in_cents": 450000,
            "liability_in_cents": 450000,
            "equity_in_cents": 0,
        }

        status, response, _payload = ObjectGenerator.create_deposit(wallet_key, amount_in_cents=450000)

        assert status == 201, response
        after_deposit = platform_book()
        assert after_deposit["difference_in_cents"] == 0, after_deposit
        assert moved(after_payout, after_deposit) == {
            "asset_in_cents": 450000,
            "liability_in_cents": 450000,
            "equity_in_cents": 0,
        }

        status, response, _payload = ObjectGenerator.create_payout(wallet_key, amount_in_cents=450000)

        assert status == 202, response
        after_withdrawal = platform_book()
        assert after_withdrawal["difference_in_cents"] == 0, after_withdrawal
        # O saque troca passivo por passivo: sai da carteira e entra na
        # `clearing/TRANSIT` da plataforma até a liquidação.
        assert moved(after_deposit, after_withdrawal) == {
            "asset_in_cents": 0,
            "liability_in_cents": 0,
            "equity_in_cents": 0,
        }
        assert after_withdrawal["asset_in_cents"] == (
            after_withdrawal["liability_in_cents"] + after_withdrawal["equity_in_cents"]
        )

        status, alfa_book = RequestGenerator.GET_integrity({"client_key": ALFA_CLIENT})
        assert status == 200, alfa_book
        assert alfa_book["difference_in_cents"] == 0, alfa_book
