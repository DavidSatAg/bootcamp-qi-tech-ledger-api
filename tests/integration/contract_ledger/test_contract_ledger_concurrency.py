from threading import Barrier, Thread

from tests.utils import DbUtils, ObjectGenerator, PayloadGenerator, RequestGenerator

THREADS = 2
ROUNDS = 5
ALFA_CLIENT = "c1c1c1c1-c1c1-4c1c-8c1c-c1c1c1c1c1c1"


def keys_by_purpose(contract_ledger: dict) -> dict:
    keys = dict()
    for account in contract_ledger["accounts"]:
        keys[account["purpose_code"]] = account["ledger_account_key"]

    return keys


def account_of(ledger_account_key: str) -> dict:
    status, response = RequestGenerator.GET_ledger_account(ledger_account_key)
    assert status == 200, response

    return response


def external_key() -> str:
    """O `external/CASH` da Imobiliária Alfa: nasce com o primeiro livro do
    cliente, e por isso está na primeira página da listagem."""
    status, page = RequestGenerator.GET_ledger_accounts({"client_key": ALFA_CLIENT, "limit": "100"})
    assert status == 200, page

    for ledger_account in page["data"]:
        if ledger_account["purpose_code"] == "CASH":
            return ledger_account["ledger_account_key"]

    raise AssertionError(f"external/CASH ausente na listagem: {page}")


def provision_contract() -> tuple:
    """Provisiona um contrato novo e devolve (contract_key, chaves por propósito)."""
    status, contract_ledger = ObjectGenerator.create_contract_ledger()
    assert status == 201, contract_ledger

    return contract_ledger["contract_key"], keys_by_purpose(contract_ledger)


def run_together(*calls) -> list:
    """Cada chamada numa thread, soltas juntas pelo Barrier; os resultados
    na ordem das chamadas."""
    barrier = Barrier(len(calls))
    results = [None] * len(calls)

    def run(index: int, call) -> None:
        barrier.wait()
        results[index] = call()

    threads = [Thread(target=run, args=(index, call)) for index, call in enumerate(calls)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    return results


def outcome(status: int, response: dict) -> tuple:
    """(status, código do erro), ou (status, None) no sucesso."""
    if status >= 400:
        return status, response.get("code")

    return status, None


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

    def test_contract_ledgers_closure_concurrent_inflow(self):
        """Fumaça: entrada e encerramento juntos. Qualquer intercalação dá
        um dos dois desfechos, e nunca a entrada aceita numa conta fechada."""
        for _ in range(ROUNDS):
            contract_key, keys = provision_contract()

            inflow_result, closure_result = run_together(
                lambda: ObjectGenerator.create_inflow(contract_key, amount_in_cents=640000)[:2],
                lambda: ObjectGenerator.close_contract_ledger(contract_key),
            )

            outcomes = (outcome(*inflow_result), outcome(*closure_result))
            collection = account_of(keys["COLLECTION"])

            if outcomes == ((201, None), (409, "QIT001037")):
                assert collection["status"] == "active", outcomes
                assert collection["balance_in_cents"] == 640000, outcomes
            elif outcomes == ((409, "QIT001012"), (200, None)):
                assert collection["status"] == "closed", outcomes
                assert collection["balance_in_cents"] == 0, outcomes
            else:
                raise AssertionError(f"desfecho fora dos dois possíveis: {outcomes}")

    def test_contract_ledgers_closure_while_inflow_waits(self):
        """O caso do meio, determinístico: a entrada passa o passo 2 e para
        na FK da perna `D external`, travada pelo teste; o encerramento
        commita nesse intervalo; a entrada, solta, tem de dar 012."""
        contract_key, keys = provision_contract()
        inflow_results = []

        def inflow() -> None:
            inflow_results.append(ObjectGenerator.create_inflow(contract_key, amount_in_cents=640000)[:2])

        thread = Thread(target=inflow)
        with DbUtils.hold_row_lock(external_key()):
            thread.start()
            thread.join(timeout=0.5)
            assert thread.is_alive()

            status, response = ObjectGenerator.close_contract_ledger(contract_key)
            assert status == 200, response
            assert thread.is_alive()

        thread.join(timeout=10)
        assert not thread.is_alive()

        status, response = inflow_results[0]
        collection = account_of(keys["COLLECTION"])
        assert (status, response.get("code"), collection["status"], collection["balance_in_cents"]) == (
            409, "QIT001012", "closed", 0
        ), response

    def test_contract_ledgers_closure_lock_timeout_conflicts(self):
        """Uma conta do contrato travada por fora além do lock_timeout: 011,
        e nenhuma fecha; solta a trava, o encerramento passa (L26)."""
        contract_key, keys = provision_contract()

        with DbUtils.hold_row_lock(keys["RENT"]):
            status, response = ObjectGenerator.close_contract_ledger(contract_key)

            assert status == 409, response
            assert response["code"] == "QIT001011"

        assert account_of(keys["RENT"])["status"] == "active"
        assert account_of(keys["COLLECTION"])["status"] == "active"

        status, response = ObjectGenerator.close_contract_ledger(contract_key)

        assert status == 200, response
        assert account_of(keys["RENT"])["status"] == "closed"

    def test_contract_ledgers_closure_concurrent_closures(self):
        contract_key, keys = provision_contract()

        results = run_together(
            lambda: ObjectGenerator.close_contract_ledger(contract_key),
            lambda: ObjectGenerator.close_contract_ledger(contract_key),
        )

        assert [status for status, _response in results] == [200, 200], results
        assert results[0][1] == results[1][1]
        rent = account_of(keys["RENT"])
        assert sorted(status_event["status"] for status_event in rent["status_events"]) == ["active", "closed"]
