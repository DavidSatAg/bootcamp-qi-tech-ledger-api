from tests.utils.requisition import BaseConnectorResponse
from tests.utils.payload_generator import PayloadGenerator
from tests.utils.request_generator import RequestGenerator


class ObjectGenerator:
    @staticmethod
    def create_sample_entity(hello: str = None) -> BaseConnectorResponse:

        sample_entity_payload = PayloadGenerator.create_sample_entity_payload(hello=hello)

        status, response = RequestGenerator.POST_sample_entity(sample_entity_payload)
        assert status == 201

        return response

    @staticmethod
    def update_sample_entity(sample_entity_key, new_status: str = None) -> BaseConnectorResponse:

        sample_entity_payload = PayloadGenerator.create_new_status_payload(new_status)

        status, response = RequestGenerator.PUT_sample_entity(sample_entity_key, sample_entity_payload)
        assert status == 202

        return response

    @staticmethod
    def create_contract_ledger(**kwargs) -> tuple:
        """Provisiona um contrato no ledger: o cenário de toda fatia de dinheiro.

        Devolve (status, corpo) sem conferir o status: quem chama decide
        se esperava 201, 200 ou uma recusa.
        """
        contract_ledger_payload = PayloadGenerator.create_contract_ledger_payload(**kwargs)
        return RequestGenerator.POST_contract_ledgers(contract_ledger_payload)

    @staticmethod
    def create_inflow(contract_key: str, **kwargs) -> tuple:
        """Uma entrada por Pix no contrato, com a `Idempotency-Key` igual ao
        `end_to_end_id`, como o ERP manda (01b §0.5).

        Devolve (status, corpo, payload) sem conferir o status.
        """
        inflow_payload = PayloadGenerator.create_inflow_payload(contract_key, **kwargs)
        status, response = RequestGenerator.POST_transfers_inflow(
            inflow_payload, idempotency_key=inflow_payload["end_to_end_id"]
        )

        return status, response, inflow_payload

    @staticmethod
    def close_contract_ledger(contract_key: str, **kwargs) -> tuple:
        """Encerra o contrato no ledger. Devolve (status, corpo) sem
        conferir o status."""
        closure_payload = PayloadGenerator.create_closure_payload(**kwargs)
        return RequestGenerator.POST_contract_ledgers_closure(contract_key, closure_payload)
