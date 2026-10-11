from uuid import uuid4

from tests.utils import ObjectGenerator, PayloadGenerator, RequestGenerator

ALFA_CLIENT = "c1c1c1c1-c1c1-4c1c-8c1c-c1c1c1c1c1c1"
LANDLORD = "22222222-2222-4222-8222-222222222222"
PLATFORM = "99999999-9999-4999-8999-999999999999"
EARMARKS = ["RENT", "IPTU", "CONDO", "WATER", "ELECTRICITY"]


def provision_contract(**kwargs) -> dict:
    """Provisiona um contrato novo e devolve o corpo do provisionamento."""
    status, contract_ledger = ObjectGenerator.create_contract_ledger(**kwargs)
    assert status == 201, contract_ledger

    return contract_ledger


def account_keys(contract_ledger: dict) -> dict:
    """A chave de cada conta do contrato, pelo propósito (um de cada no caso do 05)."""
    return {account["purpose_code"]: account["ledger_account_key"] for account in contract_ledger["accounts"]}


def balance(ledger_account_key: str) -> int:
    status, ledger_account = RequestGenerator.GET_ledger_account(ledger_account_key)
    assert status == 200, ledger_account

    return ledger_account["balance_in_cents"]


def inflow(contract_key: str, **kwargs) -> dict:
    status, response, _payload = ObjectGenerator.create_inflow(contract_key, **kwargs)
    assert status == 201, response

    return response


def split(contract_key: str, **kwargs) -> dict:
    status, response, _payload = ObjectGenerator.create_split(contract_key, **kwargs)
    assert status == 201, response

    return response


def trace(ledger_transaction_key: str) -> dict:
    status, response = RequestGenerator.GET_transfer_trace(ledger_transaction_key)
    assert status == 200, response

    return response


def legs(entries: list) -> list:
    return [(entry["direction"], entry["purpose_code"], entry["amount_in_cents"]) for entry in entries]


def debits_and_credits(entries: list) -> tuple:
    debits = sum(entry["amount_in_cents"] for entry in entries if entry["direction"] == "D")
    credits = sum(entry["amount_in_cents"] for entry in entries if entry["direction"] == "C")

    return debits, credits


