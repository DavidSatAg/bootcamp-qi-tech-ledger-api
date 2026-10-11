from uuid import uuid4

from tests.utils import ObjectGenerator, RequestGenerator


def provision_contract(**kwargs) -> dict:
    """Provisiona um contrato novo e devolve a chave de cada conta, pelo propósito."""
    status, contract_ledger = ObjectGenerator.create_contract_ledger(**kwargs)
    assert status == 201, contract_ledger

    keys = {account["purpose_code"]: account["ledger_account_key"] for account in contract_ledger["accounts"]}
    keys["contract_key"] = contract_ledger["contract_key"]

    return keys


def collected_contract() -> dict:
    """P + TX1: o contrato provisionado com a entrada de 640000 na COLLECTION."""
    keys = provision_contract()

    status, response, _payload = ObjectGenerator.create_inflow(keys["contract_key"])
    assert status == 201, response

    return keys


def balance(ledger_account_key: str) -> int:
    status, ledger_account = RequestGenerator.GET_ledger_account(ledger_account_key)
    assert status == 200, ledger_account

    return ledger_account["balance_in_cents"]


def legs(ledger_transaction_key: str) -> list:
    """As pernas do trace, na ordem dele: (direção, conta, centavos)."""
    status, trace = RequestGenerator.GET_transfer_trace(ledger_transaction_key)
    assert status == 200, trace

    return [(entry["direction"], entry["ledger_account_key"], entry["amount_in_cents"]) for entry in trace["entries"]]


def percentage(value: str, target_account_key: str) -> dict:
    return {"target_account_key": target_account_key, "type": "percentage", "value": value}


def fixed(value: int, target_account_key: str) -> dict:
    return {"target_account_key": target_account_key, "type": "fixed", "value": value}


def remainder(target_account_key: str) -> dict:
    return {"target_account_key": target_account_key, "type": "remainder"}


