from uuid import uuid4

from tests.utils import DbUtils, ObjectGenerator, RequestGenerator

ALFA_CLIENT = "c1c1c1c1-c1c1-4c1c-8c1c-c1c1c1c1c1c1"
ANA = "22222222-2222-4222-8222-222222222222"


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

    def test_ledger_accounts_list_by_owner(self):
        DbUtils.rollback()
        status, contract_ledger = ObjectGenerator.create_contract_ledger()
        assert status == 201
        rent_key = account_key_by_purpose(contract_ledger, "RENT")

        status, response = RequestGenerator.GET_ledger_accounts({"owner_party_key": ANA})

        assert status == 200
        assert response["limit"] == 10
        assert response["page"] == 0
        assert response["is_last_page"] is True
        assert len(response["data"]) == 1
        assert response["data"][0]["ledger_account_key"] == rent_key
        assert response["data"][0]["purpose_code"] == "RENT"
        assert response["data"][0]["owner_role"] == "landlord"
        assert "status_events" not in response["data"][0]

    def test_ledger_accounts_list_refuses_bad_query(self):
        bad_queries = [
            {"client_key": ALFA_CLIENT, "limit": 101},
            {"client_key": ALFA_CLIENT, "campo_que_nao_existe": "1"},
            {"client_key": ALFA_CLIENT, "owner_party_key": ANA},
            {},
        ]

        for bad_query in bad_queries:
            status, response = RequestGenerator.GET_ledger_accounts(bad_query)

            assert status == 400, f"a consulta {bad_query} foi aceita"
            assert response["code"] == "QIT000001"
