import json
from os import environ

import requests

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

    @staticmethod
    def GET_integrity(params: dict = None) -> BaseConnectorResponse:
        response = ClientRequisition.send(
            "GET", "/integrity", headers={"INTERNAL-TOKEN": INTERNAL_TOKEN}, query_params=params
        )

        return response.response_status, response.response_json

    @staticmethod
    def POST_contract_ledgers_closure(contract_key: str, closure_payload: dict) -> BaseConnectorResponse:
        response = ClientRequisition.send(
            "POST",
            f"/contract_ledgers/{contract_key}/closure",
            payload=closure_payload,
            headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
        )

        return response.response_status, response.response_json

    @staticmethod
    def POST_transfers_split(payload: dict = None, idempotency_key: str = None) -> BaseConnectorResponse:
        """A divisão da competência. A `Idempotency-Key` só vai quando há chave."""
        headers = {"INTERNAL-TOKEN": INTERNAL_TOKEN}

        if idempotency_key is not None:
            headers["Idempotency-Key"] = idempotency_key

        response = ClientRequisition.send(
            "POST",
            "/transfers/split",
            payload=payload,
            headers=headers,
        )

        return response.response_status, response.response_json

    @staticmethod
    def GET_statement(statement_key: str) -> BaseConnectorResponse:
        response = ClientRequisition.send(
            "GET",
            f"/statement/{statement_key}",
            headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
        )

        return response.response_status, response.response_json

    @staticmethod
    def POST_statement(payload: dict, idempotency_key: str = None) -> BaseConnectorResponse:
        """A emissão do extrato. A `Idempotency-Key` só vai quando há chave."""
        headers = {"INTERNAL-TOKEN": INTERNAL_TOKEN}

        if idempotency_key is not None:
            headers["Idempotency-Key"] = idempotency_key

        response = ClientRequisition.send("POST", "/statement", payload=payload, headers=headers)

        return response.response_status, response.response_json

    @staticmethod
    def POST_statement_verify(payload: dict) -> BaseConnectorResponse:
        """A verificação do hash: rota pública, vai SEM o `INTERNAL-TOKEN`."""
        response = ClientRequisition.send("POST", "/statement/verify", payload=payload, headers={})

        return response.response_status, response.response_json

    @staticmethod
    def POST_transfers_payout(payload: dict = None, idempotency_key: str = None) -> BaseConnectorResponse:
        """O repasse. A `Idempotency-Key` só vai quando há chave."""
        headers = {"INTERNAL-TOKEN": INTERNAL_TOKEN}

        if idempotency_key is not None:
            headers["Idempotency-Key"] = idempotency_key

        response = ClientRequisition.send(
            "POST",
            "/transfers/payout",
            payload=payload,
            headers=headers,
        )

        return response.response_status, response.response_json

    @staticmethod
    def POST_transfers_internal(payload: dict = None, idempotency_key: str = None) -> BaseConnectorResponse:
        """A transferência interna. A `Idempotency-Key` só vai quando há chave."""
        headers = {"INTERNAL-TOKEN": INTERNAL_TOKEN}

        if idempotency_key is not None:
            headers["Idempotency-Key"] = idempotency_key

        response = ClientRequisition.send(
            "POST",
            "/transfers/internal",
            payload=payload,
            headers=headers,
        )

        return response.response_status, response.response_json

    @staticmethod
    def GET_mock_requests(mock: str, url_path: str) -> list:
        """O diário do mock (`party-mock` ou `provider-mock`), só das
        chamadas a `url_path`: [(headers, corpo)], do mais novo ao mais velho.

        Vai direto ao `/__admin/requests` do WireMock: o `ClientRequisition`
        só monta a URL da API. Os nomes dos cabeçalhos saem em minúsculas, e
        o corpo, lido como JSON (vazio vira None).
        """
        ports = {
            "party-mock": environ.get("PARTY_MOCK_PORT", "8091"),
            "provider-mock": environ.get("PROVIDER_MOCK_PORT", "8082"),
        }
        api_host = environ.get("SERVER_LOCALHOST", "0.0.0.0")
        response = requests.get(f"http://{api_host}:{ports[mock]}/__admin/requests", timeout=5)
        assert response.status_code == 200, response.text

        logged_requests = []
        for logged in response.json()["requests"]:
            request = logged["request"]
            if request["url"].split("?")[0] != url_path:
                continue
            headers = {name.lower(): value for name, value in request["headers"].items()}
            body = None
            if request.get("body"):
                body = json.loads(request["body"])
            logged_requests.append((headers, body))

        return logged_requests

    @staticmethod
    def POST_webhooks_provider(payload: dict = None, raw_body: bytes = None) -> BaseConnectorResponse:
        """O aviso do provedor. Sem `Idempotency-Key`: a chave é o
        `provider_reference` (RFC :154). `raw_body` manda os bytes exatos,
        como no `POST_transfers_inflow`; o 204 volta com `json` None."""
        headers = {"INTERNAL-TOKEN": INTERNAL_TOKEN}

        if raw_body is not None:
            headers["Content-Type"] = "application/json"

        response = ClientRequisition.send(
            "POST",
            "/webhooks/provider",
            payload=payload,
            headers=headers,
            data=raw_body,
        )

        return response.response_status, response.response_json

    @staticmethod
    def POST_transfers_reversal(
        ledger_transaction_key: str, payload: dict = None, idempotency_key: str = None
    ) -> BaseConnectorResponse:
        """O estorno da transação. A `Idempotency-Key` só vai quando há chave."""
        headers = {"INTERNAL-TOKEN": INTERNAL_TOKEN}

        if idempotency_key is not None:
            headers["Idempotency-Key"] = idempotency_key

        response = ClientRequisition.send(
            "POST",
            f"/transfers/{ledger_transaction_key}/reversal",
            payload=payload,
            headers=headers,
        )

        return response.response_status, response.response_json
