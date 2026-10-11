from uuid import uuid4

from tests.utils import ObjectGenerator, PayloadGenerator, RequestGenerator


def provision_contract(**kwargs) -> dict:
    """Provisiona um contrato novo e devolve o corpo do provisionamento."""
    status, contract_ledger = ObjectGenerator.create_contract_ledger(**kwargs)
    assert status == 201, contract_ledger

    return contract_ledger


class TestSplitCreate:
    def test_transfers_split_unknown_contract_returns_404(self):
        status, response, _payload = ObjectGenerator.create_split(str(uuid4()))

        assert status == 404, response
        assert response["code"] == "QIT001035"

    def test_transfers_split_refuses_malformed_body(self):
        contract_key = provision_contract()["contract_key"]
        valid = PayloadGenerator.create_split_payload(contract_key)

        without_actor = dict(valid)
        del without_actor["actor"]
        malformed = [
            (valid, None),
            (valid, "k" * 256),
            (without_actor, str(uuid4())),
            (dict(valid, period_reference="2026-9"), str(uuid4())),
            (dict(valid, amount_in_cents=640000), str(uuid4())),
            (dict(valid, value_date="2026-02-30T00:00:00Z"), str(uuid4())),
        ]

        for payload, idempotency_key in malformed:
            status, response = RequestGenerator.POST_transfers_split(payload, idempotency_key=idempotency_key)

            assert status == 400, (payload, idempotency_key, response)
            assert response["code"] == "QIT000001", (payload, idempotency_key, response)
