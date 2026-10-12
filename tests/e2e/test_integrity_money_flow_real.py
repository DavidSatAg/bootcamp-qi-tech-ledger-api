"""Cópia de tests/integration/integrity/test_integrity_money_flow.py contra o
Cadastro de verdade. O original continua intacto, contra o party-mock.

O caminho repassa por Pix a RENT e a CONDO do contrato, e o Ledger consulta o
Cadastro pelo dono de cada uma. Sem `items`, o `create_contract_ledger()` põe
na RENT a Ana (2222…) e na CONDO o condomínio (5555…, outra chave do
party-mock: active, com pix_key), e as duas dão 404 no real. A cópia passa os
`items` (parâmetro que o helper já tem) com a "aprovada" da fixture
`party_scenarios` nas duas, e compara o dono da RENT com ela.
"""
from tests.utils import ObjectGenerator, PayloadGenerator, RequestGenerator
from tests.utils.party_scenarios import APROVADA

ALFA_CLIENT = "c1c1c1c1-c1c1-4c1c-8c1c-c1c1c1c1c1c1"
BOOK_ACCOUNTS = ["CASH", "TRANSIT", "OWN", "PLATFORM_FEE"]
CONTRACT_ACCOUNTS = ["COLLECTION", "RENT", "IPTU", "CONDO", "WATER", "ELECTRICITY"]


def provision_contract(owner_party_key: str) -> dict:
    """Provisiona um contrato novo e devolve a chave de cada conta, pelo
    propósito, mais as do livro da Imobiliária Alfa (CASH, TRANSIT). A RENT
    e a CONDO, que o caminho repassa por Pix, ficam com a parte real pedida."""
    items = PayloadGenerator.create_contract_ledger_payload()["items"]
    for item in items:
        if item["purpose_code"] in ("RENT", "CONDO"):
            item["beneficiary_party_key"] = owner_party_key

    status, contract_ledger = ObjectGenerator.create_contract_ledger(items=items)
    assert status == 201, contract_ledger

    keys = {account["purpose_code"]: account["ledger_account_key"] for account in contract_ledger["accounts"]}
    keys["contract_key"] = contract_ledger["contract_key"]
    keys["CASH"] = ObjectGenerator.get_client_account_key(ALFA_CLIENT, "CASH")
    keys["TRANSIT"] = ObjectGenerator.get_client_account_key(ALFA_CLIENT, "TRANSIT")

    return keys


def balance(ledger_account_key: str) -> int:
    status, ledger_account = RequestGenerator.GET_ledger_account(ledger_account_key)
    assert status == 200, ledger_account

    return ledger_account["balance_in_cents"]


def balances(keys: dict) -> dict:
    """Os saldos das contas do caso do remodelagem/05."""
    return {name: balance(keys[name]) for name in BOOK_ACCOUNTS + CONTRACT_ACCOUNTS}


def integrity(params: dict = None) -> dict:
    status, response = RequestGenerator.GET_integrity(params)
    assert status == 200, response

    return response


def trace(ledger_transaction_key: str) -> dict:
    status, response = RequestGenerator.GET_transfer_trace(ledger_transaction_key)
    assert status == 200, response

    return response


def pay_out_and_settle(source_account_key: str, **kwargs) -> dict:
    """Um repasse por Pix (TX3, TX5) e a liquidação dele (TX4, TX6).
    Devolve o corpo do 202 do repasse."""
    status, payout, _payload = ObjectGenerator.create_payout(source_account_key, **kwargs)
    assert status == 202, payout
    assert payout["outbox"]["outbox_status"] == "sent", payout

    status, response, _payload = ObjectGenerator.create_settlement(payout["outbox"])
    assert status == 204, response

    return payout


def run_tx1_to_tx6(keys: dict) -> dict:
    """O remodelagem/05 da TX1 à TX6 no contrato. Devolve
    {"inflow": corpo da TX1, "inflow_payload": corpo enviado, "rent_payout": corpo da TX3}."""
    status, inflow, inflow_payload = ObjectGenerator.create_inflow(
        keys["contract_key"], value_date="2026-09-05T14:22:00Z"
    )
    assert status == 201, inflow

    status, split, _payload = ObjectGenerator.create_split(keys["contract_key"], value_date="2026-09-05T14:23:00Z")
    assert status == 201, split

    rent_payout = pay_out_and_settle(keys["RENT"])
    pay_out_and_settle(keys["CONDO"], amount_in_cents=80000)

    return {"inflow": inflow, "inflow_payload": inflow_payload, "rent_payout": rent_payout}


