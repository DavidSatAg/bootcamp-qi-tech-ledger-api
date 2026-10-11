from fastapi import Request
from fastapi import status as http_status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from controllers import IntegrityController


class IntegrityResource:
    """A porta de entrada HTTP da conferência de integridade. Fala HTTP e só."""

    def on_get(self, request: Request) -> JSONResponse:
        """O balanço geral, ou o de um livro com `?client_key=`.

        Sem schema: a RFC só lista o 200. Parâmetro desconhecido é
        ignorado, e livro desconhecido sai com zeros.
        """
        controller = IntegrityController()
        integrity = controller.get_integrity(request.query_params.get("client_key"))

        return JSONResponse(
            content=jsonable_encoder(integrity),
            status_code=http_status.HTTP_200_OK,
        )
