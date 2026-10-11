from uuid import uuid4

from database import Context
from models import LedgerTransaction, LedgerTransactionType


class LedgerTransactionRepository:
    """As transações do ledger: o cabeçalho de cada movimento."""

    def __init__(self, context: Context) -> None:
        self.session = context.db_session

    def create(self, transaction: dict, trace_id: str) -> LedgerTransaction:
        """Grava o cabeçalho com uma chave nova. `transaction` traz as colunas
        que a rota preenche, com o tipo como enumerador.

        O `flush` manda o INSERT agora: o `id` passa a existir para as
        pernas, e a UNIQUE do `end_to_end_id` dispara aqui, não no commit.
        """
        ledger_transaction = LedgerTransaction()
        ledger_transaction.ledger_transaction_key = str(uuid4())
        ledger_transaction.ledger_transaction_type = self.get_type(transaction["ledger_transaction_type"])
        ledger_transaction.contract_key = transaction.get("contract_key", "")
        ledger_transaction.period_reference = transaction.get("period_reference", "")
        ledger_transaction.split_version = transaction.get("split_version")
        ledger_transaction.payer_party_key = transaction.get("payer_party_key", "")
        ledger_transaction.end_to_end_id = transaction.get("end_to_end_id")
        ledger_transaction.value_date = transaction["value_date"]
        ledger_transaction.actor = transaction["actor"]
        ledger_transaction.reason = transaction.get("reason")
        ledger_transaction.trace_id = trace_id

        self.session.add(ledger_transaction)
        self.session.flush()

        return ledger_transaction

    def get_by_key(self, ledger_transaction_key: str) -> LedgerTransaction:
        return (
            self.session.query(LedgerTransaction)
            .filter(LedgerTransaction.ledger_transaction_key == ledger_transaction_key)
            .first()
        )

    def get_type(self, enumerator: str) -> LedgerTransactionType:
        return self.session.query(LedgerTransactionType).filter(LedgerTransactionType.enumerator == enumerator).one()
