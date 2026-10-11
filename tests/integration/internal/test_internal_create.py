from uuid import uuid4

from tests.utils import ObjectGenerator, PayloadGenerator, RequestGenerator

ALFA_CLIENT = "c1c1c1c1-c1c1-4c1c-8c1c-c1c1c1c1c1c1"


def provision_contract(**kwargs) -> dict:
    """Provisiona um contrato novo e devolve a chave de cada conta, pelo propósito."""
    status, contract_ledger = ObjectGenerator.create_contract_ledger(**kwargs)
    assert status == 201, contract_ledger

    keys = {account["purpose_code"]: account["ledger_account_key"] for account in contract_ledger["accounts"]}
    keys["contract_key"] = contract_ledger["contract_key"]

    return keys


def divided_contract() -> dict:
    """Contrato provisionado com a TX1 (640000, 2026-09) e a TX2 (a divisão):
    COLLECTION 0, RENT 450000, IPTU 30000, e a `own` da Alfa com +45000."""
    keys = provision_contract()

    status, response, _payload = ObjectGenerator.create_inflow(keys["contract_key"])
    assert status == 201, response

    status, response, _payload = ObjectGenerator.create_split(keys["contract_key"])
    assert status == 201, response

    return keys


def balance(ledger_account_key: str) -> int:
    status, ledger_account = RequestGenerator.GET_ledger_account(ledger_account_key)
    assert status == 200, ledger_account

    return ledger_account["balance_in_cents"]


class TestInternalCreate:
    def test_transfers_internal_moves_between_same_client_accounts(self):
        """TX8 do remodelagem/05: a devolução de taxa, da `own` da Alfa para
        a COLLECTION do contrato (controle positivo, D2)."""
        keys = divided_contract()
        assert balance(keys["COLLECTION"]) == 0
        own_before = balance(keys["OWN"])

        status, response, _payload = ObjectGenerator.create_internal(
            keys["OWN"], keys["COLLECTION"], gross_amount_in_cents=45000
        )

        assert status == 201, response
        assert response["ledger_transaction_type"] == "internal"
        assert response["contract_key"] is None
        assert response["period_reference"] is None
        assert response["payer_party_key"] is None
        assert response["split_version"] is None

        status, trace = RequestGenerator.GET_transfer_trace(response["ledger_transaction_key"])
        assert status == 200, trace
        entries = [
            (entry["direction"], entry["purpose_code"], entry["amount_in_cents"], entry["ledger_account_key"],
             entry["owner_party_key"], entry["owner_role"])
            for entry in trace["entries"]
        ]
        assert entries == [
            ("D", "OWN", 45000, keys["OWN"], "11111111-1111-4111-8111-111111111111", "administrator"),
            ("C", "COLLECTION", 45000, keys["COLLECTION"], None, None),
        ]
        assert trace["chain"] == []

        assert balance(keys["COLLECTION"]) == 45000
        assert balance(keys["OWN"]) - own_before == -45000

        status, integrity = RequestGenerator.GET_integrity({"client_key": ALFA_CLIENT})
        assert status == 200, integrity
        assert integrity["difference_in_cents"] == 0

    def test_transfers_internal_rent_to_iptu_refused(self):
        """CU-C4: não há RENT → IPTU na `purpose_rule`."""
        keys = divided_contract()
        assert balance(keys["RENT"]) == 450000
        assert balance(keys["IPTU"]) == 30000

        status, response, _payload = ObjectGenerator.create_internal(
            keys["RENT"], keys["IPTU"], gross_amount_in_cents=30000
        )

        assert status == 422, response
        assert response["code"] == "QIT001008"
        assert balance(keys["RENT"]) == 450000
        assert balance(keys["IPTU"]) == 30000

    def test_transfers_internal_other_contract_refused(self):
        """CU-C7: COLLECTION → IPTU exige o mesmo contrato."""
        contract_a = provision_contract()
        status, response, _payload = ObjectGenerator.create_inflow(contract_a["contract_key"])
        assert status == 201, response
        contract_b = provision_contract()

        status, response, _payload = ObjectGenerator.create_internal(
            contract_a["COLLECTION"], contract_b["IPTU"], gross_amount_in_cents=30000
        )

        assert status == 422, response
        assert response["code"] == "QIT001008"
        assert balance(contract_a["COLLECTION"]) == 640000
        assert balance(contract_b["IPTU"]) == 0

    def test_transfers_internal_unknown_account_returns_404(self):
        """O 018 sai antes do motor e não grava (D-01): a mesma chave, com o
        destino que existe, chega ao motor e leva o 008, não o 010."""
        contract = provision_contract()
        unknown_source = str(uuid4())
        idempotency_key = str(uuid4())
        status, response, _payload = ObjectGenerator.create_internal(
            unknown_source, contract["COLLECTION"], idempotency_key=idempotency_key
        )

        assert status == 404, response
        assert response["code"] == "QIT001018"

        idempotency_key = str(uuid4())
        status, response, _payload = ObjectGenerator.create_internal(
            contract["COLLECTION"], str(uuid4()), idempotency_key=idempotency_key
        )

        assert status == 404, response
        assert response["code"] == "QIT001018"

        other_contract = provision_contract()
        status, response, _payload = ObjectGenerator.create_internal(
            contract["COLLECTION"], other_contract["IPTU"], idempotency_key=idempotency_key
        )

        assert status == 422, response
        assert response["code"] == "QIT001008"

    def test_transfers_internal_refuses_malformed_body(self):
        """O `value_date` impossível só é conferido depois das contas (RN-02):
        por isso as duas existem, COLLECTION → RENT de um contrato."""
        keys = provision_contract()
        valid = PayloadGenerator.create_internal_payload(keys["COLLECTION"], keys["RENT"])
        without_actor = dict(valid)
        del without_actor["actor"]
        without_reason = dict(valid)
        del without_reason["reason"]
        two_remainders = dict(valid, allocations=valid["allocations"] * 2)
        cases = [
            (valid, None),
            (valid, "k" * 256),
            (without_actor, str(uuid4())),
            (without_reason, str(uuid4())),
            (dict(valid, gross_amount_in_cents=0), str(uuid4())),
            (dict(valid, allocations=[]), str(uuid4())),
            (two_remainders, str(uuid4())),
            (dict(valid, amount_in_cents=45000), str(uuid4())),
            (dict(valid, value_date="2026-02-30T00:00:00Z"), str(uuid4())),
        ]

        for payload, idempotency_key in cases:
            status, response = RequestGenerator.POST_transfers_internal(payload, idempotency_key=idempotency_key)

            assert status == 400, (payload, idempotency_key, response)
            assert response["code"] == "QIT000001", (payload, idempotency_key, response)
