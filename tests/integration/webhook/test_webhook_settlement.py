import json
from uuid import uuid4

from tests.utils import DbUtils, ObjectGenerator, PayloadGenerator, RequestGenerator

ALFA_CLIENT = "c1c1c1c1-c1c1-4c1c-8c1c-c1c1c1c1c1c1"


def balance(ledger_account_key: str) -> int:
    status, ledger_account = RequestGenerator.GET_ledger_account(ledger_account_key)
    assert status == 200, ledger_account

    return ledger_account["balance_in_cents"]


def clearing_key() -> str:
    """A `clearing/TRANSIT` da Imobiliária Alfa: por onde passa todo repasse dela."""
    return ObjectGenerator.get_client_account_key(ALFA_CLIENT, "TRANSIT")


def cash_key() -> str:
    """O `external/CASH` da Imobiliária Alfa: o dinheiro de verdade no banco."""
    return ObjectGenerator.get_client_account_key(ALFA_CLIENT, "CASH")


def rent_key(contract_ledger: dict) -> str:
    """A chave da RENT no corpo do provisionamento."""
    for account in contract_ledger["accounts"]:
        if account["purpose_code"] == "RENT":
            return account["ledger_account_key"]

    raise AssertionError(contract_ledger)


def balances(contract_ledger: dict) -> dict:
    """Os saldos que a liquidação move: clearing, external e a RENT do contrato."""
    return {
        "CLR": balance(clearing_key()),
        "CASH": balance(cash_key()),
        "RENT": balance(rent_key(contract_ledger)),
    }


def moved(before: dict, contract_ledger: dict) -> dict:
    """Quanto cada saldo andou desde `before`."""
    after = balances(contract_ledger)

    return {name: after[name] - before[name] for name in before}


def links_of_type(payout: dict, ledger_transaction_type: str) -> list:
    """Os elos da cadeia do repasse com o tipo pedido."""
    chain = trace(payout["ledger_transaction_key"])["chain"]

    return [link for link in chain if link["ledger_transaction_type"] == ledger_transaction_type]


def entry_summary(entries: list) -> list:
    return [
        (
            entry["direction"],
            entry["amount_in_cents"],
            entry["ledger_account_type"],
            entry["purpose_code"],
            entry["owner_party_key"],
            entry["owner_role"],
        )
        for entry in entries
    ]


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

    def test_webhooks_provider_settlement_confirmed_settles(self):
        contract_ledger, payout = ObjectGenerator.create_paid_out_contract()
        before = balances(contract_ledger)

        status, response, _payload = ObjectGenerator.create_settlement(payout["outbox"])

        assert status == 204, response
        assert response is None
        assert payout_link(payout)["outbox_status"] == "settled"
        assert moved(before, contract_ledger) == {"CLR": -450000, "CASH": -450000, "RENT": 0}
        status, integrity = RequestGenerator.GET_integrity({"client_key": ALFA_CLIENT})
        assert status == 200, integrity
        assert integrity["difference_in_cents"] == 0

    def test_webhooks_provider_settlement_inherits_payout(self):
        contract_ledger, payout = ObjectGenerator.create_paid_out_contract()

        status, response, _payload = ObjectGenerator.create_settlement(payout["outbox"])

        assert status == 204, response
        settlements = links_of_type(payout, "settlement")
        assert len(settlements) == 1, settlements
        settlement_trace = trace(settlements[0]["ledger_transaction_key"])
        transaction = settlement_trace["transaction"]
        assert transaction["contract_key"] == contract_ledger["contract_key"]
        assert transaction["period_reference"] == "2026-09"
        assert transaction["value_date"] == "2026-09-06T10:00:00Z"
        assert transaction["actor"] == "provider"
        assert transaction["reason"] == "settlement_confirmed"
        assert transaction["payer_party_key"] is None
        assert transaction["end_to_end_id"] is None
        assert entry_summary(settlement_trace["entries"]) == [
            ("D", 450000, "clearing", "TRANSIT", None, None),
            ("C", 450000, "external", "CASH", None, None),
        ]

    def test_webhooks_provider_resend_has_no_effect(self):
        contract_ledger, payout = ObjectGenerator.create_paid_out_contract()
        before = balances(contract_ledger)

        status_first, first, payload = ObjectGenerator.create_settlement(payout["outbox"])
        status_second, second = RequestGenerator.POST_webhooks_provider(payload)
        status_third, third = RequestGenerator.POST_webhooks_provider(raw_body=(json.dumps(payload) + " ").encode())

        assert (status_first, status_second, status_third) == (204, 204, 204), (first, second, third)
        assert len(links_of_type(payout, "settlement")) == 1
        assert moved(before, contract_ledger) == {"CLR": -450000, "CASH": -450000, "RENT": 0}

    def test_webhooks_provider_lock_timeout_is_repeatable(self):
        contract_ledger, payout = ObjectGenerator.create_paid_out_contract()
        before = balances(contract_ledger)

        with DbUtils.hold_row_lock(clearing_key()):
            status, response, payload = ObjectGenerator.create_settlement(payout["outbox"])

        assert status == 409, response
        assert response["code"] == "QIT001011"

        status, response = RequestGenerator.POST_webhooks_provider(payload)

        assert status == 204, response
        assert payout_link(payout)["outbox_status"] == "settled"
        assert len(links_of_type(payout, "settlement")) == 1
        assert moved(before, contract_ledger)["CLR"] == -450000
