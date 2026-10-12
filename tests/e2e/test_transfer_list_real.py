"""Cópia de tests/integration/transfer/test_transfer_list.py contra o Cadastro
de verdade. O original continua intacto, contra o party-mock.

A única mudança é a origem do dono da RENT repassada por Pix: a Ana (2222…)
vira a "aprovada" criada pela fixture `party_scenarios`. O Bruno (3333…) fica:
ele é só o pagador das entradas, e o Ledger nunca o envia ao Cadastro.
"""
from uuid import uuid4

from tests.utils import DbUtils, ObjectGenerator, RequestGenerator
from tests.utils.party_scenarios import APROVADA

BRUNO = "33333333-3333-4333-8333-333333333333"


def trace(ledger_transaction_key: str) -> dict:
    status, response = RequestGenerator.GET_transfer_trace(ledger_transaction_key)
    assert status == 200, response

    return response


class TestTransferList:
    def test_transfers_list_by_contract_and_period(self, party_scenarios):
        ANA = party_scenarios[APROVADA]

        contract_ledger, payout = ObjectGenerator.create_paid_out_contract(ANA)
        assert payout["outbox"]["outbox_status"] == "sent", payout
        contract_key = contract_ledger["contract_key"]
        chain_keys = [link["ledger_transaction_key"] for link in trace(payout["ledger_transaction_key"])["chain"]]

        status, response = RequestGenerator.GET_transfers({"contract_key": contract_key, "period_reference": "2026-09"})

        assert status == 200, response
        assert [item["ledger_transaction_type"] for item in response["data"]] == ["inflow", "split", "payout"]
        assert [item["ledger_transaction_key"] for item in response["data"]] == chain_keys
        assert chain_keys[2] == payout["ledger_transaction_key"]
        assert response["is_last_page"] is True

        status, response = RequestGenerator.GET_transfers({"contract_key": contract_key, "period_reference": "2026-10"})

        assert status == 200, response
        assert response["data"] == []

    def test_transfers_list_by_payer_paginated(self):
        DbUtils.rollback()
        inflow_keys = []
        for _ in range(2):
            status, contract_ledger = ObjectGenerator.create_contract_ledger()
            assert status == 201, contract_ledger
            status, inflow, _payload = ObjectGenerator.create_inflow(contract_ledger["contract_key"])
            assert status == 201, inflow
            inflow_keys.append(inflow["ledger_transaction_key"])

        status, response = RequestGenerator.GET_transfers({"payer_party_key": BRUNO, "limit": "1"})

        assert status == 200, response
        assert [item["ledger_transaction_key"] for item in response["data"]] == [inflow_keys[0]]
        assert response["limit"] == 1
        assert response["page"] == 0
        assert response["is_last_page"] is False

        status, response = RequestGenerator.GET_transfers({"payer_party_key": BRUNO, "limit": "1", "page": "1"})

        assert status == 200, response
        assert [item["ledger_transaction_key"] for item in response["data"]] == [inflow_keys[1]]
        assert response["page"] == 1
        assert response["is_last_page"] is True

    def test_transfers_list_refuses_malformed_query(self):
        contract_key = str(uuid4())
        cases = [
            {},
            {"contract_key": contract_key},
            {"payer_party_key": BRUNO, "contract_key": contract_key, "period_reference": "2026-09"},
            {"payer_party_key": BRUNO, "period_reference": "2026-09"},
            {"payer_party_key": BRUNO, "contract_key": contract_key},
            {"contract_key": contract_key, "period_reference": "2026-9"},
            {"payer_party_key": BRUNO, "limit": "101"},
            {"payer_party_key": BRUNO, "client_key": "c1c1c1c1-c1c1-4c1c-8c1c-c1c1c1c1c1c1"},
        ]

        for params in cases:
            status, response = RequestGenerator.GET_transfers(params)

            assert status == 400, (params, response)
            assert response["code"] == "QIT000001", (params, response)
