from controllers.base_controller import BaseController
from controllers.posting_controller import PostingController
from errors import LedgerTransactionNotFound
from repositories import LedgerTransactionRepository


class ReversalController(BaseController):
    """O estorno: a transação original de novo, com as pernas invertidas
    (guia do Ledger §6, reversal; D0005)."""

    def __init__(self) -> None:
        super().__init__(__name__)
        self.ledger_transaction_repository = LedgerTransactionRepository(self.context)

    def create(self, ledger_transaction_key: str, payload: dict, idempotency_key: str, raw_body: bytes) -> dict:
        """Confere a chave e acha a original, nesta ordem (RN-01). Sem a
        original não há livro que escope o registro: o 020 sai antes do
        motor e nada se grava (D-01)."""
        PostingController.require_idempotency_key(idempotency_key)
        original = self.ledger_transaction_repository.get_by_key(ledger_transaction_key)

        if original is None:
            raise LedgerTransactionNotFound()

        return {}
