from tests.utils import DbUtils, ObjectGenerator, PayloadGenerator, RequestGenerator

ALFA_CLIENT = "c1c1c1c1-c1c1-4c1c-8c1c-c1c1c1c1c1c1"
PLATFORM_CLIENT = "9c9c9c9c-9c9c-49c9-89c9-9c9c9c9c9c9c"
ANA = "22222222-2222-4222-8222-222222222222"
# O condomínio (5555…), ativo e com chave Pix no Cadastro, e cuja carteira
# nenhum outro teste usa: o MED a deixa negativa.
CONDO = "55555555-5555-4555-8555-555555555555"


def rent_key(contract_ledger: dict) -> str:
    """A chave da RENT no corpo do provisionamento."""
    for account in contract_ledger["accounts"]:
        if account["purpose_code"] == "RENT":
            return account["ledger_account_key"]

    raise AssertionError(contract_ledger)


def open_wallet(party_key: str) -> str:
    status, wallet = ObjectGenerator.open_wallet(party_key)
    assert status in (200, 201), wallet

    return wallet["ledger_account_key"]


def balance(ledger_account_key: str) -> int:
    status, ledger_account = RequestGenerator.GET_ledger_account(ledger_account_key)
    assert status == 200, ledger_account

    return ledger_account["balance_in_cents"]


def book(client_key: str) -> dict:
    status, integrity = RequestGenerator.GET_integrity({"client_key": client_key})
    assert status == 200, integrity

    return integrity


def trace(ledger_transaction_key: str) -> dict:
    status, response = RequestGenerator.GET_transfer_trace(ledger_transaction_key)
    assert status == 200, response

    return response


def entry_summary(entries: list) -> list:
    return [
        (entry["direction"], entry["purpose_code"], entry["amount_in_cents"], entry["ledger_account_key"])
        for entry in entries
    ]


class TestWalletReversal:
    def test_transfers_reversal_wallet_payout_total(self):
        """O estorno total do repasse para a carteira (L21): as quatro pernas
        voltam, a RENT recupera os 450000, a carteira os devolve, e os dois
        livros, o do cliente e o da plataforma, fecham em zero."""
        wallet_key = open_wallet(ANA)
        rent = rent_key(ObjectGenerator.create_divided_contract(ANA))
        platform_cash = ObjectGenerator.get_client_account_key(PLATFORM_CLIENT, "CASH")
        alfa_cash = ObjectGenerator.get_client_account_key(ALFA_CLIENT, "CASH")
        wallet_before = balance(wallet_key)
        status, payout, _payload = ObjectGenerator.create_payout(rent, destination="wallet")
        assert status == 201, payout
        assert balance(wallet_key) == wallet_before + 450000

        status, response, _payload = ObjectGenerator.create_reversal(payout["ledger_transaction_key"])

        assert status == 201, response
        assert response["ledger_transaction_type"] == "reversal"
        assert sorted(entry_summary(trace(response["ledger_transaction_key"])["entries"])) == sorted([
            ("C", "RENT", 450000, rent),
            ("C", "CASH", 450000, platform_cash),
            ("D", "WALLET", 450000, wallet_key),
            ("D", "CASH", 450000, alfa_cash),
        ])
        assert balance(rent) == 450000
        assert balance(wallet_key) == wallet_before
        for client_key in [ALFA_CLIENT, PLATFORM_CLIENT]:
            integrity = book(client_key)
            assert integrity["difference_in_cents"] == 0, (client_key, integrity)

    def test_webhooks_provider_med_spent_deposit_goes_negative(self):
        """O MED de um depósito já sacado (L21): 204, a carteira fica
        negativa com o estorno no histórico, e o livro da plataforma fecha
        em zero, sem a carteira entre as negativas suspeitas (D0005)."""
        DbUtils.rollback()
        wallet_key = open_wallet(CONDO)
        status, deposit, deposit_payload = ObjectGenerator.create_deposit(wallet_key, amount_in_cents=450000)
        assert status == 201, deposit
        status, withdrawal, _payload = ObjectGenerator.create_payout(wallet_key, amount_in_cents=450000)
        assert status == 202, withdrawal
        assert balance(wallet_key) == 0

        status, response, _payload = ObjectGenerator.create_med_return(
            deposit_payload["end_to_end_id"], amount_in_cents=450000
        )

        assert status == 204, response
        assert balance(wallet_key) == -450000

        # O depósito não tem contrato, e o trace não tem cadeia para ele
        # (RFC :179): que o MED o estornou inteiro, prova-o o 015 de mais um.
        status, response, _payload = ObjectGenerator.create_reversal(deposit["ledger_transaction_key"])

        assert status == 422, response
        assert response["code"] == "QIT001015"
        integrity = book(PLATFORM_CLIENT)
        assert integrity["difference_in_cents"] == 0, integrity
        assert integrity["negative_accounts"] == [], integrity

        status, response = RequestGenerator.POST_webhooks_provider(
            PayloadGenerator.create_med_payload(deposit_payload["end_to_end_id"], amount_in_cents=450000)
        )

        assert status == 204, response
        assert balance(wallet_key) == -450000
