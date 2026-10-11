from uuid import uuid4

from tests.utils import DbUtils, ObjectGenerator, PayloadGenerator, RequestGenerator

ALFA_CLIENT = "c1c1c1c1-c1c1-4c1c-8c1c-c1c1c1c1c1c1"
ALFA = "11111111-1111-4111-8111-111111111111"
ANA = "22222222-2222-4222-8222-222222222222"
PREFEITURA = "44444444-4444-4444-8444-444444444444"
CONDOMINIO = "55555555-5555-4555-8555-555555555555"
AGUA = "66666666-6666-4666-8666-666666666666"
LUZ = "77777777-7777-4777-8777-777777777777"
PLATAFORMA = "99999999-9999-4999-8999-999999999999"


def owners_by_purpose(contract_ledger: dict) -> list:
    owners = []
    for account in contract_ledger["accounts"]:
        owners.append((account["purpose_code"], account["owner_party_key"], account["owner_role"]))

    return owners


def keys_by_purpose(contract_ledger: dict) -> dict:
    keys = dict()
    for account in contract_ledger["accounts"]:
        keys[account["purpose_code"]] = account["ledger_account_key"]

    return keys


class TestContractLedgerProvision:
    def test_contract_ledgers_returns_split_accounts(self):
        payload = PayloadGenerator.create_contract_ledger_payload()

        status, response = RequestGenerator.POST_contract_ledgers(payload)

        assert status == 201
        assert response["contract_key"] == payload["contract_key"]
        assert response["split_version"] == 1
        assert response["expected_amount_in_cents"] == 640000
        assert owners_by_purpose(response) == [
            ("COLLECTION", None, None),
            ("RENT", ANA, "landlord"),
            ("IPTU", PREFEITURA, "provider"),
            ("CONDO", CONDOMINIO, "provider"),
            ("WATER", AGUA, "provider"),
            ("ELECTRICITY", LUZ, "provider"),
            ("OWN", ALFA, "administrator"),
            ("PLATFORM_FEE", PLATAFORMA, "platform"),
        ]
        account_keys = [account["ledger_account_key"] for account in response["accounts"]]
        assert len(set(account_keys)) == 8

    def test_contract_ledgers_reuses_client_books(self):
        DbUtils.rollback()

        status, first_contract = ObjectGenerator.create_contract_ledger()
        assert status == 201

        status, response = RequestGenerator.GET_ledger_accounts({"contract_key": first_contract["contract_key"]})
        assert status == 200
        assert len(response["data"]) == 6

        status, response = RequestGenerator.GET_ledger_accounts({"client_key": ALFA_CLIENT, "limit": 100})
        assert status == 200
        assert len(response["data"]) == 11

        status, second_contract = ObjectGenerator.create_contract_ledger()
        assert status == 201
        assert second_contract["contract_key"] != first_contract["contract_key"]

        assert keys_by_purpose(second_contract)["OWN"] == keys_by_purpose(first_contract)["OWN"]
        assert keys_by_purpose(second_contract)["PLATFORM_FEE"] == keys_by_purpose(first_contract)["PLATFORM_FEE"]
        assert keys_by_purpose(second_contract)["RENT"] != keys_by_purpose(first_contract)["RENT"]

        status, response = RequestGenerator.GET_ledger_accounts({"client_key": ALFA_CLIENT, "limit": 100})
        assert status == 200
        assert len(response["data"]) == 17

    def test_contract_ledgers_new_version_reuses_earmarks(self):
        status, first_version = ObjectGenerator.create_contract_ledger(split_version=1)
        assert status == 201

        status, second_version = ObjectGenerator.create_contract_ledger(
            contract_key=first_version["contract_key"], split_version=2
        )

        assert status == 201
        assert second_version["split_version"] == 2
        assert keys_by_purpose(second_version) == keys_by_purpose(first_version)

    def test_contract_ledgers_version_rules(self):
        # Cada caso: os passos (versão, aluguel) num contrato novo, o status
        # de cada passo e o código esperado no último. Aluguel None é o
        # padrão; 409032 é o aluguel que o mock do 01b recusa com 032.
        cases = [
            ("v1 repetida", [(1, None), (1, None)], [201, 200], None),
            ("v1, v2 e v1 de novo", [(1, None), (2, None), (1, None)], [201, 201, 200], None),
            ("v1 com outro conteúdo", [(1, None), (1, 409032)], [201, 409], "QIT001032"),
            ("v1 antiga com outro conteúdo", [(1, None), (2, None), (1, 409032)], [201, 201, 409], "QIT001033"),
            ("contrato novo em v2", [(2, None)], [409], "QIT001033"),
            ("v1 e depois v3", [(1, None), (3, None)], [201, 409], "QIT001033"),
        ]

        for name, steps, expected_statuses, expected_code in cases:
            contract_key = str(uuid4())
            responses = []

            for (split_version, rent_amount_in_cents), expected_status in zip(steps, expected_statuses):
                status, response = ObjectGenerator.create_contract_ledger(
                    contract_key=contract_key,
                    split_version=split_version,
                    rent_amount_in_cents=rent_amount_in_cents,
                )
                assert status == expected_status, f"{name}: veio {status} {response}"
                responses.append(response)

            if expected_code is not None:
                assert responses[-1]["code"] == expected_code, name
            else:
                replayed_version = steps[-1][0]
                first_response_of_version = responses[[step[0] for step in steps].index(replayed_version)]
                assert responses[-1] == first_response_of_version, name
