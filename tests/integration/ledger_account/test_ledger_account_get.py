from uuid import uuid4

from tests.utils import ObjectGenerator, RequestGenerator


def account_key_by_purpose(contract_ledger: dict, purpose_code: str) -> str:
    for account in contract_ledger["accounts"]:
        if account["purpose_code"] == purpose_code:
            return account["ledger_account_key"]

    raise AssertionError(f"o provisionamento não devolveu a conta {purpose_code}")


class TestLedgerAccountGet:
    def test_ledger_accounts_get_returns_balance_by_sum(self):
        status, contract_ledger = ObjectGenerator.create_contract_ledger()
        assert status == 201
        rent_key = account_key_by_purpose(contract_ledger, "RENT")

        status, response = RequestGenerator.GET_ledger_account(rent_key)

        assert status == 200
        assert response["ledger_account_key"] == rent_key
        assert response["contract_key"] == contract_ledger["contract_key"]
        assert response["purpose_code"] == "RENT"
        assert response["owner_party_key"] == "22222222-2222-4222-8222-222222222222"
        assert response["owner_role"] == "landlord"
        assert response["status"] == "active"
        assert response["balance_in_cents"] == 0
        assert len(response["status_events"]) == 1
        assert response["status_events"][0]["status"] == "active"

    def test_ledger_accounts_get_unknown_returns_404(self):
        unknown_key = str(uuid4())

        status, response = RequestGenerator.GET_ledger_account(unknown_key)

        assert status == 404
        assert response["code"] == "QIT001018"
