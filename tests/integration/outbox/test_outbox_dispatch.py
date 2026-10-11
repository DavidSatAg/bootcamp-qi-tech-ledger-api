from uuid import uuid4

from tests.utils import DbUtils, ObjectGenerator, RequestGenerator

ALFA_CLIENT = "c1c1c1c1-c1c1-4c1c-8c1c-c1c1c1c1c1c1"


def balance(ledger_account_key: str) -> int:
    status, ledger_account = RequestGenerator.GET_ledger_account(ledger_account_key)
    assert status == 200, ledger_account

    return ledger_account["balance_in_cents"]


def clearing_key() -> str:
    """A `clearing/TRANSIT` da Imobiliária Alfa: o destino de todo repasse dela."""
    return ObjectGenerator.get_client_account_key(ALFA_CLIENT, "TRANSIT")


def pending_payout() -> tuple:
    """O banco zerado e um repasse da RENT do `ffff…` (Pix com erro no
    provedor): `pending`, uma tentativa. Devolve (corpo do 202, payload, K)."""
    DbUtils.rollback()
    idempotency_key = str(uuid4())
    payout, payload = ObjectGenerator.create_pending_payout(idempotency_key)

    return payout, payload, idempotency_key


def outbox_state(payload: dict, idempotency_key: str) -> dict:
    """A outbox atual do repasse: o replay com a mesma chave e o mesmo corpo
    não despacha (S09 D4)."""
    status, response = RequestGenerator.POST_transfers_payout(payload, idempotency_key=idempotency_key)
    assert status == 202, response

    return response["outbox"]


def pix_dispatches(dispatch_idempotency_key: str) -> list:
    """As chamadas `POST /pix` que o provedor recebeu com esta chave de despacho."""
    return [
        (headers, body)
        for headers, body in RequestGenerator.GET_mock_requests("provider-mock", "/pix")
        if body is not None and body.get("dispatch_idempotency_key") == dispatch_idempotency_key
    ]


def sweep(limit: int) -> dict:
    status, response = RequestGenerator.POST_outbox_dispatch({"limit": limit})
    assert status == 200, response

    return response


class TestOutboxDispatch:
    def test_outbox_dispatch_redispatches_with_same_key(self):
        payout, payload, idempotency_key = pending_payout()
        dispatch_idempotency_key = payout["outbox"]["dispatch_idempotency_key"]

        assert sweep(10) == {"sent": 0, "pending": 1, "dead": 0}

        dispatches = pix_dispatches(dispatch_idempotency_key)
        assert len(dispatches) == 2, dispatches
        for _headers, body in dispatches:
            assert body["dispatch_idempotency_key"] == dispatch_idempotency_key
            assert body["pix_key"] == "erro@mock"
            assert body["amount_in_cents"] == 450000
        outbox = outbox_state(payload, idempotency_key)
        assert outbox["outbox_status"] == "pending"
        assert outbox["attempt_count"] == 2
        assert balance(payload["source_account_key"]) == 0
        # O banco foi zerado: a clearing estava em 0 antes do repasse.
        assert balance(clearing_key()) == 450000

    def test_outbox_dispatch_limit_and_body(self):
        DbUtils.rollback()
        first_key = str(uuid4())
        _first, first_payload = ObjectGenerator.create_pending_payout(first_key)
        second_key = str(uuid4())
        _second, second_payload = ObjectGenerator.create_pending_payout(second_key)

        assert sweep(1) == {"sent": 0, "pending": 1, "dead": 0}

        assert outbox_state(first_payload, first_key)["attempt_count"] == 2
        assert outbox_state(second_payload, second_key)["attempt_count"] == 1

        for payload in [{"limit": 0}, {"limit": 101}, {"limit": "1"}, {"limit": 1, "outbox_key": str(uuid4())}]:
            status, response = RequestGenerator.POST_outbox_dispatch(payload)

            assert status == 400, (payload, response)
            assert response["code"] == "QIT000001", (payload, response)
