from fastapi import Depends, Header
from fastapi import status as http_status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from controllers import InflowController
from controllers import TraceController
from controllers import SplitController
from controllers import PayoutController
from controllers import InternalController
from controllers import ReversalController
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

    def on_get_trace(self, ledger_transaction_key: str) -> JSONResponse:
        """A transação, as pernas dela e a cadeia do contrato na competência."""
        controller = TraceController()
        trace = controller.get_trace(ledger_transaction_key)

        return JSONResponse(
            content=jsonable_encoder(trace),
            status_code=http_status.HTTP_200_OK,
        )

    @SchemaHandler.validate("post_transfers_split.json")
    def on_post_split(
        self,
        payload: dict,
        raw_body: bytes = Depends(read_raw_body),
        idempotency_key: str | None = Header(default=None),
    ) -> JSONResponse:
        """A divisão de uma competência do contrato pela cópia do split."""
        controller = SplitController()
        ledger_transaction = controller.create(payload, idempotency_key, raw_body)

        return JSONResponse(
            content=jsonable_encoder(ledger_transaction),
            status_code=http_status.HTTP_201_CREATED,
        )

    @SchemaHandler.validate("post_transfers_payout.json")
    def on_post_payout(
        self,
        payload: dict,
        raw_body: bytes = Depends(read_raw_body),
        idempotency_key: str | None = Header(default=None),
    ) -> JSONResponse:
        """O repasse por Pix: aceito, e despachado ao provedor depois do
        commit; por isso 202, e não 201 (RFC :150)."""
        controller = PayoutController()
        payout = controller.create(payload, idempotency_key, raw_body)

        return JSONResponse(
            content=jsonable_encoder(payout),
            status_code=http_status.HTTP_202_ACCEPTED,
        )

    @SchemaHandler.validate("post_transfers_internal.json")
    def on_post_internal(
        self,
        payload: dict,
        raw_body: bytes = Depends(read_raw_body),
        idempotency_key: str | None = Header(default=None),
    ) -> JSONResponse:
        """A transferência interna entre contas do mesmo cliente."""
        controller = InternalController()
        ledger_transaction = controller.create(payload, idempotency_key, raw_body)

        return JSONResponse(
            content=jsonable_encoder(ledger_transaction),
            status_code=http_status.HTTP_201_CREATED,
        )

    @SchemaHandler.validate("post_transfers_reversal.json")
    def on_post_reversal(
        self,
        ledger_transaction_key: str,
        payload: dict,
        raw_body: bytes = Depends(read_raw_body),
        idempotency_key: str | None = Header(default=None),
    ) -> JSONResponse:
        """O estorno da transação pela chave dela (RFC :151)."""
        controller = ReversalController()
        ledger_transaction = controller.create(ledger_transaction_key, payload, idempotency_key, raw_body)

        return JSONResponse(
            content=jsonable_encoder(ledger_transaction),
            status_code=http_status.HTTP_201_CREATED,
        )
