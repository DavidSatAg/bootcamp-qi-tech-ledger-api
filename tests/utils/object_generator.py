from uuid import uuid4

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

    @staticmethod
    def create_split(contract_key: str, idempotency_key: str = None, **kwargs) -> tuple:
        """A divisão da competência no contrato, com uma `Idempotency-Key`
        nova quando nenhuma vem.

        Devolve (status, corpo, payload) sem conferir o status.
        """
        if idempotency_key is None:
            idempotency_key = str(uuid4())

        split_payload = PayloadGenerator.create_split_payload(contract_key, **kwargs)
        status, response = RequestGenerator.POST_transfers_split(split_payload, idempotency_key=idempotency_key)

        return status, response, split_payload

    @staticmethod
    def create_statement(ledger_account_key: str, **kwargs) -> tuple:
        """Emite o extrato da conta com uma `Idempotency-Key` nova.

        Devolve (status, corpo, payload) sem conferir o status.
        """
        statement_payload = PayloadGenerator.create_statement_payload(ledger_account_key, **kwargs)
        status, response = RequestGenerator.POST_statement(statement_payload, idempotency_key=str(uuid4()))

        return status, response, statement_payload

    @staticmethod
    def create_payout(source_account_key: str, idempotency_key: str = None, **kwargs) -> tuple:
        """Um repasse da conta, com uma `Idempotency-Key` nova quando
        nenhuma vem.

        Devolve (status, corpo, payload) sem conferir o status.
        """
        if idempotency_key is None:
            idempotency_key = str(uuid4())

        payout_payload = PayloadGenerator.create_payout_payload(source_account_key, **kwargs)
        status, response = RequestGenerator.POST_transfers_payout(payout_payload, idempotency_key=idempotency_key)

        return status, response, payout_payload

    @staticmethod
    def create_divided_contract(rent_beneficiary_party_key: str = "22222222-2222-4222-8222-222222222222") -> dict:
        """O caso do remodelagem/05 até a divisão: provisiona com o dono da
        RENT trocado, recebe a TX1 e divide a competência (TX2), deixando
        450000 na RENT. Devolve o corpo do provisionamento."""
        contract_ledger_payload = PayloadGenerator.create_contract_ledger_payload()
        for item in contract_ledger_payload["items"]:
            if item["purpose_code"] == "RENT":
                item["beneficiary_party_key"] = rent_beneficiary_party_key

        status, contract_ledger = RequestGenerator.POST_contract_ledgers(contract_ledger_payload)
        assert status == 201, contract_ledger
        contract_key = contract_ledger["contract_key"]

        status, response, _payload = ObjectGenerator.create_inflow(contract_key, value_date="2026-09-05T14:22:00Z")
        assert status == 201, response

        status, response, _payload = ObjectGenerator.create_split(contract_key, value_date="2026-09-05T14:23:00Z")
        assert status == 201, response

        return contract_ledger

    @staticmethod
    def get_client_account_key(client_key: str, purpose_code: str) -> str:
        """A chave da primeira conta do cliente com esse propósito, pela
        listagem (a `clearing/TRANSIT`, na prática: uma por cliente)."""
        status, response = RequestGenerator.GET_ledger_accounts({"client_key": client_key, "limit": "100"})
        assert status == 200, response

        for ledger_account in response["data"]:
            if ledger_account["purpose_code"] == purpose_code:
                return ledger_account["ledger_account_key"]

        raise AssertionError(f"o cliente {client_key} não tem conta {purpose_code} na primeira página")

    @staticmethod
    def create_internal(
        source_account_key: str, target_account_key: str, idempotency_key: str = None, **kwargs
    ) -> tuple:
        """Uma transferência interna, com uma `Idempotency-Key` nova quando
        nenhuma vem.

        Devolve (status, corpo, payload) sem conferir o status.
        """
        if idempotency_key is None:
            idempotency_key = str(uuid4())

        internal_payload = PayloadGenerator.create_internal_payload(source_account_key, target_account_key, **kwargs)
        status, response = RequestGenerator.POST_transfers_internal(internal_payload, idempotency_key=idempotency_key)

        return status, response, internal_payload
