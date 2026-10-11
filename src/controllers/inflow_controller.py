from datetime import datetime, timezone

from controllers.base_controller import BaseController
from controllers.posting_controller import PostingController
from errors import ContractNotProvisioned, InvalidSchema
from models import LedgerAccountType, PurposeCode
from repositories import LedgerAccountRepository


class InflowController(BaseController):
    """A entrada por Pix: o dinheiro que chega de fora para a COLLECTION de
    um contrato (guia do Ledger §6, inflow)."""

    def __init__(self) -> None:
        super().__init__(__name__)
        self.ledger_account_repository = LedgerAccountRepository(self.context)

    def create(self, payload: dict, idempotency_key: str, raw_body: bytes) -> dict:
        """Confere a chave, acha as duas contas e a data-valor, nesta ordem
        (RN-02), e entrega as pernas ao motor."""
        PostingController.require_idempotency_key(idempotency_key)
        self._find_accounts(payload)
        self._value_date(payload)

        raise NotImplementedError("o motor de postagem chega na tarefa T2b da fatia 05a")

    def _find_accounts(self, payload: dict) -> tuple:
        """A COLLECTION do contrato e o `external/CASH` do mesmo cliente.

        Sem COLLECTION não há cliente, e sem cliente não há onde guardar a
        chave de idempotência: o 035 sai antes do motor e não grava nada.
        O `external` existe sempre que há contrato (provisionamento, S04 RN-07).
        """
        collection = self.ledger_account_repository.find_contract_account(
            payload["contract_key"], PurposeCode.COLLECTION
        )

        if collection is None:
            raise ContractNotProvisioned(payload["contract_key"])

        external = self.ledger_account_repository.find_by_natural_key(
            collection.client_key, LedgerAccountType.EXTERNAL, PurposeCode.CASH, "", ""
        )

        return collection, external

    def _value_date(self, payload: dict) -> datetime:
        """A data-valor do corpo, ou o agora quando ela não veio (CU-J10).

        O `pattern` do schema conta dígitos, não dias: "2026-02-30" passa por
        ele e morre aqui, como pedido malformado (400).
        """
        value_date = payload.get("value_date")

        if value_date is None:
            return datetime.now(timezone.utc)

        try:
            return datetime.fromisoformat(value_date)
        except ValueError:
            raise InvalidSchema(f"value_date {value_date} is not a real date")
