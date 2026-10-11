from controllers.base_controller import BaseController
from errors import LedgerTransactionNotFound
from repositories import LedgerTransactionRepository


class TraceController(BaseController):
    """O rastreio de uma transação. Só lê: nenhum commit, nenhuma trava."""

    def __init__(self) -> None:
        super().__init__(__name__)
        self.ledger_transaction_repository = LedgerTransactionRepository(self.context)

    def get_trace(self, ledger_transaction_key: str) -> dict:
        self.logger.debug(f"Rastreando a transação de chave {ledger_transaction_key}")

        ledger_transaction = self.ledger_transaction_repository.get_by_key(ledger_transaction_key)

        if ledger_transaction is None:
            raise LedgerTransactionNotFound(ledger_transaction_key)

        return {"transaction": {}, "entries": [], "chain": []}
