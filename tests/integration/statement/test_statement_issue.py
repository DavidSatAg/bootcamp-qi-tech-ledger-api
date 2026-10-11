import re
from uuid import UUID, uuid4

from tests.utils import ObjectGenerator, PayloadGenerator, RequestGenerator

BRUNO = "33333333-3333-4333-8333-333333333333"
TX1_VALUE_DATE = "2026-09-05T14:22:00Z"


def provision_contract() -> tuple:
    """Provisiona um contrato novo e devolve (contract_key, {purpose_code: ledger_account_key})."""
    status, contract_ledger = ObjectGenerator.create_contract_ledger()
    assert status == 201, contract_ledger

    accounts = {account["purpose_code"]: account["ledger_account_key"] for account in contract_ledger["accounts"]}

    return contract_ledger["contract_key"], accounts


def provision_with_tx1() -> tuple:
    """O contrato com a TX1 de setembro; devolve (contract_key, chave da COLLECTION)."""
    contract_key, accounts = provision_contract()
    status, inflow, _payload = ObjectGenerator.create_inflow(contract_key, value_date=TX1_VALUE_DATE)
    assert status == 201, inflow

    return contract_key, accounts["COLLECTION"]


class TestStatementIssue:
    def test_statement_issues_with_hash(self):
        contract_key, collection_key = provision_with_tx1()

        status, response, _payload = ObjectGenerator.create_statement(collection_key)

        assert status == 201, response
        assert str(UUID(response["statement_key"])) == response["statement_key"]
        assert re.fullmatch("[0-9a-f]{64}", response["content_hash"])
        assert response["ledger_account_key"] == collection_key
        assert len(response["lines"]) == 1
        line = response["lines"][0]
        assert line["direction"] == "C"
        assert line["amount_in_cents"] == 640000
        assert line["transaction_type"] == "inflow"
        assert line["payer_party_key"] == BRUNO
        assert line["contract_key"] == contract_key
        assert line["value_date"] == TX1_VALUE_DATE
        assert response["opening_balance_in_cents"] == 0
        assert response["total_debit_in_cents"] == 0
        assert response["total_credit_in_cents"] == 640000
        assert response["closing_balance_in_cents"] == 640000

    def test_statement_empty_account_has_zero_totals(self):
        _contract_key, accounts = provision_contract()

        status, response, _payload = ObjectGenerator.create_statement(accounts["RENT"])

        assert status == 201, response
        assert response["lines"] == []
        assert response["opening_balance_in_cents"] == 0
        assert response["total_debit_in_cents"] == 0
        assert response["total_credit_in_cents"] == 0
        assert response["closing_balance_in_cents"] == 0

    def test_statement_same_period_conflicts(self):
        _contract_key, collection_key = provision_with_tx1()
        status, original, _payload = ObjectGenerator.create_statement(collection_key)
        assert status == 201, original

        periods = [
            ("2026-09-01T00:00:00Z", "2026-10-01T00:00:00Z"),
            ("2026-09-15T00:00:00Z", "2026-10-15T00:00:00Z"),
        ]

        for period_start, period_end in periods:
            status, response, _payload = ObjectGenerator.create_statement(
                collection_key, period_start=period_start, period_end=period_end
            )

            assert status == 409, (period_start, period_end, response)
            assert response["code"] == "QIT001017", (period_start, period_end, response)

    def test_statement_late_entry_issues_successor(self):
        contract_key, collection_key = provision_with_tx1()
        status, original, _payload = ObjectGenerator.create_statement(collection_key)
        assert status == 201, original
        status, late_inflow, _payload = ObjectGenerator.create_inflow(contract_key, value_date=TX1_VALUE_DATE)
        assert status == 201, late_inflow

        status, successor, _payload = ObjectGenerator.create_statement(collection_key)

        assert status == 201, successor
        assert successor["supersedes_statement_key"] == original["statement_key"]
        assert successor["previous_statement_key"] == original["statement_key"]
        assert len(successor["lines"]) == 2
        assert successor["content_hash"] != original["content_hash"]

    def test_statement_second_successor_conflicts(self):
        contract_key, collection_key = provision_with_tx1()
        status, original, _payload = ObjectGenerator.create_statement(collection_key)
        assert status == 201, original
        status, late_inflow, _payload = ObjectGenerator.create_inflow(contract_key, value_date=TX1_VALUE_DATE)
        assert status == 201, late_inflow
        status, successor, _payload = ObjectGenerator.create_statement(collection_key)
        assert status == 201, successor

        status, response, _payload = ObjectGenerator.create_statement(collection_key)

        assert status == 409, response
        assert response["code"] == "QIT001017"

        status, response = RequestGenerator.GET_statement(original["statement_key"])

        assert status == 200, response
        assert response["superseded_by_statement_key"] == successor["statement_key"]

    def test_statement_replays_same_key(self):
        _contract_key, collection_key = provision_with_tx1()
        payload = PayloadGenerator.create_statement_payload(collection_key)
        idempotency_key = str(uuid4())

        first_status, first_response = RequestGenerator.POST_statement(payload, idempotency_key=idempotency_key)
        second_status, second_response = RequestGenerator.POST_statement(payload, idempotency_key=idempotency_key)

        assert first_status == 201, first_response
        assert second_status == 201, second_response
        assert second_response == first_response

        other_actor = PayloadGenerator.create_statement_payload(collection_key, actor="erp-beta")
        status, response = RequestGenerator.POST_statement(other_actor, idempotency_key=idempotency_key)

        assert status == 409, response
        assert response["code"] == "QIT001010"

    def test_statement_unknown_account_returns_404(self):
        status, response, _payload = ObjectGenerator.create_statement(str(uuid4()))

        assert status == 404, response
        assert response["code"] == "QIT001018"

    def test_statement_refuses_malformed_request(self):
        _contract_key, accounts = provision_contract()
        collection_key = accounts["COLLECTION"]

        without_actor = PayloadGenerator.create_statement_payload(collection_key)
        del without_actor["actor"]
        extra_field = PayloadGenerator.create_statement_payload(collection_key)
        extra_field["extra"] = "x"
        impossible_date = PayloadGenerator.create_statement_payload(collection_key, period_start="2026-02-30T00:00:00Z")
        empty_period = PayloadGenerator.create_statement_payload(
            collection_key, period_start="2026-09-01T00:00:00Z", period_end="2026-09-01T00:00:00Z"
        )

        cases = [
            (PayloadGenerator.create_statement_payload(collection_key), None),
            (without_actor, str(uuid4())),
            (extra_field, str(uuid4())),
            (impossible_date, str(uuid4())),
            (empty_period, str(uuid4())),
        ]

        for payload, idempotency_key in cases:
            status, response = RequestGenerator.POST_statement(payload, idempotency_key=idempotency_key)

            assert status == 400, (payload, idempotency_key, response)
            assert response["code"] == "QIT000001", (payload, idempotency_key, response)
