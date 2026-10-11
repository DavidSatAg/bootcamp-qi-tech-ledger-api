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
