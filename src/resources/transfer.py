from fastapi import Depends, Header
from fastapi import status as http_status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from controllers import InflowController
from utils.raw_body import read_raw_body
from utils.schema_handler import SchemaHandler


class TransferResource:
    """A porta de entrada HTTP das transferências que movem dinheiro."""

    @SchemaHandler.validate("post_transfers_inflow.json")
    def on_post_inflow(
        self,
        payload: dict,
        raw_body: bytes = Depends(read_raw_body),
        idempotency_key: str | None = Header(default=None),
    ) -> JSONResponse:
        """A entrada por Pix num contrato. `raw_body` são os bytes do corpo,
        de onde sai a impressão digital da `Idempotency-Key`."""
        controller = InflowController()
        ledger_transaction = controller.create(payload, idempotency_key, raw_body)

        return JSONResponse(
            content=jsonable_encoder(ledger_transaction),
            status_code=http_status.HTTP_201_CREATED,
        )
