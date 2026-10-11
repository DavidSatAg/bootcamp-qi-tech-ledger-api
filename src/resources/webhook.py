from fastapi import Depends, Response
from fastapi import status as http_status

from controllers import WebhookController
from utils.raw_body import read_raw_body
from utils.schema_handler import SchemaHandler


class WebhookResource:
    """A porta de entrada HTTP dos avisos de outros serviços."""

    @SchemaHandler.validate("post_webhooks_provider.json")
    def on_post_provider(self, payload: dict, raw_body: bytes = Depends(read_raw_body)) -> Response:
        """O aviso do provedor sobre um repasse. Sem corpo na resposta, e
        o reenvio também é 204 (RFC :154)."""
        controller = WebhookController()
        controller.handle(payload, raw_body)

        return Response(status_code=http_status.HTTP_204_NO_CONTENT)
