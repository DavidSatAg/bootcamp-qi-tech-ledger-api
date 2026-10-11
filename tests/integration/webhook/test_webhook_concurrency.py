from threading import Barrier, Thread

from tests.utils import ObjectGenerator, PayloadGenerator, RequestGenerator

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
    def test_webhooks_provider_concurrent_resend(self):
        contract_ledger, payout = ObjectGenerator.create_paid_out_contract()
        before = balances(contract_ledger)
        payload = webhook_payload(payout["outbox"], "settlement_confirmed")

        results = send_together([payload, payload])

        assert [status for status, _response in results] == [204, 204], results
        settlements = [link for link in chain_of(payout) if link["ledger_transaction_type"] == "settlement"]
        assert len(settlements) == 1, settlements
        assert moved(before, contract_ledger)["CLR"] == -450000

    def test_webhooks_provider_confirm_and_fail_race(self):
        """Confirmação e falha da mesma outbox juntas: um só desfecho, o que
        o estado final diz (INV-01)."""
        contract_ledger, payout = ObjectGenerator.create_paid_out_contract()
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
