from uuid import uuid4

from tests.utils import ObjectGenerator, PayloadGenerator, RequestGenerator


def provision_contract() -> dict:
    """Provisiona um contrato novo e devolve a chave de cada conta, pelo propósito."""
    status, contract_ledger = ObjectGenerator.create_contract_ledger()
    assert status == 201, contract_ledger

    keys = {account["purpose_code"]: account["ledger_account_key"] for account in contract_ledger["accounts"]}
    keys["contract_key"] = contract_ledger["contract_key"]

    return keys


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
