from uuid import uuid4

from sqlalchemy import func
from sqlalchemy.orm import aliased

from database import Context
from models import LedgerTransaction, LedgerTransactionType
from models import Outbox


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
        ledger_transaction.reverses_transaction_id = transaction.get("reverses_transaction_id")

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

    def get_key_by_id(self, ledger_transaction_id: int) -> str | None:
        """A chave da transação de `id` pedido: o `id` nunca sai da API."""
        return (
            self.session.query(LedgerTransaction.ledger_transaction_key)
            .filter(LedgerTransaction.id == ledger_transaction_id)
            .scalar()
        )

    def list_chain(self, contract_key: str, period_reference: str) -> list:
        """As transações do contrato na competência, em `value_date` e `id`:
        [(LedgerTransaction, chave da estornada ou None, Outbox ou None)].

        Transação sem contrato não tem cadeia. Supõe uma outbox por
        transação de repasse: duas linhas repetiriam a transação.
        """
        if contract_key == "":
            return []

        reversed_transaction = aliased(LedgerTransaction)

        return (
            self.session.query(LedgerTransaction, reversed_transaction.ledger_transaction_key, Outbox)
            .outerjoin(reversed_transaction, LedgerTransaction.reverses_transaction_id == reversed_transaction.id)
            .outerjoin(Outbox, Outbox.ledger_transaction_id == LedgerTransaction.id)
            .filter(
                LedgerTransaction.contract_key == contract_key,
                LedgerTransaction.period_reference == period_reference,
            )
            .order_by(LedgerTransaction.value_date, LedgerTransaction.id)
            .all()
        )

    def exists_split(self, contract_key: str, period_reference: str) -> bool:
        """Se já há `split` do contrato na competência. Sem trava: quem
        pergunta já segura a da COLLECTION (passo 5 do motor)."""
        query = (
            self.session.query(LedgerTransaction.id)
            .join(LedgerTransaction.ledger_transaction_type)
            .filter(
                LedgerTransaction.contract_key == contract_key,
                LedgerTransaction.period_reference == period_reference,
                LedgerTransactionType.enumerator == LedgerTransactionType.SPLIT,
            )
        )

        return self.session.query(query.exists()).scalar()

    def lock_for_update(self, ledger_transaction_id: int, lock_timeout: str) -> None:
        """Trava a linha da transação, esperando no máximo `lock_timeout`
        (a original do estorno, fatia 11 RN-05; G :460; D0005 :46-50).

        Como no `LedgerAccountRepository.lock_for_update`: o `set_config(...,
        true)` é o `SET LOCAL`, e estourar o tempo sobe como está (`55P03`):
        quem o traduz é o controller. A trava solta no commit ou no rollback.
        """
        self.session.query(func.set_config("lock_timeout", lock_timeout, True)).scalar()

        (
            self.session.query(LedgerTransaction.id)
            .filter(LedgerTransaction.id == ledger_transaction_id)
            .with_for_update()
            .one()
        )

    def get_by_end_to_end_id(self, end_to_end_id: str) -> LedgerTransaction | None:
        """A transação do `end_to_end_id` (a entrada Pix; UNIQUE): a que o
        MED devolve (fatia 11 RN-09)."""
        return self.session.query(LedgerTransaction).filter(LedgerTransaction.end_to_end_id == end_to_end_id).first()

    def list_page(self, limit: int, offset: int, filters: dict) -> list:
        """A página de transações do pagador, ou do contrato na competência
        (o schema garante um filtro só), por `id`, como a das contas: pede
        um a mais que o limite para saber se há próxima. Sem trava."""
        query = self.session.query(LedgerTransaction)

        payer_party_key = filters.get("payer_party_key")
        if payer_party_key is not None:
            query = query.filter(LedgerTransaction.payer_party_key == payer_party_key)

        contract_key = filters.get("contract_key")
        if contract_key is not None:
            query = query.filter(LedgerTransaction.contract_key == contract_key)

        period_reference = filters.get("period_reference")
        if period_reference is not None:
            query = query.filter(LedgerTransaction.period_reference == period_reference)

        query = query.order_by(LedgerTransaction.id)

        return query.limit(limit + 1).offset(offset).all()
