from threading import Barrier, Thread
from uuid import uuid4

from tests.utils import ObjectGenerator, PayloadGenerator, RequestGenerator

THREADS = 2


def provision_contract() -> tuple:
    """Provisiona um contrato novo e devolve (contract_key, chave da COLLECTION)."""
    status, contract_ledger = ObjectGenerator.create_contract_ledger()
    assert status == 201, contract_ledger

    collection = contract_ledger["accounts"][0]
    assert collection["purpose_code"] == "COLLECTION"

    return contract_ledger["contract_key"], collection["ledger_account_key"]


def balance(ledger_account_key: str) -> int:
    status, ledger_account = RequestGenerator.GET_ledger_account(ledger_account_key)
    assert status == 200, ledger_account

    return ledger_account["balance_in_cents"]


def post_together(payload: dict, idempotency_key: str) -> list:
    """O mesmo pedido, com a mesma chave, em duas threads soltas juntas."""
    barrier = Barrier(THREADS)
    results = []

    def post() -> None:
        barrier.wait()
        results.append(RequestGenerator.POST_transfers_inflow(payload, idempotency_key=idempotency_key))

    threads = [Thread(target=post) for _ in range(THREADS)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    return results


class TestInflowConcurrency:
    def test_transfers_inflow_concurrent_same_key(self):
        """A segunda espera no INSERT do registro e, quando a primeira
        commita, colide e replica: uma transação só, a mesma chave nas duas."""
        contract_key, collection_key = provision_contract()
        payload = PayloadGenerator.create_inflow_payload(contract_key)

        results = post_together(payload, payload["end_to_end_id"])

        statuses = [status for status, _response in results]
        assert statuses == [201, 201], results
        assert results[0][1]["ledger_transaction_key"] == results[1][1]["ledger_transaction_key"]
        assert balance(collection_key) == 640000

    def test_transfers_inflow_concurrent_same_key_error(self):
        """Um Pix já aceito, de novo sob outra chave, em duas threads: a
        primeira grava o 010; a segunda, que esperava, replica o erro."""
        contract_key, collection_key = provision_contract()
        payload = PayloadGenerator.create_inflow_payload(contract_key)

        status, response = RequestGenerator.POST_transfers_inflow(payload, idempotency_key=str(uuid4()))
        assert status == 201, response

        results = post_together(payload, str(uuid4()))

        statuses = [status for status, _response in results]
        assert statuses == [409, 409], results
        assert [response["code"] for _status, response in results] == ["QIT001010", "QIT001010"]
        assert balance(collection_key) == 640000
