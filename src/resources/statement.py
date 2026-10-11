from fastapi import status as http_status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from controllers import StatementController


class StatementResource:
    """A porta de entrada HTTP dos extratos. Fala HTTP e só."""

    def on_get_by_key(self, statement_key: str) -> JSONResponse:
        controller = StatementController()
        statement = controller.get_by_key(statement_key)

        return JSONResponse(
            content=jsonable_encoder(statement),
            status_code=http_status.HTTP_200_OK,
        )
