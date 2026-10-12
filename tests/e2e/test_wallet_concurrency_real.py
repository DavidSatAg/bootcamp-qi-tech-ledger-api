"""Cópia de tests/integration/wallet/test_wallet_concurrency.py contra o
Cadastro de verdade. O original continua intacto, contra o party-mock.

A única mudança é a dona da carteira: o `create_funded_wallet()`, que sem
argumento cairia no 2222… do valor padrão, recebe a "aprovada" criada pela
fixture `party_scenarios`. A abertura da carteira consulta o Cadastro real.
"""
from threading import Barrier, Thread

from tests.utils import ObjectGenerator, RequestGenerator
from tests.utils.party_scenarios import APROVADA

PLATFORM_CLIENT = "9c9c9c9c-9c9c-49c9-89c9-9c9c9c9c9c9c"
THREADS = 2
JOIN_TIMEOUT_SECONDS = 30


def balance(ledger_account_key: str) -> int:
    status, ledger_account = RequestGenerator.GET_ledger_account(ledger_account_key)
    assert status == 200, ledger_account

    return ledger_account["balance_in_cents"]


def pay_together(contract_key: str, wallet_key: str, amount_in_cents: int) -> list:
    """Dois pagamentos da mesma carteira, com chaves diferentes, em duas
    threads soltas juntas. Devolve [(status, corpo)]."""
    barrier = Barrier(THREADS)
    results = []

    def pay() -> None:
        barrier.wait()
        status, response, _payload = ObjectGenerator.pay_with_wallet(
            contract_key, wallet_key, amount_in_cents=amount_in_cents
        )
        results.append((status, response))

    threads = [Thread(target=pay, daemon=True) for _ in range(THREADS)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=JOIN_TIMEOUT_SECONDS)
        assert not thread.is_alive(), "a requisição não voltou dentro do prazo"

    return results


class TestWalletConcurrency:
    def test_transfers_inflow_wallet_concurrent_never_overdraw(self, party_scenarios):
        """Os dois pagamentos querem o saldo inteiro: o segundo espera a
        trava da carteira e soma o saldo depois dela, já zerado (W8)."""
        ANA = party_scenarios[APROVADA]

        wallet_key = ObjectGenerator.create_funded_wallet(ANA)
        status, contract_ledger = ObjectGenerator.create_contract_ledger()
        assert status == 201, contract_ledger
        collection = contract_ledger["accounts"][0]
        assert collection["purpose_code"] == "COLLECTION"
        wallet_before = balance(wallet_key)

        results = pay_together(contract_ledger["contract_key"], wallet_key, wallet_before)

        assert len(results) == THREADS, results
        assert sorted(status for status, _response in results) == [201, 422], results
        refused = [response for status, response in results if status == 422]
        assert refused[0]["code"] == "QIT001009", results
        assert balance(wallet_key) == 0
        assert balance(collection["ledger_account_key"]) == wallet_before

        status, integrity = RequestGenerator.GET_integrity({"client_key": PLATFORM_CLIENT})
        assert status == 200, integrity
        assert integrity["difference_in_cents"] == 0