class TestInternalAllocations:
    def test_transfers_internal_splits_into_three_allocations(self):
        """CU-J2 (D0013 :41-48): percentual, fixo e `remainder` num pedido
        só; a mesma chave e o mesmo corpo devolvem a mesma transação."""
        keys = collected_contract()
        own_before = balance(keys["OWN"])
        idempotency_key = str(uuid4())
        allocations = [
            percentage("10.0000", keys["OWN"]),
            fixed(30000, keys["IPTU"]),
            remainder(keys["RENT"]),
        ]

        status, response, _payload = ObjectGenerator.create_internal_allocations(
            keys["COLLECTION"], allocations, idempotency_key=idempotency_key
        )

        assert status == 201, response
        assert response["ledger_transaction_type"] == "internal"
        assert legs(response["ledger_transaction_key"]) == [
            ("D", keys["COLLECTION"], 500000),
            ("C", keys["OWN"], 50000),
            ("C", keys["IPTU"], 30000),
            ("C", keys["RENT"], 420000),
        ]
        assert balance(keys["COLLECTION"]) == 140000
        assert balance(keys["IPTU"]) == 30000
        assert balance(keys["RENT"]) == 420000
        assert balance(keys["OWN"]) - own_before == 50000

        status, replay, _payload = ObjectGenerator.create_internal_allocations(
            keys["COLLECTION"], allocations, idempotency_key=idempotency_key
        )

        assert status == 201, replay
        assert replay["ledger_transaction_key"] == response["ledger_transaction_key"]
        assert balance(keys["COLLECTION"]) == 140000

    def test_transfers_internal_percentage_residue_goes_to_remainder(self):
        """CU-J3 (D0013 :173-174): o piso do percentual deixa o centavo na
        `remainder`."""
        keys = collected_contract()

        status, response, _payload = ObjectGenerator.create_internal_allocations(
            keys["COLLECTION"],
            [percentage("10.0000", keys["OWN"]), remainder(keys["RENT"])],
            gross_amount_in_cents=100001,
        )

        assert status == 201, response
        assert legs(response["ledger_transaction_key"]) == [
            ("D", keys["COLLECTION"], 100001),
            ("C", keys["OWN"], 10000),
            ("C", keys["RENT"], 90001),
        ]
        assert balance(keys["COLLECTION"]) == 539999

    def test_transfers_internal_without_remainder_exact_sum(self):
        """CU-J4 (05:166-167): sem `remainder`, os percentuais fecham o bruto."""
        keys = collected_contract()

        status, response, _payload = ObjectGenerator.create_internal_allocations(
            keys["COLLECTION"], [percentage("90.0000", keys["RENT"]), percentage("10.0000", keys["OWN"])]
        )

        assert status == 201, response
        assert legs(response["ledger_transaction_key"]) == [
            ("D", keys["COLLECTION"], 500000),
            ("C", keys["RENT"], 450000),
            ("C", keys["OWN"], 50000),
        ]
        assert balance(keys["COLLECTION"]) == 140000

    def test_transfers_internal_largest_remainder_ties_to_own(self):
        """CU-J9 (D0004 :30-32, :54-63): sem `remainder`, o maior resto leva
        o centavo; o empate no corte o manda para a `own` do cliente, somado
        à alocação dela ou numa perna nova. O mesmo corpo, as mesmas partes."""
        keys = collected_contract()
        even_split = [percentage("50.0000", keys["RENT"]), percentage("50.0000", keys["OWN"])]
        cases = [
            (
                [percentage("7.0000", keys["OWN"]), percentage("93.0000", keys["RENT"])],
                [("C", keys["OWN"], 7000), ("C", keys["RENT"], 93001)],
            ),
            (even_split, [("C", keys["RENT"], 50000), ("C", keys["OWN"], 50001)]),
            (even_split, [("C", keys["RENT"], 50000), ("C", keys["OWN"], 50001)]),
            (
                [percentage("50.0000", keys["RENT"]), percentage("50.0000", keys["IPTU"])],
                [("C", keys["RENT"], 50000), ("C", keys["IPTU"], 50000), ("C", keys["OWN"], 1)],
            ),
        ]

        for allocations, credits in cases:
            status, response, _payload = ObjectGenerator.create_internal_allocations(
                keys["COLLECTION"], allocations, gross_amount_in_cents=100001
            )

            assert status == 201, (allocations, response)
            assert legs(response["ledger_transaction_key"]) == [("D", keys["COLLECTION"], 100001)] + credits

        assert balance(keys["COLLECTION"]) == 239996

    def test_transfers_internal_refuses_malformed_allocations(self):
        """CU-J6 e J8 e o formato de cada tipo: o schema recusa, 400."""
        keys = provision_contract()
        cases = [
            [percentage("10.00001", keys["OWN"])],
            [remainder(keys["RENT"]), remainder(keys["IPTU"]), fixed(30000, keys["OWN"])],
            [percentage(10, keys["OWN"]), remainder(keys["RENT"])],
            [fixed("30000", keys["IPTU"]), remainder(keys["RENT"])],
            [fixed(0, keys["IPTU"]), remainder(keys["RENT"])],
            [{"target_account_key": keys["OWN"], "type": "percentage"}, remainder(keys["RENT"])],
            [dict(remainder(keys["RENT"]), value=30000)],
            [{"target_account_key": keys["RENT"], "type": "amount", "value": 30000}],
            [{"type": "remainder"}],
        ]

        for allocations in cases:
            status, response, _payload = ObjectGenerator.create_internal_allocations(keys["COLLECTION"], allocations)

            assert status == 400, (allocations, response)
            assert response["code"] == "QIT000001", (allocations, response)

    def test_transfers_internal_unknown_target_returns_404(self):
        """Qualquer destino inexistente é 018, e nada se move (S15a D-01)."""
        keys = collected_contract()
        own_before = balance(keys["OWN"])

        status, response, _payload = ObjectGenerator.create_internal_allocations(
            keys["COLLECTION"],
            [percentage("10.0000", keys["OWN"]), fixed(30000, keys["IPTU"]), remainder(str(uuid4()))],
        )

        assert status == 404, response
        assert response["code"] == "QIT001018"
        assert balance(keys["COLLECTION"]) == 640000
        assert balance(keys["OWN"]) == own_before
