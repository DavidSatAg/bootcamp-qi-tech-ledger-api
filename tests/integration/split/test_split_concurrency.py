from threading import Barrier, Thread
from uuid import uuid4

from tests.utils import DbUtils, ObjectGenerator, PayloadGenerator, RequestGenerator

ALFA_CLIENT = "c1c1c1c1-c1c1-4c1c-8c1c-c1c1c1c1c1c1"
THREADS = 2


def provision_contract() -> dict:
    """Provisiona um contrato novo e devolve a chave de cada conta, pelo propósito."""
    status, contract_ledger = ObjectGenerator.create_contract_ledger()
    assert status == 201, contract_ledger

    keys = {account["purpose_code"]: account["ledger_account_key"] for account in contract_ledger["accounts"]}
    keys["contract_key"] = contract_ledger["contract_key"]

    return keys


def balance(ledger_account_key: str) -> int:
    status, ledger_account = RequestGenerator.GET_ledger_account(ledger_account_key)
    assert status == 200, ledger_account

    return ledger_account["balance_in_cents"]


def split_together(payloads: list) -> list:
    """Uma divisão por payload, cada uma com a sua chave, soltas juntas.
    Devolve [(status, corpo)] ordenado por status."""
    barrier = Barrier(len(payloads))
    results = []

    def post(payload: dict) -> None:
        barrier.wait()
        results.append(RequestGenerator.POST_transfers_split(payload, idempotency_key=str(uuid4())))

    threads = [Thread(target=post, args=(payload,)) for payload in payloads]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    return sorted(results, key=lambda result: result[0])


class TestSplitConcurrency:
    def test_transfers_split_concurrent_same_period(self):
        """A segunda espera a trava da COLLECTION e, quando a primeira
        commita, vê a divisão dela antes do SUM: 036, uma divisão só."""
        keys = provision_contract()
        status, response, _payload = ObjectGenerator.create_inflow(keys["contract_key"])
        assert status == 201, response
        payload = PayloadGenerator.create_split_payload(keys["contract_key"])

        results = split_together([payload] * THREADS)

        assert [status for status, _response in results] == [201, 409], results
        assert results[1][1]["code"] == "QIT001036"
        assert balance(keys["RENT"]) == 450000
        assert balance(keys["COLLECTION"]) == 0

    def test_transfers_split_concurrent_periods_never_overdraw(self):
        """Competências diferentes, saldo para uma: a segunda soma depois da
        trava e não acha o dinheiro que a primeira já levou: 009."""
        keys = provision_contract()
        status, response, _payload = ObjectGenerator.create_inflow(keys["contract_key"])
        assert status == 201, response
        payloads = [
            PayloadGenerator.create_split_payload(keys["contract_key"], period_reference="2026-09"),
            PayloadGenerator.create_split_payload(keys["contract_key"], period_reference="2026-10"),
        ]

        results = split_together(payloads)

        assert [status for status, _response in results] == [201, 422], results
        assert results[1][1]["code"] == "QIT001009"
        assert balance(keys["COLLECTION"]) == 0

    def test_transfers_split_lock_timeout_conflicts(self):
        """A COLLECTION travada por fora além do lock_timeout: 011, gravado
        sob a chave; nada se move; com chave nova, depois, a divisão passa."""
        keys = provision_contract()
        status, response, _payload = ObjectGenerator.create_inflow(keys["contract_key"])
        assert status == 201, response
        payload = PayloadGenerator.create_split_payload(keys["contract_key"])
        idempotency_key = str(uuid4())
        with DbUtils.hold_row_lock(keys["COLLECTION"]):
            status, response = RequestGenerator.POST_transfers_split(payload, idempotency_key=idempotency_key)

        assert status == 409, response
        assert response["code"] == "QIT001011"
        assert balance(keys["COLLECTION"]) == 640000
        assert balance(keys["RENT"]) == 0
        status, integrity = RequestGenerator.GET_integrity({"client_key": ALFA_CLIENT})
        assert status == 200, integrity
        assert integrity["difference_in_cents"] == 0

        status, response = RequestGenerator.POST_transfers_split(payload, idempotency_key=idempotency_key)

        assert status == 409, response
        assert response["code"] == "QIT001011"

        status, response = RequestGenerator.POST_transfers_split(payload, idempotency_key=str(uuid4()))

        assert status == 201, response
        assert balance(keys["COLLECTION"]) == 0
        assert balance(keys["RENT"]) == 450000
