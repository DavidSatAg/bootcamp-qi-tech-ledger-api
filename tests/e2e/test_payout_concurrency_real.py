"""Cópia de tests/integration/payout/test_payout_concurrency.py contra o
Cadastro de verdade. O original continua intacto, contra o party-mock.

A única mudança é a origem do dono da RENT: a Ana (2222…) vira a "aprovada"
criada pela fixture `party_scenarios`. Os dez repasses consultam o Cadastro
real ao mesmo tempo, cada um pelo dono da RENT.
"""
from threading import Barrier, Thread
from uuid import uuid4

from tests.utils import ObjectGenerator, PayloadGenerator, RequestGenerator
from tests.utils.party_scenarios import APROVADA

ALFA_CLIENT = "c1c1c1c1-c1c1-4c1c-8c1c-c1c1c1c1c1c1"
THREADS = 10
PAYOUT_AMOUNT = 80000


def rent_key(contract_ledger: dict) -> str:
    """A chave da RENT no corpo do provisionamento."""
    for account in contract_ledger["accounts"]:
        if account["purpose_code"] == "RENT":
            return account["ledger_account_key"]

    raise AssertionError(contract_ledger)


def balance(ledger_account_key: str) -> int:
    status, ledger_account = RequestGenerator.GET_ledger_account(ledger_account_key)
    assert status == 200, ledger_account

    return ledger_account["balance_in_cents"]


def payout_together(payloads: list) -> list:
    """Um repasse por payload, cada um com a sua chave, soltos juntos.
    Devolve [(status, corpo)] ordenado por status."""
    barrier = Barrier(len(payloads))
    results = []

    def post(payload: dict) -> None:
        barrier.wait()
        results.append(RequestGenerator.POST_transfers_payout(payload, idempotency_key=str(uuid4())))

    threads = [Thread(target=post, args=(payload,)) for payload in payloads]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    return sorted(results, key=lambda result: result[0])


class TestPayoutConcurrency:
    def test_transfers_payout_concurrent_never_overdraw(self, party_scenarios):
        """450000 na RENT, dez repasses de 80000 juntos: cada um soma o saldo
        depois da trava, e só os cinco que cabem passam (CU-D3, H4)."""
        ANA = party_scenarios[APROVADA]

        rent = rent_key(ObjectGenerator.create_divided_contract(ANA))
        payload = PayloadGenerator.create_payout_payload(rent, amount_in_cents=PAYOUT_AMOUNT)

        results = payout_together([payload] * THREADS)

        statuses = [status for status, _response in results]
        assert statuses == [202] * 5 + [422] * 5, results
        assert all(response["code"] == "QIT001009" for status, response in results if status == 422), results
        assert balance(rent) == 50000
        status, integrity = RequestGenerator.GET_integrity({"client_key": ALFA_CLIENT})
        assert status == 200, integrity
        assert integrity["difference_in_cents"] == 0
