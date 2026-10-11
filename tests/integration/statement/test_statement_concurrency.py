from threading import Barrier, Thread

from tests.utils import ObjectGenerator

TX1_VALUE_DATE = "2026-09-05T14:22:00Z"

# Teto de espera por thread: o `lock_timeout` (3s) mais folga. Uma thread
# pendurada falha o teste em vez de pendurar a suíte.
JOIN_TIMEOUT_SECONDS = 15


def run_together(*calls) -> list:
    """Cada chamada numa thread, soltas juntas pelo Barrier; os resultados
    na ordem das chamadas."""
    barrier = Barrier(len(calls))
    results = [None] * len(calls)

    def run(index: int, call) -> None:
        barrier.wait()
        results[index] = call()

    threads = [Thread(target=run, args=(index, call), daemon=True) for index, call in enumerate(calls)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(JOIN_TIMEOUT_SECONDS)
        assert not thread.is_alive(), "a requisição não voltou dentro do tempo"

    return results


class TestStatementConcurrency:
    def test_statement_concurrent_successors(self):
        """Duas emissões do sucessor ao mesmo tempo, com chaves diferentes.

        A asserção vale para qualquer intercalação: uma emite o sucessor
        (201) e a outra, servida depois da primeira, vê o sucessor vigente e
        responde 017 (RN-07). Nenhum 500 e nenhum segundo sucessor.
        """
        status, contract_ledger = ObjectGenerator.create_contract_ledger()
        assert status == 201, contract_ledger
        accounts = {account["purpose_code"]: account["ledger_account_key"] for account in contract_ledger["accounts"]}
        collection_key = accounts["COLLECTION"]

        status, inflow, _payload = ObjectGenerator.create_inflow(contract_ledger["contract_key"], value_date=TX1_VALUE_DATE)
        assert status == 201, inflow
        status, original, _payload = ObjectGenerator.create_statement(collection_key)
        assert status == 201, original
        status, late_inflow, _payload = ObjectGenerator.create_inflow(
            contract_ledger["contract_key"], value_date=TX1_VALUE_DATE
        )
        assert status == 201, late_inflow

        results = run_together(
            lambda: ObjectGenerator.create_statement(collection_key),
            lambda: ObjectGenerator.create_statement(collection_key),
        )

        statuses = sorted(status for status, _response, _payload in results)
        assert statuses == [201, 409], results

        conflict = [response for status, response, _payload in results if status == 409][0]
        assert conflict["code"] == "QIT001017", conflict
