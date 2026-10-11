from os import environ

from tests.utils.requisition import ClientRequisition, BaseConnectorResponse


INTERNAL_TOKEN = environ.get("INTERNAL_TOKEN", "default_token")


class RequestGenerator:
    @staticmethod
    def POST_sample_entity(sample_entity_payload: dict) -> BaseConnectorResponse:
        response = ClientRequisition.send(
            "POST",
            "/sample_entity",
            payload=sample_entity_payload,
            headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
        )

        return response.response_status, response.response_json

    @staticmethod
    def GET_sample_entity(sample_entity_key: str) -> BaseConnectorResponse:
        response = ClientRequisition.send(
            "GET",
            f"/sample_entity/{sample_entity_key}",
            headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
        )
        return response.response_status, response.response_json

    @staticmethod
    def PUT_sample_entity(sample_entity_key: str, update_payload: dict) -> BaseConnectorResponse:
        response = ClientRequisition.send(
            "PUT",
            f"/sample_entity/{sample_entity_key}",
            payload=update_payload,
            headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
        )
        return response.response_status, response.response_json

    @staticmethod
    def PUT_webhook_sample_entity(sample_entity_key: str) -> BaseConnectorResponse:
        response = ClientRequisition.send(
            "PUT",
            f"/webhook/sample_entity/{sample_entity_key}/increment_counter",
            headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
        )
        return response.response_status, response.response_json

    @staticmethod
    def GET_sample_entities(params: dict = None) -> BaseConnectorResponse:
        response = ClientRequisition.send(
            "GET", "/sample_entities", headers={"INTERNAL-TOKEN": INTERNAL_TOKEN}, query_params=params
        )
        return response.response_status, response.response_json

    @staticmethod
    def GET_ledger_account(ledger_account_key: str) -> BaseConnectorResponse:
        response = ClientRequisition.send(
            "GET",
            f"/ledger_accounts/{ledger_account_key}",
            headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
        )

        return response.response_status, response.response_json

    @staticmethod
    def POST_contract_ledgers(contract_ledger_payload: dict) -> BaseConnectorResponse:
        response = ClientRequisition.send(
            "POST",
            "/contract_ledgers",
            payload=contract_ledger_payload,
            headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
        )

        return response.response_status, response.response_json

    @staticmethod
    def GET_ledger_accounts(params: dict = None) -> BaseConnectorResponse:
        response = ClientRequisition.send(
            "GET", "/ledger_accounts", headers={"INTERNAL-TOKEN": INTERNAL_TOKEN}, query_params=params
        )

        return response.response_status, response.response_json

    @staticmethod
    def POST_transfers_inflow(payload: dict = None, idempotency_key: str = None, raw_body: bytes = None) -> BaseConnectorResponse:
        """A entrada por Pix. A `Idempotency-Key` só vai quando há chave.

        `raw_body` manda os bytes exatos, no lugar do `payload`: é assim que
        um teste prova que um espaço a mais já é outro pedido. Vai com o
        `Content-Type` de JSON, que o `json=` põe sozinho e o `data=` não.
        """
        headers = {"INTERNAL-TOKEN": INTERNAL_TOKEN}

        if idempotency_key is not None:
            headers["Idempotency-Key"] = idempotency_key

        if raw_body is not None:
            headers["Content-Type"] = "application/json"

        response = ClientRequisition.send(
            "POST",
            "/transfers/inflow",
            payload=payload,
            headers=headers,
            data=raw_body,
        )

        return response.response_status, response.response_json

    @staticmethod
    def GET_transfer_trace(ledger_transaction_key: str) -> BaseConnectorResponse:
        response = ClientRequisition.send(
            "GET",
            f"/transfers/{ledger_transaction_key}/trace",
            headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
        )

        return response.response_status, response.response_json
