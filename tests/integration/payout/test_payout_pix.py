from uuid import uuid4

from tests.utils import ObjectGenerator, PayloadGenerator, RequestGenerator

ALFA_CLIENT = "c1c1c1c1-c1c1-4c1c-8c1c-c1c1c1c1c1c1"
ANA = "22222222-2222-4222-8222-222222222222"
PENDING_PARTY = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
UNKNOWN_PARTY = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
PARTY_DOWN = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
WITHOUT_PIX_KEY = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
OTHER_AMOUNT = 80000


def provision_contract() -> dict:
    """Provisiona um contrato novo e devolve a chave de cada conta, pelo propósito."""
    status, contract_ledger = ObjectGenerator.create_contract_ledger()
    assert status == 201, contract_ledger

    keys = {account["purpose_code"]: account["ledger_account_key"] for account in contract_ledger["accounts"]}
    keys["contract_key"] = contract_ledger["contract_key"]

    return keys


def rent_key(contract_ledger: dict) -> str:
    """A chave da RENT no corpo do provisionamento."""
    for account in contract_ledger["accounts"]:
        if account["purpose_code"] == "RENT":
            return account["ledger_account_key"]

    raise AssertionError(contract_ledger)


def balance(ledger_account_key: str) -> int:
    status, ledger_account = RequestGenerator.GET_ledger_account(ledger_account_key)
    assert status == 200, ledger_account

    return ledger_account["balance_in_cents"]


def clearing_key() -> str:
    """A `clearing/TRANSIT` da Imobiliária Alfa: o destino de todo repasse dela."""
    return ObjectGenerator.get_client_account_key(ALFA_CLIENT, "TRANSIT")


class TestPayoutPix:
    def test_transfers_payout_unknown_source_returns_404(self):
        status, response, _payload = ObjectGenerator.create_payout(str(uuid4()))

        assert status == 404, response
        assert response["code"] == "QIT001018"

    def test_transfers_payout_refuses_malformed_body(self):
        keys = provision_contract()
        rent_key = keys["RENT"]
        valid = PayloadGenerator.create_payout_payload(rent_key)
        without_actor = dict(valid)
        del without_actor["actor"]
        without_period = dict(valid)
        del without_period["period_reference"]
        cases = [
            (valid, None),
            (valid, "k" * 256),
            (PayloadGenerator.create_payout_payload(rent_key, amount_in_cents=0), str(uuid4())),
            (PayloadGenerator.create_payout_payload(rent_key, amount_in_cents="450000"), str(uuid4())),
            (PayloadGenerator.create_payout_payload(rent_key, destination="ted"), str(uuid4())),
            (without_actor, str(uuid4())),
            (without_period, str(uuid4())),
            (PayloadGenerator.create_payout_payload(rent_key, period_reference="2026-9"), str(uuid4())),
            (dict(valid, pix_key="ana.locadora@example.com"), str(uuid4())),
        ]

        for payload, idempotency_key in cases:
            status, response = RequestGenerator.POST_transfers_payout(payload, idempotency_key=idempotency_key)

            assert status == 400, (payload, idempotency_key, response)
            assert response["code"] == "QIT000001", (payload, idempotency_key, response)

    def test_transfers_payout_from_collection_refused(self):
        keys = provision_contract()
        status, response, _payload = ObjectGenerator.create_inflow(keys["contract_key"])
        assert status == 201, response
        clearing_before = balance(clearing_key())

        status, response, _payload = ObjectGenerator.create_payout(keys["COLLECTION"], amount_in_cents=640000)

        assert status == 422, response
        assert response["code"] == "QIT001008"
        assert balance(keys["COLLECTION"]) == 640000
        assert balance(clearing_key()) == clearing_before

    def test_transfers_payout_forbidden_pair_before_balance(self):
        """COLLECTION vazia: o par proibido sai antes da trava e do saldo,
        e a mesma chave repete o 008 gravado."""
        keys = provision_contract()
        idempotency_key = str(uuid4())

        status, response, _payload = ObjectGenerator.create_payout(keys["COLLECTION"], idempotency_key=idempotency_key)

        assert status == 422, response
        assert response["code"] == "QIT001008"

        status, response, _payload = ObjectGenerator.create_payout(keys["COLLECTION"], idempotency_key=idempotency_key)

        assert status == 422, response
        assert response["code"] == "QIT001008"

    def test_transfers_payout_insufficient_balance(self):
        rent = rent_key(ObjectGenerator.create_divided_contract(ANA))
        clearing_before = balance(clearing_key())

        status, response, _payload = ObjectGenerator.create_payout(rent, amount_in_cents=640000)

        assert status == 422, response
        assert response["code"] == "QIT001009"
        assert balance(rent) == 450000
        assert balance(clearing_key()) == clearing_before

    def test_transfers_payout_party_unavailable_records_nothing(self):
        """Cadastro fora: 040 antes do motor, nada gravado; a mesma chave com
        outro corpo dá 040 de novo, e não 010."""
        rent = rent_key(ObjectGenerator.create_divided_contract(PARTY_DOWN))
        clearing_before = balance(clearing_key())
        idempotency_key = str(uuid4())

        status, response, _payload = ObjectGenerator.create_payout(rent, idempotency_key=idempotency_key)

        assert status == 503, response
        assert response["code"] == "QIT001040"

        status, response, _payload = ObjectGenerator.create_payout(
            rent, idempotency_key=idempotency_key, amount_in_cents=OTHER_AMOUNT
        )

        assert status == 503, response
        assert response["code"] == "QIT001040"
        assert balance(rent) == 450000
        assert balance(clearing_key()) == clearing_before

    def test_transfers_payout_owner_not_active(self):
        """Dono pendente ou desconhecido: 038 gravado (D1); a mesma chave
        repete o 038, e com outro corpo dá 010."""
        for party_key in [PENDING_PARTY, UNKNOWN_PARTY]:
            rent = rent_key(ObjectGenerator.create_divided_contract(party_key))
            idempotency_key = str(uuid4())

            status, response, _payload = ObjectGenerator.create_payout(rent, idempotency_key=idempotency_key)

            assert status == 409, (party_key, response)
            assert response["code"] == "QIT001038", (party_key, response)

            status, response, _payload = ObjectGenerator.create_payout(rent, idempotency_key=idempotency_key)

            assert status == 409, (party_key, response)
            assert response["code"] == "QIT001038", (party_key, response)

            status, response, _payload = ObjectGenerator.create_payout(
                rent, idempotency_key=idempotency_key, amount_in_cents=OTHER_AMOUNT
            )

            assert status == 409, (party_key, response)
            assert response["code"] == "QIT001010", (party_key, response)
            assert balance(rent) == 450000

    def test_transfers_payout_owner_without_pix_key(self):
        rent = rent_key(ObjectGenerator.create_divided_contract(WITHOUT_PIX_KEY))

        status, response, _payload = ObjectGenerator.create_payout(rent)

        assert status == 422, response
        assert response["code"] == "QIT001039"
        assert balance(rent) == 450000
