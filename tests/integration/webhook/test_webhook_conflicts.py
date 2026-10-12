import time
from threading import Thread
from uuid import uuid4

from tests.utils import DbUtils, ObjectGenerator, PayloadGenerator, RequestGenerator

ALFA_CLIENT = "c1c1c1c1-c1c1-4c1c-8c1c-c1c1c1c1c1c1"
PIX_TIMEOUT = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"
JOIN_TIMEOUT_SECONDS = 30
IN_FLIGHT_TIMEOUT_SECONDS = 10


def balance(ledger_account_key: str) -> int:
    status, ledger_account = RequestGenerator.GET_ledger_account(ledger_account_key)
    assert status == 200, ledger_account

    return ledger_account["balance_in_cents"]


def clearing_key() -> str:
    """A `clearing/TRANSIT` da Imobiliária Alfa: o destino de todo repasse dela."""
    return ObjectGenerator.get_client_account_key(ALFA_CLIENT, "TRANSIT")


def trace(ledger_transaction_key: str) -> dict:
    status, response = RequestGenerator.GET_transfer_trace(ledger_transaction_key)
    assert status == 200, response

    return response


def payout_link(payout: dict) -> dict:
    """O elo do repasse na cadeia do trace dele: traz o estado da outbox."""
    for link in trace(payout["ledger_transaction_key"])["chain"]:
        if link["ledger_transaction_key"] == payout["ledger_transaction_key"]:
            return link

    raise AssertionError(payout)


def links_of_type(payout: dict, ledger_transaction_type: str) -> list:
    """Os elos da cadeia do repasse com o tipo pedido."""
    chain = trace(payout["ledger_transaction_key"])["chain"]

    return [link for link in chain if link["ledger_transaction_type"] == ledger_transaction_type]


def sweep(limit: int = 10) -> dict:
    status, response = RequestGenerator.POST_outbox_dispatch({"limit": limit})
    assert status == 200, response

    return response


def sweep_until_dead(payout: dict) -> None:
    """Quatro varreduras que falham (tentativas 2 a 5) e a quinta, que marca
    `dead` sem chamar o provedor (G :474; D3). Pede o banco zerado: a
    contagem da varredura é da fila inteira."""
    for _ in range(4):
        assert sweep() == {"sent": 0, "pending": 1, "dead": 0}

    assert sweep() == {"sent": 0, "pending": 0, "dead": 1}
    assert payout_link(payout)["outbox_status"] == "dead"


def wait_for_outbox_status(payout: dict, outbox_status: str) -> None:
    """Lê o trace até a outbox do repasse chegar ao estado pedido."""
    deadline = time.monotonic() + IN_FLIGHT_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if payout_link(payout)["outbox_status"] == outbox_status:
            return
        time.sleep(0.05)

    raise AssertionError(f"a outbox não chegou a {outbox_status}: {payout_link(payout)}")


def assert_integrity() -> None:
    status, integrity = RequestGenerator.GET_integrity({"client_key": ALFA_CLIENT})
    assert status == 200, integrity
    assert integrity["difference_in_cents"] == 0, integrity


class TestWebhookConflicts:
    def test_webhooks_provider_med_closed_account_conflicts(self):
        """O MED de uma entrada já dividida, com a COLLECTION zerada e
        encerrada (PUT status): 409 QIT001012, repetível, e nada se grava,
        nem o estorno (RFC :181; S10 D-02)."""
        status, contract_ledger = ObjectGenerator.create_contract_ledger()
        assert status == 201, contract_ledger
        keys = {account["purpose_code"]: account["ledger_account_key"] for account in contract_ledger["accounts"]}
        status, tx1, inflow_payload = ObjectGenerator.create_inflow(contract_ledger["contract_key"])
        assert status == 201, tx1
        status, response, _payload = ObjectGenerator.create_split(contract_ledger["contract_key"])
        assert status == 201, response
        status, response = RequestGenerator.PUT_ledger_account_status(
            keys["COLLECTION"], PayloadGenerator.create_status_payload("closed")
        )
        assert status == 200, response

        med_payload = PayloadGenerator.create_med_payload(inflow_payload["end_to_end_id"])
        for _attempt in range(2):
            status, response = RequestGenerator.POST_webhooks_provider(med_payload)

            assert status == 409, response
            assert response["code"] == "QIT001012"

        chain = trace(tx1["ledger_transaction_key"])["chain"]
        assert [link for link in chain if link["ledger_transaction_type"] == "reversal"] == []
        assert balance(keys["COLLECTION"]) == 0
        assert balance(keys["RENT"]) == 450000
        assert_integrity()

    def test_webhooks_provider_dead_outbox_has_no_effect(self):
        """Outbox `dead` (tentativas esgotadas): a confirmação e a falha dão
        204 sem efeito; nada se liquida nem volta à origem, e a outbox
        continua `dead` (RFC :181)."""
        DbUtils.rollback()
        payout, payload = ObjectGenerator.create_pending_payout(str(uuid4()))
        sweep_until_dead(payout)
        clearing_before = balance(clearing_key())

        status, response, _payload = ObjectGenerator.create_settlement(payout["outbox"])

        assert status == 204, response

        status, response, _payload = ObjectGenerator.create_settlement(
            payout["outbox"], event_type="settlement_failed"
        )

        assert status == 204, response
        assert payout_link(payout)["outbox_status"] == "dead"
        assert links_of_type(payout, "settlement") == []
        assert links_of_type(payout, "dispatch_return") == []
        assert balance(clearing_key()) == clearing_before
        assert balance(payload["source_account_key"]) == 0
        assert_integrity()

    def test_webhooks_provider_in_flight_outbox_conflicts(self):
        """O aviso chega enquanto a varredura despacha a outbox (`in_flight`,
        o provedor demorando): 409 QIT001011 e nada se grava, nem o
        `provider_event`. Despachada depois, o mesmo aviso liquida (RFC :181;
        S10 D4)."""
        DbUtils.rollback()
        _contract_ledger, payout = ObjectGenerator.create_paid_out_contract(PIX_TIMEOUT)
        assert payout["outbox"]["outbox_status"] == "pending", payout
        clearing_before = balance(clearing_key())
        sweeps = []
        sweeper = Thread(target=lambda: sweeps.append(sweep()), daemon=True)

        sweeper.start()
        wait_for_outbox_status(payout, "in_flight")
        status, response, webhook_payload = ObjectGenerator.create_settlement(payout["outbox"])
        sweeper.join(timeout=JOIN_TIMEOUT_SECONDS)

        assert not sweeper.is_alive(), "a varredura não voltou dentro do prazo"
        assert status == 409, response
        assert response["code"] == "QIT001011"
        assert sweeps == [{"sent": 0, "pending": 1, "dead": 0}]
        assert payout_link(payout)["outbox_status"] == "pending"
        assert links_of_type(payout, "settlement") == []
        assert balance(clearing_key()) == clearing_before

        with RequestGenerator.accept_pix(payout["outbox"]["dispatch_idempotency_key"]):
            assert sweep() == {"sent": 1, "pending": 0, "dead": 0}

        status, response = RequestGenerator.POST_webhooks_provider(webhook_payload)

        assert status == 204, response
        assert payout_link(payout)["outbox_status"] == "settled"
        assert len(links_of_type(payout, "settlement")) == 1
        assert balance(clearing_key()) == clearing_before - 450000
        assert_integrity()
