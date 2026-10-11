from tests.utils import ObjectGenerator, PayloadGenerator, RequestGenerator

BRUNO = "33333333-3333-4333-8333-333333333333"


def contract_ledger_owned_by(client_party_key: str, contract_key: str = None) -> dict:
    """O provisionamento do caso do remodelagem/05 no livro da Alfa (c1c1…),
    com o dono do cliente trocado."""
    payload = PayloadGenerator.create_contract_ledger_payload(contract_key=contract_key)
    payload["client_party_key"] = client_party_key

    return payload


class TestContractLedgerOwner:
    def test_contract_ledgers_owner_diverges_from_client_book(self):
        """Cliente e parte são 1:1: o livro da Alfa já tem a `own/OWN` da
        1111…, e um provisionamento com outro dono é bug do Contrato (L19)."""
        status, contract_ledger = ObjectGenerator.create_contract_ledger()
        assert status == 201, contract_ledger

        status, response = RequestGenerator.POST_contract_ledgers(contract_ledger_owned_by(BRUNO))

        assert status == 400, response
        assert response["code"] == "QIT000001"
        status, accounts = RequestGenerator.GET_ledger_accounts({"owner_party_key": BRUNO})
        assert status == 200, accounts
        assert accounts["data"] == []

        status, response = RequestGenerator.POST_contract_ledgers(
            contract_ledger_owned_by(BRUNO, contract_key=contract_ledger["contract_key"])
        )

        assert status == 409, response
        assert response["code"] == "QIT001032"
