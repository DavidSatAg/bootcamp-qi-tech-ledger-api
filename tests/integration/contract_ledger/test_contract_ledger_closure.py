from uuid import uuid4

from tests.utils import ObjectGenerator, PayloadGenerator, RequestGenerator


def contract_statuses(contract_key: str) -> list:
    """O status de cada conta do contrato, pela listagem."""
    status, response = RequestGenerator.GET_ledger_accounts({"contract_key": contract_key})
    assert status == 200

    return [account["status"] for account in response["data"]]


class TestContractLedgerClosure:
    def test_contract_ledgers_closure_unknown_contract_returns_404(self):
        status, response = ObjectGenerator.close_contract_ledger(str(uuid4()))

        assert status == 404
        assert response["code"] == "QIT001035"

    def test_contract_ledgers_closure_refuses_malformed_body(self):
        status, contract_ledger = ObjectGenerator.create_contract_ledger()
        assert status == 201
        contract_key = contract_ledger["contract_key"]

        without_actor = PayloadGenerator.create_closure_payload()
        del without_actor["actor"]
        extra_field = PayloadGenerator.create_closure_payload()
        extra_field["status"] = "closed"

        malformed_bodies = [
            without_actor,
            PayloadGenerator.create_closure_payload(actor=""),
            PayloadGenerator.create_closure_payload(reason="x" * 256),
            extra_field,
        ]

        for malformed_body in malformed_bodies:
            status, response = RequestGenerator.POST_contract_ledgers_closure(contract_key, malformed_body)

            assert status == 400, malformed_body
            assert response["code"] == "QIT000001"

        assert contract_statuses(contract_key) == ["active"] * 6
