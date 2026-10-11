from uuid import uuid4

from tests.utils import ObjectGenerator, PayloadGenerator, RequestGenerator

ALFA_CLIENT = "c1c1c1c1-c1c1-4c1c-8c1c-c1c1c1c1c1c1"
ABOVE_MAXIMUM = 10**15 + 1


def balance(ledger_account_key: str) -> int:
    status, ledger_account = RequestGenerator.GET_ledger_account(ledger_account_key)
    assert status == 200, ledger_account

    return ledger_account["balance_in_cents"]


def contract_ledger_with_iptu(value: int) -> dict:
    """O provisionamento do caso do remodelagem/05 com o `value` do IPTU trocado."""
    payload = PayloadGenerator.create_contract_ledger_payload()
    for item in payload["items"]:
        if item["purpose_code"] == "IPTU":
            item["value"] = value

    return payload


class TestMoneyMaximum:
    def test_money_fields_refuse_above_maximum(self):
        """Todo campo de dinheiro vai até 10^15 centavos (RN-06, L20): acima
        disso é `400 QIT000001`, com uma chave nova por caso."""
        status, contract_ledger = ObjectGenerator.create_contract_ledger()
        assert status == 201, contract_ledger
        keys = {account["purpose_code"]: account["ledger_account_key"] for account in contract_ledger["accounts"]}
        contract_key = contract_ledger["contract_key"]
        raw_inflow = (
            '{"amount_in_cents": 12345678901234567.0, "contract_key": "' + contract_key + '", '
            '"period_reference": "2026-09", "payer_party_key": "33333333-3333-4333-8333-333333333333", '
            '"end_to_end_id": "E00000000202609051422' + uuid4().hex[:11] + '", "actor": "erp-alfa"}'
        ).encode("utf-8")

        cases = [
            (
                "rent_amount_in_cents",
                lambda: RequestGenerator.POST_contract_ledgers(
                    PayloadGenerator.create_contract_ledger_payload(rent_amount_in_cents=ABOVE_MAXIMUM)
                ),
            ),
            ("value do IPTU", lambda: RequestGenerator.POST_contract_ledgers(contract_ledger_with_iptu(ABOVE_MAXIMUM))),
            ("inflow", lambda: ObjectGenerator.create_inflow(contract_key, amount_in_cents=ABOVE_MAXIMUM)[:2]),
            (
                "inflow cru",
                lambda: RequestGenerator.POST_transfers_inflow(raw_body=raw_inflow, idempotency_key=str(uuid4())),
            ),
            ("payout", lambda: ObjectGenerator.create_payout(keys["RENT"], amount_in_cents=ABOVE_MAXIMUM)[:2]),
            ("estorno", lambda: ObjectGenerator.create_reversal(str(uuid4()), amount_in_cents=ABOVE_MAXIMUM)[:2]),
            (
                "MED",
                lambda: ObjectGenerator.create_med_return(
                    "E00000000202609051422" + uuid4().hex[:11], amount_in_cents=ABOVE_MAXIMUM
                )[:2],
            ),
            (
                "interna",
                lambda: ObjectGenerator.create_internal(
                    keys["OWN"], keys["COLLECTION"], gross_amount_in_cents=ABOVE_MAXIMUM
                )[:2],
            ),
            (
                "fixed do rateio interno",
                lambda: ObjectGenerator.create_internal_allocations(
                    keys["OWN"],
                    [{"target_account_key": keys["COLLECTION"], "type": "fixed", "value": ABOVE_MAXIMUM}],
                    gross_amount_in_cents=10**15,
                )[:2],
            ),
        ]

        for name, send in cases:
            status, response = send()

            assert status == 400, (name, status, response)
            assert response["code"] == "QIT000001", (name, response)

        assert balance(keys["COLLECTION"]) == 0
        status, integrity = RequestGenerator.GET_integrity({"client_key": ALFA_CLIENT})
        assert status == 200, integrity
        assert integrity["difference_in_cents"] == 0