class TestSplitCreate:
    def test_transfers_split_divides_by_snapshot(self):
        contract_ledger = provision_contract()
        contract_key = contract_ledger["contract_key"]
        keys = account_keys(contract_ledger)
        inflow(contract_key)

        response = split(contract_key)

        assert response["ledger_transaction_type"] == "split"
        assert response["split_version"] == 1
        assert response["contract_key"] == contract_key
        assert response["period_reference"] == "2026-09"
        assert response["payer_party_key"] is None
        assert response["end_to_end_id"] is None
        entries = trace(response["ledger_transaction_key"])["entries"]
        assert legs(entries) == [
            ("D", "COLLECTION", 640000),
            ("D", "OWN", 5000),
            ("C", "RENT", 450000),
            ("C", "OWN", 50000),
            ("C", "IPTU", 30000),
            ("C", "CONDO", 80000),
            ("C", "WATER", 12000),
            ("C", "ELECTRICITY", 18000),
            ("C", "PLATFORM_FEE", 5000),
        ]
        assert [entry["ledger_account_key"] for entry in entries] == [
            keys["COLLECTION"], keys["OWN"], keys["RENT"], keys["OWN"], keys["IPTU"],
            keys["CONDO"], keys["WATER"], keys["ELECTRICITY"], keys["PLATFORM_FEE"],
        ]
        assert (entries[2]["owner_party_key"], entries[2]["owner_role"]) == (LANDLORD, "landlord")
        assert (entries[8]["owner_party_key"], entries[8]["owner_role"]) == (PLATFORM, "platform")
        assert debits_and_credits(entries) == (645000, 645000)
        assert balance(keys["COLLECTION"]) == 0
        credited = {"RENT": 450000, "IPTU": 30000, "CONDO": 80000, "WATER": 12000, "ELECTRICITY": 18000}
        for purpose_code in EARMARKS:
            assert balance(keys[purpose_code]) == credited[purpose_code], purpose_code
        status, integrity = RequestGenerator.GET_integrity({"client_key": ALFA_CLIENT})
        assert status == 200, integrity
        assert integrity["difference_in_cents"] == 0

    def test_transfers_split_credits_platform_revenue(self):
        contract_ledger = provision_contract()
        contract_key = contract_ledger["contract_key"]
        keys = account_keys(contract_ledger)
        inflow(contract_key)
        own_before = balance(keys["OWN"])
        revenue_before = balance(keys["PLATFORM_FEE"])

        split(contract_key)

        assert balance(keys["PLATFORM_FEE"]) - revenue_before == 5000
        assert balance(keys["OWN"]) - own_before == 45000

    def test_transfers_split_chain_follows_inflow(self):
        contract_key = provision_contract()["contract_key"]
        first = inflow(contract_key, value_date="2026-09-05T14:22:00Z")

        second = split(contract_key, value_date="2026-09-05T14:23:00Z")

        chain = trace(second["ledger_transaction_key"])["chain"]
        assert [link["ledger_transaction_key"] for link in chain] == [
            first["ledger_transaction_key"],
            second["ledger_transaction_key"],
        ]
        assert [link["ledger_transaction_type"] for link in chain] == ["inflow", "split"]
        assert [len(link["entries"]) for link in chain] == [2, 9]
        assert chain[1]["value_date"] == "2026-09-05T14:23:00Z"

    def test_transfers_split_zero_fee_has_no_leg(self):
        contract_ledger = provision_contract(platform_fee_percentage="0.0000")
        contract_key = contract_ledger["contract_key"]
        inflow(contract_key)

        response = split(contract_key)

        entries = trace(response["ledger_transaction_key"])["entries"]
        assert legs(entries) == [
            ("D", "COLLECTION", 640000),
            ("C", "RENT", 450000),
            ("C", "OWN", 50000),
            ("C", "IPTU", 30000),
            ("C", "CONDO", 80000),
            ("C", "WATER", 12000),
            ("C", "ELECTRICITY", 18000),
        ]
        assert debits_and_credits(entries) == (640000, 640000)

    def test_transfers_split_partial_payment_refused(self):
        contract_ledger = provision_contract()
        contract_key = contract_ledger["contract_key"]
        keys = account_keys(contract_ledger)
        inflow(contract_key, amount_in_cents=320000)

        status, response, _payload = ObjectGenerator.create_split(contract_key)

        assert status == 422, response
        assert response["code"] == "QIT001009"
        assert balance(keys["COLLECTION"]) == 320000
        assert balance(keys["RENT"]) == 0

        inflow(contract_key, amount_in_cents=320000)

        status, response, _payload = ObjectGenerator.create_split(contract_key, idempotency_key=str(uuid4()))

        assert status == 201, response
        assert balance(keys["COLLECTION"]) == 0
        assert balance(keys["RENT"]) == 450000

    def test_transfers_split_same_period_twice_conflicts(self):
        contract_ledger = provision_contract()
        contract_key = contract_ledger["contract_key"]
        keys = account_keys(contract_ledger)
        inflow(contract_key)
        split(contract_key)

        status, response, _payload = ObjectGenerator.create_split(contract_key, idempotency_key=str(uuid4()))

        assert status == 409, response
        assert response["code"] == "QIT001036"
        assert balance(keys["RENT"]) == 450000

    def test_transfers_split_replays_same_key(self):
        contract_ledger = provision_contract()
        contract_key = contract_ledger["contract_key"]
        keys = account_keys(contract_ledger)
        inflow(contract_key)
        idempotency_key = str(uuid4())
        first = split(contract_key, idempotency_key=idempotency_key)

        status, response, _payload = ObjectGenerator.create_split(contract_key, idempotency_key=idempotency_key)

        assert status == 201, response
        assert response["ledger_transaction_key"] == first["ledger_transaction_key"]
        assert balance(keys["RENT"]) == 450000

    def test_transfers_split_unknown_contract_returns_404(self):
        status, response, _payload = ObjectGenerator.create_split(str(uuid4()))

        assert status == 404, response
        assert response["code"] == "QIT001035"

    def test_transfers_split_refuses_malformed_body(self):
        contract_key = provision_contract()["contract_key"]
        valid = PayloadGenerator.create_split_payload(contract_key)

        without_actor = dict(valid)
        del without_actor["actor"]
        malformed = [
            (valid, None),
            (valid, "k" * 256),
            (without_actor, str(uuid4())),
            (dict(valid, period_reference="2026-9"), str(uuid4())),
            (dict(valid, amount_in_cents=640000), str(uuid4())),
            (dict(valid, value_date="2026-02-30T00:00:00Z"), str(uuid4())),
        ]

        for payload, idempotency_key in malformed:
            status, response = RequestGenerator.POST_transfers_split(payload, idempotency_key=idempotency_key)

            assert status == 400, (payload, idempotency_key, response)
            assert response["code"] == "QIT000001", (payload, idempotency_key, response)
