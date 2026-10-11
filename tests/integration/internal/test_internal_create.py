from uuid import uuid4

from tests.utils import ObjectGenerator, PayloadGenerator, RequestGenerator


def provision_contract(**kwargs) -> dict:
    """Provisiona um contrato novo e devolve a chave de cada conta, pelo propósito."""
    status, contract_ledger = ObjectGenerator.create_contract_ledger(**kwargs)
    assert status == 201, contract_ledger

    keys = {account["purpose_code"]: account["ledger_account_key"] for account in contract_ledger["accounts"]}
    keys["contract_key"] = contract_ledger["contract_key"]

    return keys


class TestInternalCreate:
    def test_transfers_internal_refuses_malformed_body(self):
        """O `value_date` impossível só é conferido depois das contas (RN-02):
        por isso as duas existem, COLLECTION → RENT de um contrato."""
        keys = provision_contract()
        valid = PayloadGenerator.create_internal_payload(keys["COLLECTION"], keys["RENT"])
        without_actor = dict(valid)
        del without_actor["actor"]
        without_reason = dict(valid)
        del without_reason["reason"]
        two_remainders = dict(valid, allocations=valid["allocations"] * 2)
        cases = [
            (valid, None),
            (valid, "k" * 256),
            (without_actor, str(uuid4())),
            (without_reason, str(uuid4())),
            (dict(valid, gross_amount_in_cents=0), str(uuid4())),
            (dict(valid, allocations=[]), str(uuid4())),
            (two_remainders, str(uuid4())),
            (dict(valid, amount_in_cents=45000), str(uuid4())),
            (dict(valid, value_date="2026-02-30T00:00:00Z"), str(uuid4())),
        ]

        for payload, idempotency_key in cases:
            status, response = RequestGenerator.POST_transfers_internal(payload, idempotency_key=idempotency_key)

            assert status == 400, (payload, idempotency_key, response)
            assert response["code"] == "QIT000001", (payload, idempotency_key, response)
