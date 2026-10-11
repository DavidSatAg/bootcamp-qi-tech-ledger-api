from uuid import uuid4

from tests.utils import ObjectGenerator, PayloadGenerator, RequestGenerator

ALFA_CLIENT = "c1c1c1c1-c1c1-4c1c-8c1c-c1c1c1c1c1c1"


def provision_contract() -> dict:
    """Provisiona um contrato novo e devolve a chave de cada conta, pelo propósito."""
    status, contract_ledger = ObjectGenerator.create_contract_ledger()
    assert status == 201, contract_ledger

    keys = {account["purpose_code"]: account["ledger_account_key"] for account in contract_ledger["accounts"]}
    keys["contract_key"] = contract_ledger["contract_key"]

    return keys


def balance(ledger_account_key: str) -> int:
    status, ledger_account = RequestGenerator.GET_ledger_account(ledger_account_key)
    assert status == 200, ledger_account

    return ledger_account["balance_in_cents"]


def clearing_key() -> str:
    """A `clearing/TRANSIT` da Imobiliária Alfa: o destino de todo repasse dela."""
    return ObjectGenerator.get_client_account_key(ALFA_CLIENT, "TRANSIT")


class TestPayoutPix:
    def test_transfers_payout_unknown_source_returns_404(self):
        status, response, _payload = ObjectGenerator.create_payout(str(uuid4()))

        assert status == 404, response
        assert response["code"] == "QIT001018"

    def test_transfers_payout_refuses_malformed_body(self):
        keys = provision_contract()
        rent_key = keys["RENT"]
        valid = PayloadGenerator.create_payout_payload(rent_key)
        without_actor = dict(valid)
        del without_actor["actor"]
        without_period = dict(valid)
        del without_period["period_reference"]
        cases = [
            (valid, None),
            (valid, "k" * 256),
            (PayloadGenerator.create_payout_payload(rent_key, amount_in_cents=0), str(uuid4())),
            (PayloadGenerator.create_payout_payload(rent_key, amount_in_cents="450000"), str(uuid4())),
            (PayloadGenerator.create_payout_payload(rent_key, destination="ted"), str(uuid4())),
            (without_actor, str(uuid4())),
            (without_period, str(uuid4())),
            (PayloadGenerator.create_payout_payload(rent_key, period_reference="2026-9"), str(uuid4())),
            (dict(valid, pix_key="ana.locadora@example.com"), str(uuid4())),
        ]

        for payload, idempotency_key in cases:
            status, response = RequestGenerator.POST_transfers_payout(payload, idempotency_key=idempotency_key)

            assert status == 400, (payload, idempotency_key, response)
            assert response["code"] == "QIT000001", (payload, idempotency_key, response)

    def test_transfers_payout_from_collection_refused(self):
        keys = provision_contract()
        status, response, _payload = ObjectGenerator.create_inflow(keys["contract_key"])
        assert status == 201, response
        clearing_before = balance(clearing_key())

        status, response, _payload = ObjectGenerator.create_payout(keys["COLLECTION"], amount_in_cents=640000)

        assert status == 422, response
        assert response["code"] == "QIT001008"
        assert balance(keys["COLLECTION"]) == 640000
        assert balance(clearing_key()) == clearing_before

    def test_transfers_payout_forbidden_pair_before_balance(self):
        """COLLECTION vazia: o par proibido sai antes da trava e do saldo,
        e a mesma chave repete o 008 gravado."""
        keys = provision_contract()
        idempotency_key = str(uuid4())

        status, response, _payload = ObjectGenerator.create_payout(keys["COLLECTION"], idempotency_key=idempotency_key)

        assert status == 422, response
        assert response["code"] == "QIT001008"

        status, response, _payload = ObjectGenerator.create_payout(keys["COLLECTION"], idempotency_key=idempotency_key)

        assert status == 422, response
        assert response["code"] == "QIT001008"
