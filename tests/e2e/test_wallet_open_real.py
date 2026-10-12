"""Cópia de tests/integration/wallet/test_wallet_open.py contra o Cadastro de
verdade (experimento: um arquivo só). O original continua intacto, contra o
party-mock.

A única mudança é a origem das chaves: as mágicas do party-mock viram partes
criadas de verdade pela fixture `party_scenarios` (2222… → aprovada,
aaaa… → pendente), e a inexistente (bbbb…) vira um UUID novo, nunca
cadastrado. As da plataforma (9999…, 9c9c…) já são reais: o Cadastro as
semeia.

O caso `cccc…` (Cadastro fora do ar) NÃO está aqui: contra o real ele só
existe parando o container, e isso é o tests/e2e/test_party_api_down.py, que
roda isolado e confere o mesmo 503 QIT001040 sem WALLET gravada.
"""
from uuid import uuid4

from tests.utils import DbUtils, ObjectGenerator, PayloadGenerator, RequestGenerator
from tests.utils.party_scenarios import APROVADA, PENDENTE as PAPEL_PENDENTE

PLATFORM_CLIENT = "9c9c9c9c-9c9c-49c9-89c9-9c9c9c9c9c9c"
PLATAFORMA = "99999999-9999-4999-8999-999999999999"


def books_of(accounts: list) -> list:
    books = []
    for account in accounts:
        books.append((account["purpose_code"], account["owner_party_key"], account["owner_role"]))

    return books


def purposes_of(accounts: list) -> list:
    return [account["purpose_code"] for account in accounts]


class TestWalletOpen:
    def test_wallets_opens_in_platform_books(self, party_scenarios):
        ANA = party_scenarios[APROVADA]

        DbUtils.rollback()

        status, response = ObjectGenerator.open_wallet(ANA)

        assert status == 201, response
        assert response["client_key"] == PLATFORM_CLIENT
        assert response["ledger_account_type"] == "own"
        assert response["purpose_code"] == "WALLET"
        assert response["owner_party_key"] == ANA
        assert response["owner_role"] == "holder"
        assert response["balance_in_cents"] == 0

        status, accounts = RequestGenerator.GET_ledger_accounts({"client_key": PLATFORM_CLIENT, "limit": "100"})
        assert status == 200, accounts
        assert books_of(accounts["data"]) == [
            ("CASH", None, None),
            ("UNALLOCATED", None, None),
            ("TRANSIT", None, None),
            ("OWN", PLATAFORMA, "administrator"),
            ("PLATFORM_FEE", PLATAFORMA, "platform"),
            ("WALLET", ANA, "holder"),
        ]
        assert accounts["data"][5]["ledger_account_key"] == response["ledger_account_key"]

    def test_wallets_reopen_returns_existing(self, party_scenarios):
        ANA = party_scenarios[APROVADA]

        status, first = ObjectGenerator.open_wallet(ANA)
        assert status in (200, 201), first

        status, second = ObjectGenerator.open_wallet(ANA)

        assert status == 200, second
        assert second["ledger_account_key"] == first["ledger_account_key"]

    def test_wallets_party_not_active_or_unavailable(self, party_scenarios):
        PENDENTE = party_scenarios[PAPEL_PENDENTE]
        INEXISTENTE = str(uuid4())

        cases = [
            (PENDENTE, 409, "QIT001038"),
            (INEXISTENTE, 409, "QIT001038"),
            # (FORA_DO_AR, 503, "QIT001040"): ver o topo do arquivo.
        ]

        for party_key, expected_status, expected_code in cases:
            status, response = ObjectGenerator.open_wallet(party_key)

            assert status == expected_status, (party_key, response)
            assert response["code"] == expected_code, (party_key, response)

            status, accounts = RequestGenerator.GET_ledger_accounts({"owner_party_key": party_key, "limit": "100"})
            assert status == 200, accounts
            assert "WALLET" not in purposes_of(accounts["data"]), party_key

    def test_wallets_refuses_malformed_body(self, party_scenarios):
        ANA = party_scenarios[APROVADA]

        without_party_key = PayloadGenerator.create_wallet_payload(party_key=ANA)
        del without_party_key["party_key"]

        # "2222" aqui não é a chave mágica: é uma party_key curta demais, de
        # propósito, para o 400 do formato.
        short_party_key = PayloadGenerator.create_wallet_payload(party_key="2222")

        without_actor = PayloadGenerator.create_wallet_payload(party_key=ANA)
        del without_actor["actor"]

        with_pix_key = PayloadGenerator.create_wallet_payload(party_key=ANA)
        with_pix_key["pix_key"] = "ana.locadora@example.com"

        for payload in [without_party_key, short_party_key, without_actor, with_pix_key]:
            status, response = RequestGenerator.POST_wallets(payload)

            assert status == 400, (payload, response)
            assert response["code"] == "QIT000001", (payload, response)