class TestIntegrityMoneyFlow:
    def test_integrity_money_flow_tx1_to_tx6(self, party_scenarios):
        ANA = party_scenarios[APROVADA]

        keys = provision_contract(ANA)
        before = balances(keys)
        book_before = integrity({"client_key": ALFA_CLIENT})

        flow = run_tx1_to_tx6(keys)

        after = balances(keys)
        assert {name: after[name] - before[name] for name in BOOK_ACCOUNTS} == {
            "CASH": 110000,
            "TRANSIT": 0,
            "OWN": 45000,
            "PLATFORM_FEE": 5000,
        }
        assert {name: after[name] for name in CONTRACT_ACCOUNTS} == {
            "COLLECTION": 0,
            "RENT": 0,
            "IPTU": 30000,
            "CONDO": 0,
            "WATER": 12000,
            "ELECTRICITY": 18000,
        }

        book_after = integrity({"client_key": ALFA_CLIENT})
        assert book_after["difference_in_cents"] == 0
        assert book_after["negative_accounts"] == []
        assert book_after["asset_in_cents"] - book_before["asset_in_cents"] == 110000
        assert book_after["liability_in_cents"] - book_before["liability_in_cents"] == 105000
        assert book_after["equity_in_cents"] - book_before["equity_in_cents"] == 5000
        assert integrity()["difference_in_cents"] == 0

        rent_trace = trace(flow["rent_payout"]["ledger_transaction_key"])
        legs = [
            (entry["direction"], entry["purpose_code"], entry["amount_in_cents"]) for entry in rent_trace["entries"]
        ]
        assert sorted(legs) == [("C", "TRANSIT", 450000), ("D", "RENT", 450000)]
        rent_leg = [entry for entry in rent_trace["entries"] if entry["purpose_code"] == "RENT"][0]
        assert rent_leg["owner_party_key"] == ANA
        assert rent_leg["owner_role"] == "landlord"

        chain = rent_trace["chain"]
        types = sorted(link["ledger_transaction_type"] for link in chain)
        assert types == ["inflow", "payout", "payout", "settlement", "settlement", "split"], types
        payouts = [link for link in chain if link["ledger_transaction_type"] == "payout"]
        assert [link["outbox_status"] for link in payouts] == ["settled", "settled"], payouts

    def test_integrity_money_flow_tx7_tx8_final_picture(self, party_scenarios):
        """O OWN é compartilhado pelo livro: a TX8 debita 45000 dele, e a
        TX2 deste mesmo teste é que os pôs lá (+45000)."""
        ANA = party_scenarios[APROVADA]

        keys = provision_contract(ANA)
        before = balances(keys)
        book_before = integrity({"client_key": ALFA_CLIENT})
        flow = run_tx1_to_tx6(keys)

        status, response, _payload = ObjectGenerator.create_med_return(
            flow["inflow_payload"]["end_to_end_id"], amount_in_cents=640000
        )
        assert status == 204, response

        status, internal, _payload = ObjectGenerator.create_internal(keys["OWN"], keys["COLLECTION"])
        assert status == 201, internal

        after = balances(keys)
        assert {name: after[name] - before[name] for name in BOOK_ACCOUNTS} == {
            "CASH": -530000,
            "TRANSIT": 0,
            "OWN": 0,
            "PLATFORM_FEE": 5000,
        }
        assert {name: after[name] for name in CONTRACT_ACCOUNTS} == {
            "COLLECTION": -595000,
            "RENT": 0,
            "IPTU": 30000,
            "CONDO": 0,
            "WATER": 12000,
            "ELECTRICITY": 18000,
        }

        book_after = integrity({"client_key": ALFA_CLIENT})
        assert book_after["difference_in_cents"] == 0
        assert book_after["negative_accounts"] == []
        assert book_after["asset_in_cents"] - book_before["asset_in_cents"] == -530000
        assert (
            book_after["liability_in_cents"] - book_before["liability_in_cents"]
            + book_after["equity_in_cents"] - book_before["equity_in_cents"]
        ) == -530000
        assert integrity()["difference_in_cents"] == 0

        inflow_key = flow["inflow"]["ledger_transaction_key"]
        chain = trace(inflow_key)["chain"]
        reversals = [link for link in chain if link["ledger_transaction_type"] == "reversal"]
        assert len(reversals) == 1, chain
        assert reversals[0]["reverses_transaction_key"] == inflow_key
        assert [link for link in chain if link["ledger_transaction_type"] == "internal"] == []
