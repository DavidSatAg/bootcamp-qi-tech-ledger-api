from tests.utils import PayloadGenerator, RequestGenerator

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
