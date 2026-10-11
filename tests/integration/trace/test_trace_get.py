from uuid import uuid4

from tests.utils import ObjectGenerator, RequestGenerator

BRUNO = "33333333-3333-4333-8333-333333333333"


def provision_contract() -> tuple:
    """Provisiona um contrato novo e devolve (contract_key, chave da COLLECTION)."""
    status, contract_ledger = ObjectGenerator.create_contract_ledger()
    assert status == 201, contract_ledger

    collection = contract_ledger["accounts"][0]
    assert collection["purpose_code"] == "COLLECTION"

    return contract_ledger["contract_key"], collection["ledger_account_key"]


class TestTraceGet:
    def test_transfers_trace_returns_legs(self):
        contract_key, collection_key = provision_contract()
        status, inflow, payload = ObjectGenerator.create_inflow(contract_key, value_date="2026-09-05T14:22:00Z")
        assert status == 201, inflow
        ledger_transaction_key = inflow["ledger_transaction_key"]

        status, response = RequestGenerator.GET_transfer_trace(ledger_transaction_key)

        assert status == 200, response
        transaction = response["transaction"]
        assert transaction["ledger_transaction_key"] == ledger_transaction_key
        assert transaction["ledger_transaction_type"] == "inflow"
        assert transaction["value_date"] == "2026-09-05T14:22:00Z"
        assert transaction["contract_key"] == contract_key
        assert transaction["period_reference"] == "2026-09"
        assert transaction["split_version"] is None
        assert transaction["payer_party_key"] == BRUNO
        assert transaction["end_to_end_id"] == payload["end_to_end_id"]
        assert transaction["reverses_transaction_key"] is None
        assert transaction["actor"] == "erp-alfa"
        assert transaction["reason"] is None
        assert isinstance(transaction["trace_id"], str) and transaction["trace_id"] != ""

        entries = response["entries"]
        assert len(entries) == 2
        assert entries[0]["direction"] == "D"
        assert entries[0]["amount_in_cents"] == 640000
        assert entries[0]["ledger_account_type"] == "external"
        assert entries[0]["purpose_code"] == "CASH"
        assert entries[1]["direction"] == "C"
        assert entries[1]["amount_in_cents"] == 640000
        assert entries[1]["ledger_account_key"] == collection_key
        assert entries[1]["purpose_code"] == "COLLECTION"
        for entry in entries:
            assert entry["owner_party_key"] is None
            assert entry["owner_role"] is None

    def test_transfers_trace_chain_same_contract_and_period(self):
        contract_key, _collection_key = provision_contract()
        status, inflow_a, _payload = ObjectGenerator.create_inflow(
            contract_key, amount_in_cents=320000, value_date="2026-09-05T14:23:00Z"
        )
        assert status == 201, inflow_a
        status, inflow_b, _payload = ObjectGenerator.create_inflow(
            contract_key, amount_in_cents=320000, value_date="2026-09-05T14:22:00Z"
        )
        assert status == 201, inflow_b
        status, inflow_c, _payload = ObjectGenerator.create_inflow(contract_key, period_reference="2026-10")
        assert status == 201, inflow_c
        key_a = inflow_a["ledger_transaction_key"]
        key_b = inflow_b["ledger_transaction_key"]
        key_c = inflow_c["ledger_transaction_key"]

        status, trace_a = RequestGenerator.GET_transfer_trace(key_a)

        assert status == 200, trace_a
        chain = trace_a["chain"]
        assert [link["ledger_transaction_key"] for link in chain] == [key_b, key_a]
        assert chain[0]["value_date"] == "2026-09-05T14:22:00Z"
        assert chain[1]["value_date"] == "2026-09-05T14:23:00Z"
        for link in chain:
            assert link["ledger_transaction_type"] == "inflow"
            assert link["payer_party_key"] == BRUNO
            assert link["reverses_transaction_key"] is None
            assert link["outbox_key"] is None
            assert link["outbox_status"] is None
            assert [entry["direction"] for entry in link["entries"]] == ["D", "C"]
            assert [entry["amount_in_cents"] for entry in link["entries"]] == [320000, 320000]

        status, trace_b = RequestGenerator.GET_transfer_trace(key_b)

        assert status == 200, trace_b
        assert trace_b["chain"] == chain

        status, trace_c = RequestGenerator.GET_transfer_trace(key_c)

        assert status == 200, trace_c
        assert [link["ledger_transaction_key"] for link in trace_c["chain"]] == [key_c]
        assert len(trace_c["chain"][0]["entries"]) == 2

    def test_transfers_trace_unknown_returns_404(self):
        unknown_key = str(uuid4())

        status, response = RequestGenerator.GET_transfer_trace(unknown_key)

        assert status == 404, response
        assert response["code"] == "QIT001020"
