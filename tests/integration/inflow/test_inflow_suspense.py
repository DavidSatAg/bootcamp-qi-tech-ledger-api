from tests.utils import ObjectGenerator, PayloadGenerator, RequestGenerator

ALFA_CLIENT = "c1c1c1c1-c1c1-4c1c-8c1c-c1c1c1c1c1c1"
UNKNOWN_CLIENT = "c404c404-c404-4c40-8c40-c404c404c404"
CARLOS = "33333333-3333-4333-8333-333333333333"


def provision_contract() -> dict:
    """O cenário: um contrato novo da Imobiliária Alfa, que garante os cinco
    livros do cliente c1c1… (S04)."""
    status, contract_ledger = ObjectGenerator.create_contract_ledger()
    assert status == 201, contract_ledger

    return contract_ledger


class TestInflowSuspense:
    def test_transfers_inflow_suspense_unknown_client_returns_404(self):
        status, response, _payload = ObjectGenerator.create_suspense_inflow(UNKNOWN_CLIENT)

        assert status == 404, response
        assert response["code"] == "QIT001019"

    def test_transfers_inflow_suspense_refuses_mixed_destination(self):
        contract_key = provision_contract()["contract_key"]

        def suspense_with(**fields) -> dict:
            payload = PayloadGenerator.create_suspense_inflow_payload()
            payload.update(fields)
            return payload

        without_destination = PayloadGenerator.create_suspense_inflow_payload()
        del without_destination["client_key"]

        malformed_payloads = [
            suspense_with(contract_key=contract_key, period_reference="2026-09", payer_party_key=CARLOS),
            suspense_with(period_reference="2026-09"),
            suspense_with(payer_party_key=CARLOS),
            without_destination,
            PayloadGenerator.create_suspense_inflow_payload(client_key="c1c1"),
        ]

        for payload in malformed_payloads:
            status, response = RequestGenerator.POST_transfers_inflow(
                payload, idempotency_key=payload["end_to_end_id"]
            )

            assert status == 400, (payload, response)
            assert response["code"] == "QIT000001"
