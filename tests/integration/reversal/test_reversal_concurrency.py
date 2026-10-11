from threading import Barrier, Thread
from uuid import uuid4

from tests.utils import DbUtils, ObjectGenerator, PayloadGenerator, RequestGenerator

ALFA_CLIENT = "c1c1c1c1-c1c1-4c1c-8c1c-c1c1c1c1c1c1"


def provision_contract() -> dict:
    """Provisiona um contrato novo e devolve a chave de cada conta, pelo
    propósito, e a do contrato."""
    status, contract_ledger = ObjectGenerator.create_contract_ledger()
    assert status == 201, contract_ledger

    keys = {account["purpose_code"]: account["ledger_account_key"] for account in contract_ledger["accounts"]}
    keys["contract_key"] = contract_ledger["contract_key"]

    return keys


def balance(ledger_account_key: str) -> int:
    status, ledger_account = RequestGenerator.GET_ledger_account(ledger_account_key)
    assert status == 200, ledger_account

    return ledger_account["balance_in_cents"]


def inflow(contract_key: str, **kwargs) -> dict:
    status, response, _payload = ObjectGenerator.create_inflow(contract_key, **kwargs)
    assert status == 201, response

    return response


def split(contract_key: str, **kwargs) -> dict:
    status, response, _payload = ObjectGenerator.create_split(contract_key, **kwargs)
    assert status == 201, response

    return response


def assert_book_closes() -> None:
    status, integrity = RequestGenerator.GET_integrity({"client_key": ALFA_CLIENT})
    assert status == 200, integrity
    assert integrity["difference_in_cents"] == 0
    assert integrity["negative_accounts"] == []


def reverse_together(requests: list) -> list:
    """Um estorno por (chave da original, payload), cada um com a sua
    `Idempotency-Key`, soltos juntos. Devolve [(status, corpo)] ordenado
    por status."""
    barrier = Barrier(len(requests))
    results = []

    def post(ledger_transaction_key: str, payload: dict) -> None:
        barrier.wait()
        results.append(
            RequestGenerator.POST_transfers_reversal(ledger_transaction_key, payload, idempotency_key=str(uuid4()))
        )

    threads = [Thread(target=post, args=request) for request in requests]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    return sorted(results, key=lambda result: result[0])


class TestReversalConcurrency:
    def test_transfers_reversal_original_lock_times_out(self):
        """A linha da original travada por fora além do lock_timeout: 011,
        gravado sob a chave; com chave nova, depois, o estorno passa (RN-05)."""
        keys = provision_contract()
        tx1_key = inflow(keys["contract_key"])["ledger_transaction_key"]
        payload = PayloadGenerator.create_reversal_payload()
        idempotency_key = str(uuid4())

        with DbUtils.hold_transaction_lock(tx1_key):
            status, response = RequestGenerator.POST_transfers_reversal(
                tx1_key, payload, idempotency_key=idempotency_key
            )

        assert status == 409, response
        assert response["code"] == "QIT001011"
        assert balance(keys["COLLECTION"]) == 640000

        status, response = RequestGenerator.POST_transfers_reversal(tx1_key, payload, idempotency_key=idempotency_key)

        assert status == 409, response
        assert response["code"] == "QIT001011"

        status, response = RequestGenerator.POST_transfers_reversal(tx1_key, payload, idempotency_key=str(uuid4()))

        assert status == 201, response
        assert balance(keys["COLLECTION"]) == 0

    def test_transfers_reversal_concurrent_never_exceed(self):
        """Três parciais de 320000 sobre 640000 (RFC :372): cada um soma os
        anteriores depois da trava da original; o terceiro não cabe (CU-F5)."""
        keys = provision_contract()
        tx1_key = inflow(keys["contract_key"])["ledger_transaction_key"]
        payload = PayloadGenerator.create_reversal_payload(amount_in_cents=320000)

        results = reverse_together([(tx1_key, payload)] * 3)

        assert [status for status, _response in results] == [201, 201, 422], results
        assert results[2][1]["code"] == "QIT001015"
        assert balance(keys["COLLECTION"]) == 0
        assert_book_closes()

    def test_transfers_reversal_concurrent_split_reversals(self):
        """Os estornos das divisões de duas competências travam as mesmas
        contas na mesma ordem: nenhum deadlock (D5)."""
        keys = provision_contract()
        inflow(keys["contract_key"])
        september = split(keys["contract_key"])
        inflow(keys["contract_key"], period_reference="2026-10")
        october = split(keys["contract_key"], period_reference="2026-10")
        payload = PayloadGenerator.create_reversal_payload()

        results = reverse_together(
            [(september["ledger_transaction_key"], payload), (october["ledger_transaction_key"], payload)]
        )

        assert [status for status, _response in results] == [201, 201], results
        assert balance(keys["COLLECTION"]) == 1280000
        assert balance(keys["RENT"]) == 0
        assert_book_closes()
