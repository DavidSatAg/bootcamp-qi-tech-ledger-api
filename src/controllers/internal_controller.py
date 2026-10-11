from datetime import datetime, timezone

from controllers.base_controller import BaseController
from controllers.posting_controller import PostingController
from errors import InvalidSchema, LedgerAccountNotFound
from repositories import LedgerAccountRepository


class InternalController(BaseController):
    """A transferência interna: o dinheiro entre contas do mesmo cliente, à
    escolha de quem chama (RFC :149; fatia 15a)."""

    def __init__(self) -> None:
        super().__init__(__name__)
        self.ledger_account_repository = LedgerAccountRepository(self.context)

    def create(self, payload: dict, idempotency_key: str, raw_body: bytes) -> dict:
        """Confere a chave, acha a origem, o destino e a data-valor, nesta
        ordem (RN-02)."""
        PostingController.require_idempotency_key(idempotency_key)
        self._find_account(payload["source_account_key"])
        self._find_account(payload["allocations"][0]["target_account_key"])
        self._value_date(payload)

        return dict()

    def _find_account(self, ledger_account_key: str):
        """A conta pela chave. Sem a origem não há cliente onde guardar a
        chave, e o motor recebe contas já achadas: o 018 sai antes dele e
        não grava (D-01)."""
        ledger_account = self.ledger_account_repository.get_by_key(ledger_account_key)

        if ledger_account is None:
            raise LedgerAccountNotFound(ledger_account_key)

        return ledger_account

    def _value_date(self, payload: dict) -> datetime:
        """A data-valor do corpo, ou o agora quando ela não veio.

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
