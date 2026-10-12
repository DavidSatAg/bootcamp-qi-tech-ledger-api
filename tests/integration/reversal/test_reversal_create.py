from uuid import uuid4

from tests.utils import ObjectGenerator, PayloadGenerator, RequestGenerator

ALFA_CLIENT = "c1c1c1c1-c1c1-4c1c-8c1c-c1c1c1c1c1c1"
LANDLORD = "22222222-2222-4222-8222-222222222222"
PLATFORM = "99999999-9999-4999-8999-999999999999"
EARMARKS = ["RENT", "IPTU", "CONDO", "WATER", "ELECTRICITY"]


def provision_contract(**kwargs) -> dict:
    """Provisiona um contrato novo e devolve a chave de cada conta, pelo
    propósito, e a do contrato."""
    status, contract_ledger = ObjectGenerator.create_contract_ledger(**kwargs)
    assert status == 201, contract_ledger

    keys = {account["purpose_code"]: account["ledger_account_key"] for account in contract_ledger["accounts"]}
    keys["contract_key"] = contract_ledger["contract_key"]

    return keys


def balance(ledger_account_key: str) -> int:
    status, ledger_account = RequestGenerator.GET_ledger_account(ledger_account_key)
    assert status == 200, ledger_account

    return ledger_account["balance_in_cents"]


def inflow(contract_key: str, **kwargs) -> dict:
    """A TX1: a entrada de 640000 na competência 2026-09."""
    status, response, _payload = ObjectGenerator.create_inflow(contract_key, **kwargs)
    assert status == 201, response

    return response


def cash_key() -> str:
    """O `external/CASH` da Imobiliária Alfa: o dinheiro de verdade no banco."""
    return ObjectGenerator.get_client_account_key(ALFA_CLIENT, "CASH")


def assert_book_closes() -> None:
    status, integrity = RequestGenerator.GET_integrity({"client_key": ALFA_CLIENT})
    assert status == 200, integrity
    assert integrity["difference_in_cents"] == 0
    assert integrity["negative_accounts"] == []


def split(contract_key: str, **kwargs) -> dict:
    """A TX2: a divisão da competência 2026-09."""
    status, response, _payload = ObjectGenerator.create_split(contract_key, **kwargs)
    assert status == 201, response

    return response


def trace(ledger_transaction_key: str) -> dict:
    status, response = RequestGenerator.GET_transfer_trace(ledger_transaction_key)
    assert status == 200, response

    return response


def legs(entries: list) -> list:
    """As pernas do trace como (direção, tipo da conta, propósito, valor)."""
    return [
        (entry["direction"], entry["ledger_account_type"], entry["purpose_code"], entry["amount_in_cents"])
        for entry in entries
    ]


def reverse(ledger_transaction_key: str, **kwargs) -> dict:
    status, response, _payload = ObjectGenerator.create_reversal(ledger_transaction_key, **kwargs)
    assert status == 201, response

    return response


