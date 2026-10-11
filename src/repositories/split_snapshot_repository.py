from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import aliased

from database import Context
from models import LedgerAccount, SplitSnapshot


class SplitSnapshotRepository:
    """A cópia imutável de cada versão do split. Só se acrescenta linha."""

    def __init__(self, context: Context) -> None:
        self.session = context.db_session

    def create(
        self,
        contract_key: str,
        split_version: int,
        source_ledger_account: LedgerAccount,
        ledger_account: LedgerAccount,
        allocation_type: str,
        percentage: Decimal,
        amount_in_cents: int,
        rent_amount_in_cents: int,
    ) -> SplitSnapshot:
        split_snapshot = SplitSnapshot()
        split_snapshot.contract_key = contract_key
        split_snapshot.split_version = split_version
        split_snapshot.source_ledger_account_id = source_ledger_account.id
        split_snapshot.ledger_account_id = ledger_account.id
        split_snapshot.allocation_type = allocation_type
        split_snapshot.percentage = percentage
        split_snapshot.amount_in_cents = amount_in_cents
        split_snapshot.rent_amount_in_cents = rent_amount_in_cents

        self.session.add(split_snapshot)
        return split_snapshot

    def get_max_version(self, contract_key: str) -> int:
        """A maior versão gravada do contrato; 0 se ele nunca foi provisionado."""
        max_version = (
            self.session.query(func.max(SplitSnapshot.split_version))
            .filter(SplitSnapshot.contract_key == contract_key)
            .scalar()
        )

        if max_version is None:
            return 0

        return max_version

    def list_by_version(self, contract_key: str, split_version: int) -> list:
        """As linhas de uma versão, cada uma com a conta de origem e a de destino.

        Devolve tuplas (split_snapshot, conta de origem, conta de destino):
        a linha só guarda os `id`s, e quem compara conteúdo precisa do
        propósito e do dono de cada conta.
        """
        source_ledger_account = aliased(LedgerAccount)
        target_ledger_account = aliased(LedgerAccount)

        return (
            self.session.query(SplitSnapshot, source_ledger_account, target_ledger_account)
            .join(source_ledger_account, SplitSnapshot.source_ledger_account_id == source_ledger_account.id)
            .join(target_ledger_account, SplitSnapshot.ledger_account_id == target_ledger_account.id)
            .filter(
                SplitSnapshot.contract_key == contract_key,
                SplitSnapshot.split_version == split_version,
            )
            .order_by(SplitSnapshot.id)
            .all()
        )
