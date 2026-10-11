from uuid import uuid4

from tests.utils import ObjectGenerator, RequestGenerator

ALFA_CLIENT = "c1c1c1c1-c1c1-4c1c-8c1c-c1c1c1c1c1c1"
PLATFORM_CLIENT = "9c9c9c9c-9c9c-49c9-89c9-9c9c9c9c9c9c"
ANA = "22222222-2222-4222-8222-222222222222"
INEXISTENTE = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
OTHER_AMOUNT = 80000


def account_key(contract_ledger: dict, purpose_code: str) -> str:
    """A chave da conta do contrato com esse propósito, no corpo do provisionamento."""
    for account in contract_ledger["accounts"]:
        if account["purpose_code"] == purpose_code:
            return account["ledger_account_key"]

    raise AssertionError(contract_ledger)


def balance(ledger_account_key: str) -> int:
    status, ledger_account = RequestGenerator.GET_ledger_account(ledger_account_key)
    assert status == 200, ledger_account

    return ledger_account["balance_in_cents"]


def open_wallet() -> str:
    """A carteira W da Ana, aberta agora ou reencontrada."""
    status, wallet = ObjectGenerator.open_wallet(ANA)
    assert status in (200, 201), wallet

    return wallet["ledger_account_key"]


def entries_of(ledger_transaction_key: str) -> list:
    status, response = RequestGenerator.GET_transfer_trace(ledger_transaction_key)
    assert status == 200, response

    return response["entries"]


def difference_in_cents(client_key: str) -> int:
    status, integrity = RequestGenerator.GET_integrity({"client_key": client_key})
    assert status == 200, integrity

    return integrity["difference_in_cents"]


class TestWalletPayout:
    def test_transfers_payout_wallet_four_legs(self):
        wallet_key = open_wallet()
        rent = account_key(ObjectGenerator.create_divided_contract(ANA), "RENT")
        platform_cash = ObjectGenerator.get_client_account_key(PLATFORM_CLIENT, "CASH")
        alfa_cash = ObjectGenerator.get_client_account_key(ALFA_CLIENT, "CASH")
        wallet_before = balance(wallet_key)

        status, response, _payload = ObjectGenerator.create_payout(rent, destination="wallet")

        assert status == 201, response
        assert response["ledger_transaction_type"] == "payout"
        assert response["period_reference"] == "2026-09"
        assert response["outbox"] is None
        assert balance(rent) == 0
        assert balance(wallet_key) == wallet_before + 450000

        entries = entries_of(response["ledger_transaction_key"])
        assert [
            (entry["direction"], entry["purpose_code"], entry["amount_in_cents"], entry["ledger_account_key"])
            for entry in entries
        ] == [
            ("D", "RENT", 450000, rent),
            ("D", "CASH", 450000, platform_cash),
            ("C", "WALLET", 450000, wallet_key),
            ("C", "CASH", 450000, alfa_cash),
        ]
        assert (entries[0]["owner_party_key"], entries[0]["owner_role"]) == (ANA, "landlord")
        assert (entries[2]["owner_party_key"], entries[2]["owner_role"]) == (ANA, "holder")

        assert difference_in_cents(ALFA_CLIENT) == 0
        assert difference_in_cents(PLATFORM_CLIENT) == 0

    def test_transfers_payout_wallet_owner_without_wallet(self):
        rent = account_key(ObjectGenerator.create_divided_contract(INEXISTENTE), "RENT")
        idempotency_key = str(uuid4())

        status, response, _payload = ObjectGenerator.create_payout(
            rent, idempotency_key=idempotency_key, destination="wallet"
        )

        assert status == 404, response
        assert response["code"] == "QIT001041"

        status, response, _payload = ObjectGenerator.create_payout(
            rent, idempotency_key=idempotency_key, destination="wallet"
        )

        assert status == 404, response
        assert response["code"] == "QIT001041"

        status, response, _payload = ObjectGenerator.create_payout(
            rent, idempotency_key=idempotency_key, destination="wallet", amount_in_cents=OTHER_AMOUNT
        )

        assert status == 409, response
        assert response["code"] == "QIT001010"
        assert balance(rent) == 450000

    def test_transfers_payout_wallet_forbidden_origin_refused(self):
        wallet_key = open_wallet()
        status, contract_ledger = ObjectGenerator.create_contract_ledger()
        assert status == 201, contract_ledger
        collection = account_key(contract_ledger, "COLLECTION")
        status, response, _payload = ObjectGenerator.create_inflow(contract_ledger["contract_key"])
        assert status == 201, response
        wallet_before = balance(wallet_key)

        cases = [
            (collection, 640000),
            (wallet_key, 450000),
        ]

        for source_account_key, amount_in_cents in cases:
            status, response, _payload = ObjectGenerator.create_payout(
                source_account_key, destination="wallet", amount_in_cents=amount_in_cents
            )

            assert status == 422, (source_account_key, response)
            assert response["code"] == "QIT001008", (source_account_key, response)

        assert balance(collection) == 640000
        assert balance(wallet_key) == wallet_before
