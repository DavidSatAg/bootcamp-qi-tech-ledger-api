from uuid import uuid4

from tests.utils import DbUtils, ObjectGenerator, PayloadGenerator, RequestGenerator

ALFA_CLIENT = "c1c1c1c1-c1c1-4c1c-8c1c-c1c1c1c1c1c1"
ALFA = "11111111-1111-4111-8111-111111111111"
ANA = "22222222-2222-4222-8222-222222222222"
PREFEITURA = "44444444-4444-4444-8444-444444444444"
CONDOMINIO = "55555555-5555-4555-8555-555555555555"
AGUA = "66666666-6666-4666-8666-666666666666"
LUZ = "77777777-7777-4777-8777-777777777777"
CARLOS = "88888888-8888-4888-8888-888888888888"
PLATAFORMA = "99999999-9999-4999-8999-999999999999"


def owners_by_purpose(contract_ledger: dict) -> list:
    owners = []
    for account in contract_ledger["accounts"]:
        owners.append((account["purpose_code"], account["owner_party_key"], account["owner_role"]))

    return owners


def default_items() -> list:
    """Os itens do corpo padrão, prontos para um caso torcer um deles."""
    return PayloadGenerator.create_contract_ledger_payload()["items"]


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

    def test_contract_ledgers_refusals_create_nothing(self):
        DbUtils.rollback()

        iptu_to_deposit = default_items()
        iptu_to_deposit[2]["purpose_code"] = "DEPOSIT"

        unknown_purpose = default_items()
        unknown_purpose[0]["purpose_code"] = "rent"

        own_takes_everything = default_items()
        own_takes_everything[1]["value"] = "100.0000"

        cases = [
            ("IPTU vira DEPOSIT", {"items": iptu_to_deposit}, "QIT001008"),
            ("propósito desconhecido", {"items": unknown_purpose}, "QIT001028"),
            (
                "split que não fecha",
                {"items": own_takes_everything, "platform_fee_percentage": "10.0001"},
                "QIT001034",
            ),
            ("taxa acima da administração", {"platform_fee_percentage": "10.0001"}, "QIT001034"),
        ]

        for name, overrides, expected_code in cases:
            status, response = ObjectGenerator.create_contract_ledger(**overrides)

            assert status == 422, f"{name}: veio {status} {response}"
            assert response["code"] == expected_code, name

        status, response = RequestGenerator.GET_ledger_accounts({"client_key": ALFA_CLIENT})
        assert status == 200
        assert response["data"] == []

    def test_contract_ledgers_refuses_malformed_body(self):
        without_remainder = default_items()
        without_remainder[0]["type"] = "fixed"
        without_remainder[0]["value"] = 1000

        two_remainders = default_items()
        two_remainders.append(
            {
                "purpose_code": "RENT",
                "beneficiary_party_key": CARLOS,
                "beneficiary_role": "landlord",
                "type": "remainder",
            }
        )

        provider_remainder = default_items()
        provider_remainder[0]["beneficiary_role"] = "provider"

        duplicated_iptu = default_items()
        duplicated_iptu.append(dict(duplicated_iptu[2]))

        two_owns = default_items()
        second_own = next(dict(item) for item in two_owns if item["purpose_code"] == "OWN")
        second_own["beneficiary_party_key"] = CARLOS
        second_own["value"] = "1.0000"
        two_owns.append(second_own)

        without_actor = PayloadGenerator.create_contract_ledger_payload()
        del without_actor["actor"]

        extra_field = PayloadGenerator.create_contract_ledger_payload()
        extra_field["campo_que_nao_existe"] = 1

        rent_as_text = PayloadGenerator.create_contract_ledger_payload()
        rent_as_text["rent_amount_in_cents"] = "500000"

        cases = [
            ("sem remainder", PayloadGenerator.create_contract_ledger_payload(items=without_remainder)),
            ("duas remainder", PayloadGenerator.create_contract_ledger_payload(items=two_remainders)),
            ("remainder de provider", PayloadGenerator.create_contract_ledger_payload(items=provider_remainder)),
            ("IPTU duplicado", PayloadGenerator.create_contract_ledger_payload(items=duplicated_iptu)),
            ("dois OWN", PayloadGenerator.create_contract_ledger_payload(items=two_owns)),
            ("sem actor", without_actor),
            ("campo extra", extra_field),
            ("aluguel em texto", rent_as_text),
        ]

        for name, payload in cases:
            status, response = RequestGenerator.POST_contract_ledgers(payload)

            assert status == 400, f"{name}: veio {status} {response}"
            assert response["code"] == "QIT000001", name
