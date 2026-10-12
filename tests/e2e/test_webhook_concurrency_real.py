"""Cópia de tests/integration/webhook/test_webhook_concurrency.py contra o
Cadastro de verdade. O original continua intacto, contra o party-mock.

A única mudança é a dona da RENT: o `create_paid_out_contract()`, que sem
argumento cairia no 2222… do valor padrão, recebe a "aprovada" criada pela
fixture `party_scenarios`. Os repasses por Pix consultam o Cadastro real.
"""
from threading import Barrier, Thread
from uuid import uuid4

from tests.utils import ObjectGenerator, PayloadGenerator, RequestGenerator
from tests.utils.party_scenarios import APROVADA

ALFA_CLIENT = "c1c1c1c1-c1c1-4c1c-8c1c-c1c1c1c1c1c1"


def balance(ledger_account_key: str) -> int:
    status, ledger_account = RequestGenerator.GET_ledger_account(ledger_account_key)
    assert status == 200, ledger_account

    return ledger_account["balance_in_cents"]


def rent_key(contract_ledger: dict) -> str:
    """A chave da RENT no corpo do provisionamento."""
    for account in contract_ledger["accounts"]:
        if account["purpose_code"] == "RENT":
            return account["ledger_account_key"]

    raise AssertionError(contract_ledger)


def balances(contract_ledger: dict) -> dict:
    """Os saldos que a liquidação move: clearing, external e a RENT do contrato."""
    return {
        "CLR": balance(ObjectGenerator.get_client_account_key(ALFA_CLIENT, "TRANSIT")),
        "CASH": balance(ObjectGenerator.get_client_account_key(ALFA_CLIENT, "CASH")),
        "RENT": balance(rent_key(contract_ledger)),
    }


def moved(before: dict, contract_ledger: dict) -> dict:
    """Quanto cada saldo andou desde `before`."""
    after = balances(contract_ledger)

    return {name: after[name] - before[name] for name in before}


def chain_of(payout: dict) -> list:
    status, response = RequestGenerator.GET_transfer_trace(payout["ledger_transaction_key"])
    assert status == 200, response

    return response["chain"]


def webhook_payload(outbox: dict, event_type: str) -> dict:
    """O aviso do provedor com a referência do `create_settlement`."""
    suffix = "-SETTLED"
    if event_type == "settlement_failed":
        suffix = "-FAILED"

    return PayloadGenerator.create_webhook_payload(
        outbox["outbox_key"], "PRV-" + outbox["dispatch_idempotency_key"] + suffix, event_type=event_type
    )


def send_together(payloads: list) -> list:
    """Os avisos soltos juntos, um por thread. Devolve [(status, corpo)]
    ordenado por status."""
    barrier = Barrier(len(payloads))
    results = []

    def send(payload: dict) -> None:
        barrier.wait()
        results.append(RequestGenerator.POST_webhooks_provider(payload))

    threads = [Thread(target=send, args=(payload,)) for payload in payloads]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    return sorted(results, key=lambda result: result[0])


class TestWebhookConcurrency:
    def test_webhooks_provider_concurrent_resend(self, party_scenarios):
        ANA = party_scenarios[APROVADA]

        contract_ledger, payout = ObjectGenerator.create_paid_out_contract(ANA)
        before = balances(contract_ledger)
        payload = webhook_payload(payout["outbox"], "settlement_confirmed")

        results = send_together([payload, payload])

        assert [status for status, _response in results] == [204, 204], results
        settlements = [link for link in chain_of(payout) if link["ledger_transaction_type"] == "settlement"]
        assert len(settlements) == 1, settlements
        assert moved(before, contract_ledger)["CLR"] == -450000

    def test_webhooks_provider_confirm_and_fail_race(self, party_scenarios):
        """Confirmação e falha da mesma outbox juntas: um só desfecho, o que
        o estado final diz (INV-01)."""
        ANA = party_scenarios[APROVADA]

        contract_ledger, payout = ObjectGenerator.create_paid_out_contract(ANA)
        before = balances(contract_ledger)
        payloads = [
            webhook_payload(payout["outbox"], "settlement_confirmed"),
            webhook_payload(payout["outbox"], "settlement_failed"),
        ]

        results = send_together(payloads)

        assert [status for status, _response in results] == [204, 204], results
        chain = chain_of(payout)
        outcomes = [link["ledger_transaction_type"] for link in chain if link["ledger_transaction_type"] in (
            "settlement", "dispatch_return"
        )]
        outbox_status = [link["outbox_status"] for link in chain if link["ledger_transaction_type"] == "payout"][0]
        if outbox_status == "settled":
            assert outcomes == ["settlement"], chain
            assert moved(before, contract_ledger) == {"CLR": -450000, "CASH": -450000, "RENT": 0}
        else:
            assert outbox_status == "failed", chain
            assert outcomes == ["dispatch_return"], chain
            assert moved(before, contract_ledger) == {"CLR": -450000, "CASH": 0, "RENT": 450000}
        status, integrity = RequestGenerator.GET_integrity({"client_key": ALFA_CLIENT})
        assert status == 200, integrity
        assert integrity["difference_in_cents"] == 0

    def test_webhooks_provider_failed_vs_payout_no_deadlock_500(self, party_scenarios):
        """A falha do 1º repasse trava a `clearing` e credita a RENT; um
        repasse novo da mesma RENT trava a RENT e credita a `clearing`: o
        ciclo declarado (§6). O Postgres aborta um com `40P01`, que sai 011,
        e o perdedor repetido passa."""
        ANA = party_scenarios[APROVADA]

        contract_ledger, payout = ObjectGenerator.create_paid_out_contract(ANA)
        contract_key = contract_ledger["contract_key"]
        status, response, _payload = ObjectGenerator.create_inflow(contract_key, period_reference="2026-10")
        assert status == 201, response
        status, response, _payload = ObjectGenerator.create_split(contract_key, period_reference="2026-10")
        assert status == 201, response
        before = balances(contract_ledger)
        assert before["RENT"] == 450000
        failure = webhook_payload(payout["outbox"], "settlement_failed")
        new_payout = PayloadGenerator.create_payout_payload(rent_key(contract_ledger), period_reference="2026-10")
        barrier = Barrier(2)
        results = dict()

        def send_failure() -> None:
            barrier.wait()
            results["webhook"] = RequestGenerator.POST_webhooks_provider(failure)

        def send_payout() -> None:
            barrier.wait()
            results["payout"] = RequestGenerator.POST_transfers_payout(new_payout, idempotency_key=str(uuid4()))

        threads = [Thread(target=send_failure), Thread(target=send_payout)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        for name, (status, response) in results.items():
            assert status in (202, 204) or (status == 409 and response["code"] == "QIT001011"), (name, results)

        if results["webhook"][0] == 409:
            results["webhook"] = RequestGenerator.POST_webhooks_provider(failure)
        if results["payout"][0] == 409:
            results["payout"] = RequestGenerator.POST_transfers_payout(new_payout, idempotency_key=str(uuid4()))

        assert (results["webhook"][0], results["payout"][0]) == (204, 202), results
        assert moved(before, contract_ledger) == {"CLR": 0, "CASH": 0, "RENT": 0}
        assert [link["outbox_status"] for link in chain_of(payout) if link["outbox_key"] == payout["outbox"]["outbox_key"]] == [
            "failed"
        ]
        status, integrity = RequestGenerator.GET_integrity({"client_key": ALFA_CLIENT})
        assert status == 200, integrity
        assert integrity["difference_in_cents"] == 0
