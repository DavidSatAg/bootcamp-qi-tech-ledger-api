import requests

from connectors.rest_connector import BaseConnectorResponse, RestConnector
from constants import PROVIDER_API_INTERNAL_TOKEN, PROVIDER_API_TIMEOUT, PROVIDER_API_URL
from utils.request_context import get_request_id


class ProviderConnector(RestConnector):
    """Fala com o provedor de pagamentos: é por ele que o Pix sai (01b §7).

    Devolve a resposta como veio; se ela é aceite ou falha, quem decide é
    o controller. A falha de rede (timeout, conexão recusada) vira None:
    o `send` da base a deixa subir, e o `requests` só pode ser nomeado
    aqui, em `connectors/`. Não repete: a próxima tentativa é da outbox.
    """

    def __init__(self) -> None:
        super().__init__(
            class_name=__name__,
            base_url=PROVIDER_API_URL,
            timeout=PROVIDER_API_TIMEOUT,
            internal_token=PROVIDER_API_INTERNAL_TOKEN,
        )

    def send_pix(self, dispatch_idempotency_key: str, pix_key: str, amount_in_cents: int) -> BaseConnectorResponse | None:
        """Pede o Pix (`POST /pix`). A `dispatch_idempotency_key` faz do
        reenvio um replay do lado do provedor; o valor vai em centavos."""
        payload = {
            "dispatch_idempotency_key": dispatch_idempotency_key,
            "pix_key": pix_key,
            "amount_in_cents": amount_in_cents,
        }

        try:
            return self.send(
                endpoint="/pix",
                method="POST",
                payload=payload,
                headers={"X-Request-ID": get_request_id()},
            )
        except requests.RequestException:
            self.logger.exception(f"Provedor sem resposta para o despacho {dispatch_idempotency_key}")
            return None
