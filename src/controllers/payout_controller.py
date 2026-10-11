from controllers.base_controller import BaseController
from controllers.posting_controller import PostingController
from errors import LedgerAccountNotFound
from repositories import LedgerAccountRepository


class PayoutController(BaseController):
    """O repasse por Pix: o dinheiro de uma conta com dono vai para a
    `clearing/TRANSIT` do cliente, e a outbox o despacha ao provedor
    (guia do Ledger §6, payout; D0006)."""

    def __init__(self) -> None:
        super().__init__(__name__)
        self.ledger_account_repository = LedgerAccountRepository(self.context)

    def create(self, payload: dict, idempotency_key: str, raw_body: bytes) -> dict:
        """Confere a chave, acha a origem e fecha a leitura (RN-01)."""
        PostingController.require_idempotency_key(idempotency_key)
        self._find_source(payload)

        # Fecha a leitura antes do Cadastro, sem escrita (D2).
        self.session.commit()

        return dict()

    def _find_source(self, payload: dict):
        """A conta de origem. Sem ela não há cliente, e sem cliente não há
        onde guardar a chave: o 018 sai antes do motor e não grava (D-01)."""
        source = self.ledger_account_repository.get_by_key(payload["source_account_key"])

        if source is None:
            raise LedgerAccountNotFound(payload["source_account_key"])

        return source
