from fastapi import status as http_status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from controllers import LedgerAccountController


class LedgerAccountResource:
    """A porta de entrada HTTP das contas do ledger. Fala HTTP e só."""

    def on_get_by_key(self, ledger_account_key: str) -> JSONResponse:
        controller = LedgerAccountController()
        ledger_account = controller.get_by_key(ledger_account_key)

        return JSONResponse(
            content=jsonable_encoder(ledger_account),
            status_code=http_status.HTTP_200_OK,
        )
