from threading import Barrier, Thread

from tests.utils import DbUtils, PayloadGenerator, RequestGenerator

ROUNDS = 5
ALFA_CLIENT = "c1c1c1c1-c1c1-4c1c-8c1c-c1c1c1c1c1c1"
BRUNO = "33333333-3333-4333-8333-333333333333"


def owned_by(client_party_key: str) -> dict:
    """O provisionamento do caso do remodelagem/05, com o dono do livro da
    Alfa trocado (o item OWN vai para a `own/OWN` do cliente)."""
    payload = PayloadGenerator.create_contract_ledger_payload()
    payload["client_party_key"] = client_party_key

    return payload


def provision_together(*payloads) -> list:
    """Cada provisionamento numa thread, soltos juntos pelo Barrier; os
    resultados na ordem dos payloads."""
    barrier = Barrier(len(payloads))
    results = [None] * len(payloads)

    def run(index: int, payload: dict) -> None:
        barrier.wait()
        results[index] = RequestGenerator.POST_contract_ledgers(payload)

    threads = [Thread(target=run, args=(index, payload)) for index, payload in enumerate(payloads)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    return results


def client_owns() -> list:
    """As `own/OWN` do livro da Alfa, pela listagem."""
    status, page = RequestGenerator.GET_ledger_accounts({"client_key": ALFA_CLIENT, "limit": "100"})
    assert status == 200, page

    return [
        ledger_account
        for ledger_account in page["data"]
        if (ledger_account["ledger_account_type"], ledger_account["purpose_code"]) == ("own", "OWN")
    ]


class TestContractLedgerOwnerConcurrency:
    def test_contract_ledgers_concurrent_first_provision_owner_diverges(self):
        """Os dois primeiros provisionamentos de um cliente novo, com donos
        diferentes, ao mesmo tempo (L30): um cria, o outro é bug do
        Contrato (400 QIT000001), e o livro fica com uma `own/OWN` só.

        A corrida não é determinística: a rodada se repete, cada uma com o
        banco zerado, para que a Alfa seja cliente novo em todas."""
        for _ in range(ROUNDS):
            DbUtils.rollback()

            results = provision_together(owned_by("11111111-1111-4111-8111-111111111111"), owned_by(BRUNO))

            outcomes = sorted((status, response.get("code")) for status, response in results)
            assert outcomes == [(201, None), (400, "QIT000001")], results
            assert len(client_owns()) == 1

    def test_contract_ledgers_concurrent_first_provision_same_owner(self):
        """Mesmo cliente novo, mesmo dono, contratos diferentes, ao mesmo
        tempo: os dois criam (201) e dividem a mesma `own/OWN`."""
        for _ in range(ROUNDS):
            DbUtils.rollback()

            results = provision_together(
                PayloadGenerator.create_contract_ledger_payload(),
                PayloadGenerator.create_contract_ledger_payload(),
            )

            assert sorted(status for status, _response in results) == [201, 201], results
            owns = client_owns()
            assert len(owns) == 1
            for _status, contract_ledger in results:
                own_keys = [
                    account["ledger_account_key"]
                    for account in contract_ledger["accounts"]
                    if account["purpose_code"] == "OWN"
                ]
                assert own_keys == [owns[0]["ledger_account_key"]], contract_ledger
