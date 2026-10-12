"""Cópia de tests/integration/webhook/test_webhook_med.py contra o Cadastro de
verdade. O original continua intacto, contra o party-mock.

A única mudança é a dona da RENT: a Ana (2222…) vira a "aprovada" criada pela
fixture `party_scenarios`. Só o primeiro teste repassa a RENT por Pix (e
consulta o Cadastro); os outros dois param no MED, mas usam o mesmo contrato.
"""
from uuid import uuid4

from tests.utils import DbUtils, ObjectGenerator, PayloadGenerator, RequestGenerator
from tests.utils.party_scenarios import APROVADA

ALFA_CLIENT = "c1c1c1c1-c1c1-4c1c-8c1c-c1c1c1c1c1c1"


def provision_contract(owner_party_key: str) -> dict:
    """Provisiona um contrato novo, com a RENT da Ana (a "aprovada"), e
    devolve a chave de cada conta, pelo propósito, e a do contrato."""
    contract_ledger_payload = PayloadGenerator.create_contract_ledger_payload()
    for item in contract_ledger_payload["items"]:
        if item["purpose_code"] == "RENT":
            item["beneficiary_party_key"] = owner_party_key

    status, contract_ledger = RequestGenerator.POST_contract_ledgers(contract_ledger_payload)
    assert status == 201, contract_ledger

    keys = {account["purpose_code"]: account["ledger_account_key"] for account in contract_ledger["accounts"]}
    keys["contract_key"] = contract_ledger["contract_key"]

    return keys


def balance(ledger_account_key: str) -> int:
    status, ledger_account = RequestGenerator.GET_ledger_account(ledger_account_key)
    assert status == 200, ledger_account

    return ledger_account["balance_in_cents"]


def cash_key() -> str:
    """O `external/CASH` da Imobiliária Alfa: o dinheiro de verdade no banco."""
    return ObjectGenerator.get_client_account_key(ALFA_CLIENT, "CASH")


def inflow(contract_key: str, **kwargs) -> tuple:
    """A TX1: devolve (corpo do 201, `end_to_end_id`)."""
    status, response, payload = ObjectGenerator.create_inflow(contract_key, **kwargs)
    assert status == 201, response

    return response, payload["end_to_end_id"]


def trace(ledger_transaction_key: str) -> dict:
    status, response = RequestGenerator.GET_transfer_trace(ledger_transaction_key)
    assert status == 200, response

    return response


def reversals_of(ledger_transaction_key: str) -> list:
    """Os elos `reversal` da cadeia que estornam a transação pedida."""
    return [
        link
        for link in trace(ledger_transaction_key)["chain"]
        if link["ledger_transaction_type"] == "reversal" and link["reverses_transaction_key"] == ledger_transaction_key
    ]


def assert_book_closes() -> None:
    status, integrity = RequestGenerator.GET_integrity({"client_key": ALFA_CLIENT})
    assert status == 200, integrity
    assert integrity["difference_in_cents"] == 0
    assert integrity["negative_accounts"] == []


