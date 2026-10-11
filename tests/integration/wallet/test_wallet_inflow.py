from uuid import uuid4

from tests.utils import ObjectGenerator, PayloadGenerator, RequestGenerator

ALFA_CLIENT = "c1c1c1c1-c1c1-4c1c-8c1c-c1c1c1c1c1c1"
PLATFORM_CLIENT = "9c9c9c9c-9c9c-49c9-89c9-9c9c9c9c9c9c"
ANA = "22222222-2222-4222-8222-222222222222"
BRUNO = "33333333-3333-4333-8333-333333333333"
OTHER_AMOUNT = 80000


def account_key(contract_ledger: dict, purpose_code: str) -> str:
    """A chave da conta do contrato com esse propósito, no corpo do provisionamento."""
    for account in contract_ledger["accounts"]:
        if account["purpose_code"] == purpose_code:
            return account["ledger_account_key"]

    raise AssertionError(contract_ledger)


def provision_contract() -> dict:
    status, contract_ledger = ObjectGenerator.create_contract_ledger()
    assert status == 201, contract_ledger

    return contract_ledger


def balance(ledger_account_key: str) -> int:
    status, ledger_account = RequestGenerator.GET_ledger_account(ledger_account_key)
    assert status == 200, ledger_account

    return ledger_account["balance_in_cents"]


def entries_of(ledger_transaction_key: str) -> list:
    status, response = RequestGenerator.GET_transfer_trace(ledger_transaction_key)
    assert status == 200, response

    return response["entries"]


def difference_in_cents(client_key: str) -> int:
    status, integrity = RequestGenerator.GET_integrity({"client_key": client_key})
    assert status == 200, integrity

    return integrity["difference_in_cents"]


class TestWalletInflow:
    def test_transfers_inflow_wallet_pays_collection(self):
        wallet_key = ObjectGenerator.create_funded_wallet()
        contract_ledger = provision_contract()
        collection = account_key(contract_ledger, "COLLECTION")
        platform_cash = ObjectGenerator.get_client_account_key(PLATFORM_CLIENT, "CASH")
        alfa_cash = ObjectGenerator.get_client_account_key(ALFA_CLIENT, "CASH")
        wallet_before = balance(wallet_key)

        status, response, _payload = ObjectGenerator.pay_with_wallet(
            contract_ledger["contract_key"], wallet_key, amount_in_cents=300000
        )

        assert status == 201, response
        assert response["ledger_transaction_type"] == "inflow"
        assert response["payer_party_key"] == ANA
        assert response["end_to_end_id"] is None
        assert balance(wallet_key) == wallet_before - 300000
        assert balance(collection) == 300000

        entries = entries_of(response["ledger_transaction_key"])
        assert [
            (entry["direction"], entry["purpose_code"], entry["amount_in_cents"], entry["ledger_account_key"])
            for entry in entries
        ] == [
            ("D", "WALLET", 300000, wallet_key),
            ("D", "CASH", 300000, alfa_cash),
            ("C", "COLLECTION", 300000, collection),
            ("C", "CASH", 300000, platform_cash),
        ]

        assert difference_in_cents(ALFA_CLIENT) == 0
        assert difference_in_cents(PLATFORM_CLIENT) == 0

    def test_transfers_inflow_wallet_insufficient_balance(self):
        wallet_key = ObjectGenerator.create_funded_wallet()
        contract_ledger = provision_contract()
        collection = account_key(contract_ledger, "COLLECTION")
        wallet_before = balance(wallet_key)

        status, response, _payload = ObjectGenerator.pay_with_wallet(
            contract_ledger["contract_key"], wallet_key, amount_in_cents=wallet_before
        )

        assert status == 201, response
        assert balance(wallet_key) == 0

        status, response, _payload = ObjectGenerator.pay_with_wallet(
            contract_ledger["contract_key"], wallet_key, amount_in_cents=300000
        )

        assert status == 422, response
        assert response["code"] == "QIT001009"
        assert balance(wallet_key) == 0
        assert balance(collection) == wallet_before

    def test_transfers_inflow_wallet_refuses_malformed_body(self):
        contract_key = str(uuid4())
        wallet_key = str(uuid4())
        valid = PayloadGenerator.create_wallet_inflow_payload(contract_key, wallet_key)

        with_payer = dict(valid, payer_party_key=BRUNO)
        with_end_to_end_id = dict(valid, end_to_end_id="E00000000202609051422" + uuid4().hex[:11])
        without_period = dict(valid)
        del without_period["period_reference"]
        without_contract = dict(valid)
        del without_contract["contract_key"]
        short_wallet_key = PayloadGenerator.create_wallet_inflow_payload(contract_key, "abc")

        for payload in [with_payer, with_end_to_end_id, without_period, without_contract, short_wallet_key]:
            status, response = RequestGenerator.POST_transfers_inflow(payload, idempotency_key=str(uuid4()))

            assert status == 400, (payload, response)
            assert response["code"] == "QIT000001", (payload, response)

    def test_transfers_inflow_wallet_unknown_returns_404(self):
        contract_ledger = provision_contract()
        contract_key = contract_ledger["contract_key"]
        collection = account_key(contract_ledger, "COLLECTION")

        idempotency_key = str(uuid4())
        status, response, _payload = ObjectGenerator.pay_with_wallet(
            contract_key, str(uuid4()), idempotency_key=idempotency_key
        )
        unknown_wallet_key = _payload["source_wallet_key"]

        assert status == 404, response
        assert response["code"] == "QIT001018"

        status, response, _payload = ObjectGenerator.pay_with_wallet(
            contract_key, unknown_wallet_key, idempotency_key=idempotency_key, amount_in_cents=OTHER_AMOUNT
        )

        assert status == 409, response
        assert response["code"] == "QIT001010"

        status, response, _payload = ObjectGenerator.pay_with_wallet(
            contract_key, account_key(contract_ledger, "RENT")
        )

        assert status == 404, response
        assert response["code"] == "QIT001018"

        status, wallet = ObjectGenerator.open_wallet(ANA)
        assert status in (200, 201), wallet

        status, response, _payload = ObjectGenerator.pay_with_wallet(str(uuid4()), wallet["ledger_account_key"])

        assert status == 404, response
        assert response["code"] == "QIT001035"
        assert balance(collection) == 0
