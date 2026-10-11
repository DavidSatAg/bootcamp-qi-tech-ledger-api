from tests.utils import ObjectGenerator, RequestGenerator

ALFA_CLIENT = "c1c1c1c1-c1c1-4c1c-8c1c-c1c1c1c1c1c1"


def integrity(params: dict = None) -> dict:
    status, response = RequestGenerator.GET_integrity(params)
    assert status == 200, response

    return response


class TestIntegrityGet:
    def test_integrity_book_closes_after_inflow(self):
        status, contract_ledger = ObjectGenerator.create_contract_ledger()
        assert status == 201, contract_ledger
        before = integrity({"client_key": ALFA_CLIENT})

        status, inflow, _payload = ObjectGenerator.create_inflow(contract_ledger["contract_key"])
        assert status == 201, inflow
        after = integrity({"client_key": ALFA_CLIENT})

        assert after["client_key"] == ALFA_CLIENT
        assert after["asset_in_cents"] - before["asset_in_cents"] == 640000
        assert after["liability_in_cents"] - before["liability_in_cents"] == 640000
        assert after["equity_in_cents"] - before["equity_in_cents"] == 0
        assert after["difference_in_cents"] == 0
        assert after["negative_accounts"] == []

    def test_integrity_general_closes(self):
        status, contract_ledger = ObjectGenerator.create_contract_ledger()
        assert status == 201, contract_ledger
        status, inflow, _payload = ObjectGenerator.create_inflow(contract_ledger["contract_key"])
        assert status == 201, inflow

        response = integrity()

        assert response["client_key"] is None
        assert response["difference_in_cents"] == 0
        assert response["asset_in_cents"] == response["liability_in_cents"] + response["equity_in_cents"]
        assert response["asset_in_cents"] > 0
        assert response["negative_accounts"] == []