class TestWebhookMed:
    def test_webhooks_provider_med_after_payout_goes_negative(self, party_scenarios):
        """O MED depois de dividido, repassado e liquidado: a entrada volta
        inteira, e a COLLECTION fica negativa com o estorno no histórico
        (TX7, CU-F1; RFC :405-410)."""
        ANA = party_scenarios[APROVADA]

        keys = provision_contract(ANA)
        external_before = balance(cash_key())
        tx1, end_to_end_id = inflow(keys["contract_key"], value_date="2026-09-05T14:22:00Z")
        status, response, _payload = ObjectGenerator.create_split(keys["contract_key"], value_date="2026-09-05T14:23:00Z")
        assert status == 201, response
        status, payout, _payload = ObjectGenerator.create_payout(keys["RENT"])
        assert status == 202, payout
        assert payout["outbox"]["outbox_status"] == "sent", payout
        status, response, _payload = ObjectGenerator.create_settlement(payout["outbox"])
        assert status == 204, response

        status, response, _payload = ObjectGenerator.create_med_return(end_to_end_id, amount_in_cents=640000)

        assert status == 204, response
        assert response is None
        reversals = reversals_of(tx1["ledger_transaction_key"])
        assert len(reversals) == 1
        reversal = trace(reversals[0]["ledger_transaction_key"])
        assert reversal["transaction"]["actor"] == "provider"
        assert reversal["transaction"]["reason"] == "med_return"
        assert reversal["transaction"]["value_date"] == "2026-09-06T10:00:00Z"
        assert [
            (entry["direction"], entry["ledger_account_type"], entry["purpose_code"], entry["amount_in_cents"])
            for entry in reversal["entries"]
        ] == [
            ("D", "earmark", "COLLECTION", 640000),
            ("C", "external", "CASH", 640000),
        ]
        assert balance(keys["COLLECTION"]) == -640000
        assert balance(keys["RENT"]) == 0
        assert balance(cash_key()) - external_before == -450000
        assert_book_closes()

    def test_webhooks_provider_med_resend_and_refusals(self, party_scenarios):
        """O reenvio é 204; o MED acima do que resta, 422, e o desconhecido,
        404, sem gravar; o malformado, 400 (RFC :417-422; 01b :378)."""
        ANA = party_scenarios[APROVADA]

        keys = provision_contract(ANA)
        tx1, end_to_end_id = inflow(keys["contract_key"])
        first = PayloadGenerator.create_med_payload(
            end_to_end_id, amount_in_cents=450000, provider_reference="PRV-" + str(uuid4())
        )
        excess = PayloadGenerator.create_med_payload(
            end_to_end_id, amount_in_cents=640000, provider_reference="PRV-" + str(uuid4())
        )
        unknown = PayloadGenerator.create_med_payload("E" + uuid4().hex)

        for _attempt in range(2):
            status, response = RequestGenerator.POST_webhooks_provider(first)

            assert status == 204, response

        for _attempt in range(2):
            status, response = RequestGenerator.POST_webhooks_provider(excess)

            assert status == 422, response
            assert response["code"] == "QIT001015"

        for _attempt in range(2):
            status, response = RequestGenerator.POST_webhooks_provider(unknown)

            assert status == 404, response
            assert response["code"] == "QIT001020"

        assert len(reversals_of(tx1["ledger_transaction_key"])) == 1

        malformed = PayloadGenerator.create_med_payload(end_to_end_id, provider_reference="PRV-" + str(uuid4()))
        cases = [
            dict(malformed, amount_in_cents=0),
            dict(malformed, value_date="2026-02-30T00:00:00Z"),
            dict(malformed, end_to_end_id="E" * 65),
        ]

        for payload in cases:
            status, response = RequestGenerator.POST_webhooks_provider(payload)

            assert status == 400, (payload, response)
            assert response["code"] == "QIT000001", (payload, response)

        assert balance(keys["COLLECTION"]) == 190000

    def test_webhooks_provider_med_lock_timeout_is_repeatable(self, party_scenarios):
        """A contenção não fica gravada: o mesmo aviso, de novo, estorna
        (RN-09; S10 D-02)."""
        ANA = party_scenarios[APROVADA]

        keys = provision_contract(ANA)
        tx1, end_to_end_id = inflow(keys["contract_key"])

        with DbUtils.hold_row_lock(keys["COLLECTION"]):
            status, response, payload = ObjectGenerator.create_med_return(end_to_end_id)

        assert status == 409, response
        assert response["code"] == "QIT001011"

        status, response = RequestGenerator.POST_webhooks_provider(payload)

        assert status == 204, response
        assert len(reversals_of(tx1["ledger_transaction_key"])) == 1
        assert balance(keys["COLLECTION"]) == 0
