from fastapi import status as http_status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from controllers import OutboxController
from utils.schema_handler import SchemaHandler

DEFAULT_LIMIT = 10


class OutboxResource:
    """A porta de entrada HTTP da fila da outbox. Fala HTTP e só."""

    @SchemaHandler.validate("post_outbox_dispatch.json")
    def on_post_dispatch(self, payload: dict) -> JSONResponse:
        """Uma varredura da fila (RFC :155): uma tentativa por linha
        `pending`, até `limit`; devolve os desfechos desta chamada."""
        controller = OutboxController()
        outcomes = controller.dispatch_pending(payload.get("limit", DEFAULT_LIMIT))

        return JSONResponse(
            content=jsonable_encoder(outcomes),
            status_code=http_status.HTTP_200_OK,
        )
