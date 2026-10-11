from fastapi import Request
from fastapi import status as http_status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from controllers import LedgerAccountController
from utils.schema_handler import SchemaHandler

DEFAULT_LIMIT = 10
DEFAULT_PAGE = 0


class LedgerAccountResource:
    """A porta de entrada HTTP das contas do ledger. Fala HTTP e só."""

    def on_get_by_key(self, ledger_account_key: str) -> JSONResponse:
        controller = LedgerAccountController()
        ledger_account = controller.get_by_key(ledger_account_key)

        return JSONResponse(
            content=jsonable_encoder(ledger_account),
            status_code=http_status.HTTP_200_OK,
        )

    @SchemaHandler.validate_query_params("get_ledger_accounts.json")
    def on_get_list(self, request: Request) -> JSONResponse:
        """A página de contas de um cliente, de um contrato ou de um dono.

        O decorator já conferiu a query string: exatamente um dos três
        filtros, e `limit`/`page` só com dígitos.
        """
        controller = LedgerAccountController()

        query_params = request.query_params

        limit = int(query_params.get("limit", DEFAULT_LIMIT))
        page = int(query_params.get("page", DEFAULT_PAGE))

        filters = {
            "client_key": query_params.get("client_key"),
            "contract_key": query_params.get("contract_key"),
            "owner_party_key": query_params.get("owner_party_key"),
        }

        offset = page * limit
        ledger_accounts_page = controller.get_list(limit, offset, filters)

        # O envelope da página é vocabulário de HTTP: quem o monta é o
        # resource, como na listagem da base.
        page_envelope = {
            "data": ledger_accounts_page["ledger_accounts_list_dto"],
            "limit": limit,
            "page": page,
            "is_last_page": ledger_accounts_page["is_last_page"],
        }

        return JSONResponse(
            content=jsonable_encoder(page_envelope),
            status_code=http_status.HTTP_200_OK,
        )

    @SchemaHandler.validate("put_ledger_accounts_status.json")
    def on_put_status(self, ledger_account_key: str, payload: dict) -> JSONResponse:
        """Bloqueia, desbloqueia ou encerra a conta (RFC :145): devolve a
        conta como o GET dela."""
        controller = LedgerAccountController()
        ledger_account = controller.change_status(ledger_account_key, payload)

        return JSONResponse(
            content=jsonable_encoder(ledger_account),
            status_code=http_status.HTTP_200_OK,
        )
