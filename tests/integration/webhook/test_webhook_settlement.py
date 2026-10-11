from uuid import uuid4

from tests.utils import ObjectGenerator, PayloadGenerator, RequestGenerator

ALFA_CLIENT = "c1c1c1c1-c1c1-4c1c-8c1c-c1c1c1c1c1c1"


def balance(ledger_account_key: str) -> int:
    status, ledger_account = RequestGenerator.GET_ledger_account(ledger_account_key)
    assert status == 200, ledger_account

    return ledger_account["balance_in_cents"]


def clearing_key() -> str:
    """A `clearing/TRANSIT` da Imobiliária Alfa: por onde passa todo repasse dela."""
    return ObjectGenerator.get_client_account_key(ALFA_CLIENT, "TRANSIT")


def trace(ledger_transaction_key: str) -> dict:
    status, response = RequestGenerator.GET_transfer_trace(ledger_transaction_key)
    assert status == 200, response

    return response


def payout_link(payout: dict) -> dict:
    """O elo do repasse na cadeia do trace dele."""
    for link in trace(payout["ledger_transaction_key"])["chain"]:
        if link["ledger_transaction_key"] == payout["ledger_transaction_key"]:
            return link

    raise AssertionError(payout)


class TestWebhookSettlement:
    def test_webhooks_provider_unknown_outbox_returns_404(self):
        payload = PayloadGenerator.create_webhook_payload(str(uuid4()), "PRV-" + str(uuid4()))

        for _attempt in range(2):
            status, response = RequestGenerator.POST_webhooks_provider(payload)

            assert status == 404, response
            assert response["code"] == "QIT001031"

    def test_webhooks_provider_refuses_malformed_body(self):
        _contract_ledger, payout = ObjectGenerator.create_paid_out_contract()
        outbox = payout["outbox"]
        clearing_before = balance(clearing_key())
        valid = PayloadGenerator.create_webhook_payload(
            outbox["outbox_key"], "PRV-" + outbox["dispatch_idempotency_key"] + "-SETTLED"
        )
        without_reference = dict(valid)
        del without_reference["provider_reference"]
        without_value_date = dict(valid)
        del without_value_date["value_date"]
        cases = [
            without_reference,
            dict(valid, provider_reference="p" * 256),
            dict(valid, event_type="med_return"),
            dict(valid, outbox_key="b0000000"),
            without_value_date,
            dict(valid, value_date="2026-02-30T00:00:00Z"),
            dict(valid, amount_in_cents=450000),
        ]

        for payload in cases:
            status, response = RequestGenerator.POST_webhooks_provider(payload)

            assert status == 400, (payload, response)
            assert response["code"] == "QIT000001", (payload, response)

        assert payout_link(payout)["outbox_status"] == "sent"
        assert balance(clearing_key()) == clearing_before
