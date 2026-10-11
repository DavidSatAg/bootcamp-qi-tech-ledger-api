from fastapi import Depends, Header
from fastapi import status as http_status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from controllers import StatementController
from utils.raw_body import read_raw_body
from utils.schema_handler import SchemaHandler


class StatementResource:
    """A porta de entrada HTTP dos extratos. Fala HTTP e só."""

    @SchemaHandler.validate("post_statement.json")
    def on_post(
        self,
        payload: dict,
        raw_body: bytes = Depends(read_raw_body),
        idempotency_key: str | None = Header(default=None),
    ) -> JSONResponse:
        """Emite o extrato do período. `raw_body` são os bytes do corpo, de
        onde sai a impressão digital da `Idempotency-Key`."""
        controller = StatementController()
        statement = controller.issue(payload, idempotency_key, raw_body)

        return JSONResponse(
            content=jsonable_encoder(statement),
            status_code=http_status.HTTP_201_CREATED,
        )

    def on_get_by_key(self, statement_key: str) -> JSONResponse:
        controller = StatementController()
        statement = controller.get_by_key(statement_key)

        return JSONResponse(
            content=jsonable_encoder(statement),
            status_code=http_status.HTTP_200_OK,
        )
