from threading import Barrier, Thread

from tests.utils import PayloadGenerator, RequestGenerator

THREADS = 2


class TestContractLedgerConcurrency:
    def test_contract_ledgers_concurrent_same_version(self):
        """O mesmo provisionamento, duas vezes ao mesmo tempo.

        A asserção vale para qualquer intercalação: um cria (201), o outro
        enxerga o que o primeiro gravou e responde o replay (200), com as
        mesmas chaves. O caminho da reexecução (RN-14) só roda quando as
        duas transações se cruzam de fato, e isso o Barrier favorece, mas
        não garante.
        """
        payload = PayloadGenerator.create_contract_ledger_payload()
        barrier = Barrier(THREADS)
        results = []

        def provision() -> None:
            barrier.wait()
            results.append(RequestGenerator.POST_contract_ledgers(payload))

        threads = [Thread(target=provision) for _ in range(THREADS)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        statuses = sorted(status for status, _response in results)
        assert statuses == [200, 201], results

        first_body = results[0][1]
        second_body = results[1][1]
        assert first_body["accounts"] == second_body["accounts"]