class TestReversalCreate:
    def test_transfers_reversal_unknown_transaction_returns_404(self):
        payload = PayloadGenerator.create_reversal_payload()
        unknown_key = str(uuid4())

        for _attempt in range(2):
            status, response = RequestGenerator.POST_transfers_reversal(
                unknown_key, payload, idempotency_key=str(uuid4())
            )

            assert status == 404, response
            assert response["code"] == "QIT001020"

    def test_transfers_reversal_refuses_malformed_body(self):
        keys = provision_contract()
        tx1 = inflow(keys["contract_key"])
        valid = PayloadGenerator.create_reversal_payload()
        without_actor = dict(valid)
        del without_actor["actor"]
        without_reason = dict(valid)
        del without_reason["reason"]
        cases = [
            (valid, None),
            (valid, "k" * 256),
            (without_actor, str(uuid4())),
            (without_reason, str(uuid4())),
            (dict(valid, reason=""), str(uuid4())),
            (dict(valid, amount_in_cents=0), str(uuid4())),
            (dict(valid, amount_in_cents="450000"), str(uuid4())),
            (dict(valid, value_date="2026-09-06T10:00:00Z"), str(uuid4())),
        ]

        for payload, idempotency_key in cases:
            status, response = RequestGenerator.POST_transfers_reversal(
                tx1["ledger_transaction_key"], payload, idempotency_key=idempotency_key
            )

            assert status == 400, (payload, idempotency_key, response)
            assert response["code"] == "QIT000001", (payload, idempotency_key, response)

        assert balance(keys["COLLECTION"]) == 640000

    def test_transfers_reversal_ignores_purpose_rule(self):
        """Não há par COLLECTION → CASH na `purpose_rule` (G :117-138): o
        estorno não a consulta (G :354)."""
        keys = provision_contract()
        tx1 = inflow(keys["contract_key"])

        response = reverse(tx1["ledger_transaction_key"])

        assert response["ledger_transaction_type"] == "reversal"
        assert response["reverses_transaction_key"] == tx1["ledger_transaction_key"]
        assert legs(trace(response["ledger_transaction_key"])["entries"]) == [
            ("D", "earmark", "COLLECTION", 640000),
            ("C", "external", "CASH", 640000),
        ]
        assert balance(keys["COLLECTION"]) == 0

    def test_transfers_reversal_key_scoped_by_original(self):
        """A mesma chave e o mesmo corpo em originais diferentes são dois
        estornos: o escopo tem a chave da original (RN-02, D3)."""
        keys_a = provision_contract()
        keys_b = provision_contract()
        tx1_a = inflow(keys_a["contract_key"])
        tx1_b = inflow(keys_b["contract_key"])
        idempotency_key = str(uuid4())

        reversal_a = reverse(tx1_a["ledger_transaction_key"], idempotency_key=idempotency_key)
        reversal_b = reverse(tx1_b["ledger_transaction_key"], idempotency_key=idempotency_key)
        replay_a = reverse(tx1_a["ledger_transaction_key"], idempotency_key=idempotency_key)

        assert reversal_b["ledger_transaction_key"] != reversal_a["ledger_transaction_key"]
        assert replay_a["ledger_transaction_key"] == reversal_a["ledger_transaction_key"]
        assert replay_a["reverses_transaction_key"] == tx1_a["ledger_transaction_key"]
        assert reversal_b["reverses_transaction_key"] == tx1_b["ledger_transaction_key"]
        assert balance(keys_a["COLLECTION"]) == 0
        assert balance(keys_b["COLLECTION"]) == 0

    def test_transfers_reversal_partials_capped_by_original(self):
        """Os parciais somam até a original e nem um centavo além (RN-05;
        CU-F2–F4)."""
        keys = provision_contract()
        tx1 = inflow(keys["contract_key"])
        tx1_key = tx1["ledger_transaction_key"]

        first = reverse(tx1_key, amount_in_cents=450000)

        assert legs(trace(first["ledger_transaction_key"])["entries"]) == [
            ("D", "earmark", "COLLECTION", 450000),
            ("C", "external", "CASH", 450000),
        ]
        reverse(tx1_key, amount_in_cents=80000)
        payload = PayloadGenerator.create_reversal_payload(amount_in_cents=140000)
        idempotency_key = str(uuid4())

        for _attempt in range(2):
            status, response = RequestGenerator.POST_transfers_reversal(
                tx1_key, payload, idempotency_key=idempotency_key
            )

            assert status == 422, response
            assert response["code"] == "QIT001015"

        reverse(tx1_key, amount_in_cents=110000)

        assert balance(keys["COLLECTION"]) == 0
        chain = trace(tx1_key)["chain"]
        reversals = [link for link in chain if link["ledger_transaction_type"] == "reversal"]
        assert len(reversals) == 3
        assert {link["reverses_transaction_key"] for link in reversals} == {tx1_key}

    def test_transfers_reversal_reversal_cannot_be_reversed(self):
        keys = provision_contract()
        tx1 = inflow(keys["contract_key"])
        reversal = reverse(tx1["ledger_transaction_key"])
        payload = PayloadGenerator.create_reversal_payload()
        idempotency_key = str(uuid4())

        for _attempt in range(2):
            status, response = RequestGenerator.POST_transfers_reversal(
                reversal["ledger_transaction_key"], payload, idempotency_key=idempotency_key
            )

            assert status == 422, response
            assert response["code"] == "QIT001016"

        assert balance(keys["COLLECTION"]) == 0

    def test_transfers_reversal_split_reverses_every_leg(self):
        """A divisão volta inteira: cada perna invertida, as da plataforma
        também. Parcial só com pernas iguais (D4)."""
        keys = provision_contract()
        inflow(keys["contract_key"])
        tx2 = split(keys["contract_key"])
        tx2_key = tx2["ledger_transaction_key"]
        own_before = balance(keys["OWN"])
        revenue_before = balance(keys["PLATFORM_FEE"])

        status, response, _payload = ObjectGenerator.create_reversal(tx2_key, amount_in_cents=5000)

        assert status == 400, response
        assert response["code"] == "QIT000001"

        response = reverse(tx2_key)

        entries = trace(response["ledger_transaction_key"])["entries"]
        assert [(entry["direction"], entry["purpose_code"], entry["amount_in_cents"]) for entry in entries] == [
            ("D", "RENT", 450000),
            ("D", "OWN", 50000),
            ("D", "IPTU", 30000),
            ("D", "CONDO", 80000),
            ("D", "WATER", 12000),
            ("D", "ELECTRICITY", 18000),
            ("D", "PLATFORM_FEE", 5000),
            ("C", "COLLECTION", 640000),
            ("C", "OWN", 5000),
        ]
        assert (entries[0]["owner_party_key"], entries[0]["owner_role"]) == (LANDLORD, "landlord")
        assert (entries[6]["owner_party_key"], entries[6]["owner_role"]) == (PLATFORM, "platform")
        assert sum(entry["amount_in_cents"] for entry in entries if entry["direction"] == "D") == 645000
        assert sum(entry["amount_in_cents"] for entry in entries if entry["direction"] == "C") == 645000
        assert balance(keys["COLLECTION"]) == 640000
        for purpose_code in EARMARKS:
            assert balance(keys[purpose_code]) == 0, purpose_code
        assert balance(keys["OWN"]) - own_before == -45000
        assert balance(keys["PLATFORM_FEE"]) - revenue_before == -5000

        status, response, _payload = ObjectGenerator.create_reversal(tx2_key)

        assert status == 422, response
        assert response["code"] == "QIT001015"

    def test_transfers_reversal_distributed_inflow_goes_negative(self):
        """A entrada já dividida volta assim mesmo: o estorno não confere
        saldo, e a COLLECTION fica negativa com o estorno no histórico
        (RN-06; CU-F1, H2)."""
        keys = provision_contract()
        tx1 = inflow(keys["contract_key"])
        external_after_tx1 = balance(cash_key())
        split(keys["contract_key"])

        response = reverse(tx1["ledger_transaction_key"])

        assert response["ledger_transaction_type"] == "reversal"
        assert response["contract_key"] == keys["contract_key"]
        assert response["period_reference"] == "2026-09"
        assert response["payer_party_key"] is None
        assert response["end_to_end_id"] is None
        assert response["reverses_transaction_key"] == tx1["ledger_transaction_key"]
        assert legs(trace(response["ledger_transaction_key"])["entries"]) == [
            ("D", "earmark", "COLLECTION", 640000),
            ("C", "external", "CASH", 640000),
        ]
        assert balance(keys["COLLECTION"]) == -640000
        assert balance(keys["RENT"]) == 450000
        assert balance(cash_key()) - external_after_tx1 == -640000
        assert_book_closes()

    def test_transfers_reversal_closed_account_refuses(self):
        """Conta encerrada não aceita estorno: 012 no passo 2, gravado na
        rota e não gravado no MED (RN-08; D1)."""
        keys = provision_contract()
        status, tx1, inflow_payload = ObjectGenerator.create_inflow(keys["contract_key"])
        assert status == 201, tx1
        tx1_key = tx1["ledger_transaction_key"]
        reverse(tx1_key)
        status, response = ObjectGenerator.close_contract_ledger(keys["contract_key"])
        assert status == 200, response
        payload = PayloadGenerator.create_reversal_payload()
        idempotency_key = str(uuid4())

        for _attempt in range(2):
            status, response = RequestGenerator.POST_transfers_reversal(tx1_key, payload, idempotency_key=idempotency_key)

            assert status == 409, response
            assert response["code"] == "QIT001012"

        med_payload = PayloadGenerator.create_med_payload(inflow_payload["end_to_end_id"])

        for _attempt in range(2):
            status, response = RequestGenerator.POST_webhooks_provider(med_payload)

            assert status == 409, response
            assert response["code"] == "QIT001012"

        assert balance(keys["COLLECTION"]) == 0
