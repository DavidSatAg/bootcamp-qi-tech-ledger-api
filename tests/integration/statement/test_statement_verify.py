from uuid import uuid4

from tests.utils import ObjectGenerator, RequestGenerator

TX1_VALUE_DATE = "2026-09-05T14:22:00Z"


class TestStatementVerify:
    def test_statement_verify_matches_without_token(self):
        status, contract_ledger = ObjectGenerator.create_contract_ledger()
        assert status == 201, contract_ledger
        accounts = {account["purpose_code"]: account["ledger_account_key"] for account in contract_ledger["accounts"]}
        status, inflow, _payload = ObjectGenerator.create_inflow(contract_ledger["contract_key"], value_date=TX1_VALUE_DATE)
        assert status == 201, inflow
        status, statement, _payload = ObjectGenerator.create_statement(accounts["COLLECTION"])
        assert status == 201, statement

        status, response = RequestGenerator.POST_statement_verify({"content_hash": statement["content_hash"]})

        assert status == 200, response
        assert set(response) == {"match", "issued_at"}
        assert response["match"] is True
        assert response["issued_at"] == statement["created_at"]

    def test_statement_verify_malformed_hash_returns_false(self):
        """Um hash emitido, mas malformado (espaço à direita, maiúsculas), não
        casa (decisão A4): só 64 hex minúsculos valem como hash."""
        status, contract_ledger = ObjectGenerator.create_contract_ledger()
        assert status == 201, contract_ledger
        accounts = {account["purpose_code"]: account["ledger_account_key"] for account in contract_ledger["accounts"]}
        status, statement, _payload = ObjectGenerator.create_statement(accounts["RENT"])
        assert status == 201, statement

        for content_hash in [statement["content_hash"] + "   ", statement["content_hash"].upper()]:
            status, response = RequestGenerator.POST_statement_verify({"content_hash": content_hash})

            assert status == 200, (content_hash, response)
            assert response == {"match": False}, (content_hash, response)

    def test_statement_verify_unknown_hash_returns_false(self):
        for content_hash in [uuid4().hex * 2, "abc"]:
            status, response = RequestGenerator.POST_statement_verify({"content_hash": content_hash})

            assert status == 200, (content_hash, response)
            assert response == {"match": False}, (content_hash, response)

        for payload in [{}, {"content_hash": 1}]:
            status, response = RequestGenerator.POST_statement_verify(payload)

            assert status == 400, (payload, response)
            assert response["code"] == "QIT000001", (payload, response)
