import re

from tests.utils import DbUtils, RequestGenerator
from tests.utils import ObjectGenerator

UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")

# O corpo do 01b §3, literal: é o que o Contrato manda e o que o mock do
# Ledger (fatia 02) responde. Esta classe prova que a API real responde
# os mesmos campos, com os mesmos tipos e os mesmos códigos.
CONTRACT_LEDGER_01B = {
    "contract_key": "0c0c0c0c-0c0c-40c0-80c0-0c0c0c0c0c0c",
    "client_key": "c1c1c1c1-c1c1-4c1c-8c1c-c1c1c1c1c1c1",
    "client_party_key": "11111111-1111-4111-8111-111111111111",
    "split_version": 1,
    "rent_amount_in_cents": 500000,
    "platform_fee_percentage": "1.0000",
    "items": [
        {"purpose_code": "RENT", "beneficiary_party_key": "22222222-2222-4222-8222-222222222222", "beneficiary_role": "landlord", "type": "remainder"},
        {"purpose_code": "OWN", "beneficiary_party_key": "11111111-1111-4111-8111-111111111111", "beneficiary_role": "administrator", "type": "percentage", "value": "10.0000"},
        {"purpose_code": "IPTU", "beneficiary_party_key": "44444444-4444-4444-8444-444444444444", "beneficiary_role": "provider", "type": "fixed", "value": 30000},
        {"purpose_code": "CONDO", "beneficiary_party_key": "55555555-5555-4555-8555-555555555555", "beneficiary_role": "provider", "type": "fixed", "value": 80000},
        {"purpose_code": "WATER", "beneficiary_party_key": "66666666-6666-4666-8666-666666666666", "beneficiary_role": "provider", "type": "fixed", "value": 12000},
        {"purpose_code": "ELECTRICITY", "beneficiary_party_key": "77777777-7777-4777-8777-777777777777", "beneficiary_role": "provider", "type": "fixed", "value": 18000},
    ],
    "actor": "contract-api",
    "reason": "ativação do contrato ALFA-2026-0042",
}

# As contas do 01b §3, na ordem: (propósito, dono, papel). As chaves de
# conta o mock fixa; a API real gera, e o teste só confere que são UUID.
ACCOUNTS_01B = [
    ("COLLECTION", None, None),
    ("RENT", "22222222-2222-4222-8222-222222222222", "landlord"),
    ("IPTU", "44444444-4444-4444-8444-444444444444", "provider"),
    ("CONDO", "55555555-5555-4555-8555-555555555555", "provider"),
    ("WATER", "66666666-6666-4666-8666-666666666666", "provider"),
    ("ELECTRICITY", "77777777-7777-4777-8777-777777777777", "provider"),
    ("OWN", "11111111-1111-4111-8111-111111111111", "administrator"),
    ("PLATFORM_FEE", "99999999-9999-4999-8999-999999999999", "platform"),
]

# O corpo do 01b §4, literal, e o 409 do mock `closure-saldo-retido.json`.
CLOSURE_01B = {"actor": "contract-api", "reason": "fim da locação ALFA-2026-0042"}
HAS_BALANCE_MOCK = {
    "title": "Account has balance",
    "description": "An account of this contract has non-zero balance.",
    "translation": "conta com saldo não pode ser encerrada",
    "code": "QIT001037",
}


class TestContrato01b:
    def test_contract_ledgers_matches_ledger_mock(self):
        DbUtils.rollback()

        status, response = RequestGenerator.POST_contract_ledgers(CONTRACT_LEDGER_01B)

        assert status == 201
        assert set(response.keys()) == {"contract_key", "split_version", "expected_amount_in_cents", "accounts"}
        assert response["contract_key"] == CONTRACT_LEDGER_01B["contract_key"]
        assert response["split_version"] == 1
        assert response["expected_amount_in_cents"] == 640000
        assert isinstance(response["expected_amount_in_cents"], int)

        accounts = []
        for account in response["accounts"]:
            assert set(account.keys()) == {"purpose_code", "ledger_account_key", "owner_party_key", "owner_role"}
            assert UUID.match(account["ledger_account_key"]), account
            accounts.append((account["purpose_code"], account["owner_party_key"], account["owner_role"]))
        assert accounts == ACCOUNTS_01B

        status, replay = RequestGenerator.POST_contract_ledgers(CONTRACT_LEDGER_01B)

        assert status == 200
        assert replay == response

        other_content = dict(CONTRACT_LEDGER_01B)
        other_content["rent_amount_in_cents"] = 409032

        status, error = RequestGenerator.POST_contract_ledgers(other_content)

        assert status == 409
        assert set(error.keys()) == {"title", "description", "translation", "code"}
        assert error["code"] == "QIT001032"
        for field in ("title", "description", "translation"):
            assert isinstance(error[field], str) and error[field] != ""

    def test_contract_ledgers_closure_matches_ledger_mock(self):
        DbUtils.rollback()

        status, response = RequestGenerator.POST_contract_ledgers(CONTRACT_LEDGER_01B)
        assert status == 201

        contract_key = CONTRACT_LEDGER_01B["contract_key"]
        status, response = RequestGenerator.POST_contract_ledgers_closure(contract_key, CLOSURE_01B)

        assert status == 200
        assert set(response.keys()) == {"contract_key", "closed_accounts"}
        assert response["contract_key"] == "0c0c0c0c-0c0c-40c0-80c0-0c0c0c0c0c0c"
        assert response["closed_accounts"] == 6
        assert isinstance(response["closed_accounts"], int)

        status, replay = RequestGenerator.POST_contract_ledgers_closure(contract_key, CLOSURE_01B)

        assert status == 200
        assert replay == response

        status, contract_ledger = ObjectGenerator.create_contract_ledger()
        assert status == 201
        other_contract_key = contract_ledger["contract_key"]
        status, _, _ = ObjectGenerator.create_inflow(other_contract_key, amount_in_cents=640000)
        assert status == 201

        status, error = RequestGenerator.POST_contract_ledgers_closure(
            other_contract_key, dict(CLOSURE_01B, reason="mock:saldo-retido")
        )

        assert status == 409
        assert error == HAS_BALANCE_MOCK
