"""Cópia de tests/integration/outbox/test_outbox_dispatch.py contra o Cadastro
de verdade. O original continua intacto, contra o party-mock.

A mudança é a origem dos donos: o `ffff…` (Pix com erro) e o `eeee…` (Pix em
timeout) viram a "pix_erro" e a "pix_timeout" criadas pela fixture
`party_scenarios`. O `create_pending_payout`, que sem argumento cairia no
`ffff…` fixo, recebe a "pix_erro" pelo `owner_party_key=` (D-5, LED-22). As
pix_key esperadas no despacho ao provedor deixam de ser literais e passam a
ser as que o seed cadastrou (`SCENARIOS`). O provedor continua mock no ponto
de integração (01b §0.2), e por isso o diário dele segue valendo.
"""
from uuid import uuid4

from tests.utils import DbUtils, ObjectGenerator, RequestGenerator
from tests.utils.party_scenarios import PIX_ERRO as PAPEL_PIX_ERRO, PIX_TIMEOUT as PAPEL_PIX_TIMEOUT, SCENARIOS

ALFA_CLIENT = "c1c1c1c1-c1c1-4c1c-8c1c-c1c1c1c1c1c1"

# As pix_key com que o seed cadastra as partes: (final, pix_key, status).
PIX_ERRO_PIX_KEY = SCENARIOS[PAPEL_PIX_ERRO][1]
PIX_TIMEOUT_PIX_KEY = SCENARIOS[PAPEL_PIX_TIMEOUT][1]


def balance(ledger_account_key: str) -> int:
    status, ledger_account = RequestGenerator.GET_ledger_account(ledger_account_key)
    assert status == 200, ledger_account

    return ledger_account["balance_in_cents"]


def clearing_key() -> str:
    """A `clearing/TRANSIT` da Imobiliária Alfa: o destino de todo repasse dela."""
    return ObjectGenerator.get_client_account_key(ALFA_CLIENT, "TRANSIT")


def pending_payout(owner_party_key: str) -> tuple:
    """O banco zerado e um repasse da RENT da "pix_erro" (Pix com erro no
    provedor): `pending`, uma tentativa. Devolve (corpo do 202, payload, K)."""
    DbUtils.rollback()
    idempotency_key = str(uuid4())
    payout, payload = ObjectGenerator.create_pending_payout(idempotency_key, owner_party_key=owner_party_key)

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


def trace(ledger_transaction_key: str) -> dict:
    status, response = RequestGenerator.GET_transfer_trace(ledger_transaction_key)
    assert status == 200, response

    return response


def assert_integrity() -> None:
    status, integrity = RequestGenerator.GET_integrity({"client_key": ALFA_CLIENT})
    assert status == 200, integrity
    assert integrity["difference_in_cents"] == 0, integrity


def sweep_until_dead(payload: dict, idempotency_key: str) -> None:
    """Quatro varreduras que falham (tentativas 2 a 5) e a quinta, que marca
    `dead` sem chamar o provedor (G :474; D3)."""
    for _ in range(4):
        assert sweep(10) == {"sent": 0, "pending": 1, "dead": 0}

    outbox = outbox_state(payload, idempotency_key)
    assert (outbox["outbox_status"], outbox["attempt_count"]) == ("pending", 5)

    assert sweep(10) == {"sent": 0, "pending": 0, "dead": 1}


