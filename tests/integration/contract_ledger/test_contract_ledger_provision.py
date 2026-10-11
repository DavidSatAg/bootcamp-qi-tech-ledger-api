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
