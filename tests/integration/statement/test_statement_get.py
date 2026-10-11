from uuid import uuid4

from tests.utils import ObjectGenerator, RequestGenerator

TX1_VALUE_DATE = "2026-09-05T14:22:00Z"


def provision_with_tx1() -> tuple:
    """Um contrato novo com a TX1 de setembro; devolve (contract_key, chave da COLLECTION)."""
    status, contract_ledger = ObjectGenerator.create_contract_ledger()
    assert status == 201, contract_ledger

    accounts = {account["purpose_code"]: account["ledger_account_key"] for account in contract_ledger["accounts"]}

    status, inflow, _payload = ObjectGenerator.create_inflow(contract_ledger["contract_key"], value_date=TX1_VALUE_DATE)
    assert status == 201, inflow

    return contract_ledger["contract_key"], accounts["COLLECTION"]


class TestStatementGet:
    def test_statement_get_hash_is_reproducible(self):
        _contract_key, collection_key = provision_with_tx1()

        status, august, _payload = ObjectGenerator.create_statement(
            collection_key, period_start="2026-08-01T00:00:00Z", period_end="2026-09-01T00:00:00Z"
        )
        assert status == 201, august
        status, september, _payload = ObjectGenerator.create_statement(collection_key)
        assert status == 201, september

        assert september["previous_statement_key"] == august["statement_key"]

        first_status, first_response = RequestGenerator.GET_statement(september["statement_key"])
        second_status, second_response = RequestGenerator.GET_statement(september["statement_key"])

        assert first_status == 200, first_response
        assert second_status == 200, second_response
        assert first_response == second_response
        assert first_response["content_hash"] == september["content_hash"]
        assert first_response["content_hash_matches"] is True

    def test_statement_get_original_unchanged_after_late_entry(self):
        contract_key, collection_key = provision_with_tx1()
        status, original, _payload = ObjectGenerator.create_statement(collection_key)
        assert status == 201, original

        status, late_inflow, _payload = ObjectGenerator.create_inflow(contract_key, value_date=TX1_VALUE_DATE)
        assert status == 201, late_inflow

        status, response = RequestGenerator.GET_statement(original["statement_key"])

        assert status == 200, response
        assert len(response["lines"]) == 1
        assert response["content_hash"] == original["content_hash"]
        assert response["content_hash_matches"] is True

    def test_statement_get_unknown_returns_404(self):
        status, response = RequestGenerator.GET_statement(str(uuid4()))

        assert status == 404, response
        assert response["code"] == "QIT001022"
