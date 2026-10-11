from controllers.base_controller import BaseController
from dtos import TraceDTO
from errors import LedgerTransactionNotFound
from repositories import LedgerEntryRepository, LedgerTransactionRepository


class TraceController(BaseController):
    """O rastreio de uma transação. Só lê: nenhum commit, nenhuma trava."""

    def __init__(self) -> None:
        super().__init__(__name__)
        self.ledger_transaction_repository = LedgerTransactionRepository(self.context)
        self.ledger_entry_repository = LedgerEntryRepository(self.context)

    def get_trace(self, ledger_transaction_key: str) -> dict:
        self.logger.debug(f"Rastreando a transação de chave {ledger_transaction_key}")

        ledger_transaction = self.ledger_transaction_repository.get_by_key(ledger_transaction_key)

        if ledger_transaction is None:
            raise LedgerTransactionNotFound(ledger_transaction_key)

        # O estorno aponta para a original pelo `id`; na API sai a chave.
        reverses_key = None
        if ledger_transaction.reverses_transaction_id is not None:
            reverses_key = self.ledger_transaction_repository.get_key_by_id(ledger_transaction.reverses_transaction_id)

        chain = self.ledger_transaction_repository.list_chain(
            ledger_transaction.contract_key, ledger_transaction.period_reference
        )

        # As pernas da transação pedida e as da cadeia saem de uma consulta só.
        ledger_transaction_ids = [ledger_transaction.id]
        for chain_transaction, _reverses_key, _outbox in chain:
            if chain_transaction.id not in ledger_transaction_ids:
                ledger_transaction_ids.append(chain_transaction.id)

        entries_by_transaction = {ledger_transaction_id: [] for ledger_transaction_id in ledger_transaction_ids}
        for ledger_entry, ledger_account in self.ledger_entry_repository.list_by_transactions(ledger_transaction_ids):
            entries_by_transaction[ledger_entry.ledger_transaction_id].append((ledger_entry, ledger_account))

        chain_with_entries = [
            (chain_transaction, chain_reverses_key, outbox, entries_by_transaction[chain_transaction.id])
            for chain_transaction, chain_reverses_key, outbox in chain
        ]

        return TraceDTO.obj_to_dict(
            ledger_transaction,
            reverses_key,
            entries_by_transaction[ledger_transaction.id],
            chain_with_entries,
        )
