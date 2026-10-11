from decimal import Decimal

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