class TestOutboxDispatch:
    def test_outbox_dispatch_redispatches_with_same_key(self, party_scenarios):
        PIX_ERROR = party_scenarios[PAPEL_PIX_ERRO]

        payout, payload, idempotency_key = pending_payout(PIX_ERROR)
        dispatch_idempotency_key = payout["outbox"]["dispatch_idempotency_key"]

        assert sweep(10) == {"sent": 0, "pending": 1, "dead": 0}

        dispatches = pix_dispatches(dispatch_idempotency_key)
        assert len(dispatches) == 2, dispatches
        for _headers, body in dispatches:
            assert body["dispatch_idempotency_key"] == dispatch_idempotency_key
            assert body["pix_key"] == PIX_ERRO_PIX_KEY
            assert body["amount_in_cents"] == 450000
        outbox = outbox_state(payload, idempotency_key)
        assert outbox["outbox_status"] == "pending"
        assert outbox["attempt_count"] == 2
        assert balance(payload["source_account_key"]) == 0
        # O banco foi zerado: a clearing estava em 0 antes do repasse.
        assert balance(clearing_key()) == 450000

    def test_outbox_dispatch_marks_dead_after_max_attempts(self, party_scenarios):
        PIX_ERROR = party_scenarios[PAPEL_PIX_ERRO]

        payout, payload, idempotency_key = pending_payout(PIX_ERROR)
        dispatch_idempotency_key = payout["outbox"]["dispatch_idempotency_key"]

        sweep_until_dead(payload, idempotency_key)

        outbox = outbox_state(payload, idempotency_key)
        assert (outbox["outbox_status"], outbox["attempt_count"]) == ("dead", 5)
        assert len(pix_dispatches(dispatch_idempotency_key)) == 5

        assert sweep(10) == {"sent": 0, "pending": 0, "dead": 0}
        assert len(pix_dispatches(dispatch_idempotency_key)) == 5
        # O banco foi zerado: a clearing estava em 0 antes do repasse.
        assert balance(clearing_key()) == 450000

    def test_outbox_dispatch_dead_payout_is_reversed(self, party_scenarios):
        PIX_ERROR = party_scenarios[PAPEL_PIX_ERRO]

        payout, payload, idempotency_key = pending_payout(PIX_ERROR)
        sweep_until_dead(payload, idempotency_key)

        status, response, _payload = ObjectGenerator.create_settlement(payout["outbox"])

        assert status == 204, response
        assert outbox_state(payload, idempotency_key)["outbox_status"] == "dead"
        chain = trace(payout["ledger_transaction_key"])["chain"]
        assert [link for link in chain if link["ledger_transaction_type"] == "settlement"] == []

        status, response, _payload = ObjectGenerator.create_reversal(payout["ledger_transaction_key"])

        assert status == 201, response
        entries = trace(response["ledger_transaction_key"])["entries"]
        assert [
            (entry["direction"], entry["amount_in_cents"], entry["ledger_account_type"], entry["purpose_code"])
            for entry in entries
        ] == [("D", 450000, "clearing", "TRANSIT"), ("C", 450000, "earmark", "RENT")]
        assert (entries[1]["owner_party_key"], entries[1]["owner_role"]) == (PIX_ERROR, "landlord")
        assert balance(payload["source_account_key"]) == 450000
        # O banco foi zerado: a clearing volta ao 0 de antes do repasse.
        assert balance(clearing_key()) == 0
        assert_integrity()

    def test_outbox_dispatch_skips_row_locked_elsewhere(self, party_scenarios):
        PIX_ERROR = party_scenarios[PAPEL_PIX_ERRO]

        payout, _payload, _idempotency_key = pending_payout(PIX_ERROR)
        outbox = payout["outbox"]

        with DbUtils.hold_outbox_lock(outbox["outbox_key"]):
            assert sweep(10) == {"sent": 0, "pending": 0, "dead": 0}
            assert len(pix_dispatches(outbox["dispatch_idempotency_key"])) == 1

        assert sweep(10) == {"sent": 0, "pending": 1, "dead": 0}
        assert len(pix_dispatches(outbox["dispatch_idempotency_key"])) == 2

    def test_outbox_dispatch_limit_and_body(self, party_scenarios):
        PIX_ERROR = party_scenarios[PAPEL_PIX_ERRO]

        DbUtils.rollback()
        first_key = str(uuid4())
        _first, first_payload = ObjectGenerator.create_pending_payout(first_key, owner_party_key=PIX_ERROR)
        second_key = str(uuid4())
        _second, second_payload = ObjectGenerator.create_pending_payout(second_key, owner_party_key=PIX_ERROR)

        assert sweep(1) == {"sent": 0, "pending": 1, "dead": 0}

        assert outbox_state(first_payload, first_key)["attempt_count"] == 2
        assert outbox_state(second_payload, second_key)["attempt_count"] == 1

        for payload in [{"limit": 0}, {"limit": 101}, {"limit": "1"}, {"limit": 1, "outbox_key": str(uuid4())}]:
            status, response = RequestGenerator.POST_outbox_dispatch(payload)

            assert status == 400, (payload, response)
            assert response["code"] == "QIT000001", (payload, response)

    def test_outbox_dispatch_pending_payout_for_given_owner(self, party_scenarios):
        """O `create_pending_payout` aceita o dono da RENT (D-5): com a
        "pix_timeout" (Pix em timeout), o repasse também fica `pending`, e o
        provedor recebe a pix_key dela, não a da "pix_erro"."""
        PIX_TIMEOUT = party_scenarios[PAPEL_PIX_TIMEOUT]

        DbUtils.rollback()
        payout, _payload = ObjectGenerator.create_pending_payout(str(uuid4()), owner_party_key=PIX_TIMEOUT)

        dispatches = pix_dispatches(payout["outbox"]["dispatch_idempotency_key"])
        assert len(dispatches) == 1, dispatches
        assert dispatches[0][1]["pix_key"] == PIX_TIMEOUT_PIX_KEY
        entries = trace(payout["ledger_transaction_key"])["entries"]
        assert PIX_TIMEOUT in [entry["owner_party_key"] for entry in entries], entries

    def test_outbox_dispatch_sends_pending_later(self, party_scenarios):
        PIX_ERROR = party_scenarios[PAPEL_PIX_ERRO]

        payout, payload, idempotency_key = pending_payout(PIX_ERROR)
        dispatch_idempotency_key = payout["outbox"]["dispatch_idempotency_key"]

        status, response, webhook_payload = ObjectGenerator.create_settlement(payout["outbox"])

        assert status == 409, response
        assert response["code"] == "QIT001011"

        with RequestGenerator.accept_pix(dispatch_idempotency_key):
            assert sweep(10) == {"sent": 1, "pending": 0, "dead": 0}

        outbox = outbox_state(payload, idempotency_key)
        assert (outbox["outbox_status"], outbox["attempt_count"]) == ("sent", 1)
        assert len(pix_dispatches(dispatch_idempotency_key)) == 2

        status, response = RequestGenerator.POST_webhooks_provider(webhook_payload)

        assert status == 204, response
        chain = trace(payout["ledger_transaction_key"])["chain"]
        payout_links = [link for link in chain if link["ledger_transaction_key"] == payout["ledger_transaction_key"]]
        assert payout_links[0]["outbox_status"] == "settled"
        assert len([link for link in chain if link["ledger_transaction_type"] == "settlement"]) == 1
