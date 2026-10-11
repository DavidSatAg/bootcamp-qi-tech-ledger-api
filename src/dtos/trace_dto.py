from dtos.ledger_account_dto import empty_as_null
from dtos.ledger_transaction_dto import utc_with_z
from models import LedgerAccount, LedgerEntry, LedgerTransaction, Outbox


class TraceDTO:
    """Traduz o rastreio de uma transação no JSON que a API devolve:
    a transação, as pernas dela e a cadeia do contrato na competência."""

    @staticmethod
    def obj_to_dict(ledger_transaction: LedgerTransaction, reverses_key: str | None, entries: list, chain: list) -> dict:
        """`entries` = [(LedgerEntry, LedgerAccount)] da transação pedida;
        `chain` = [(LedgerTransaction, chave da estornada, Outbox ou None,
        [(LedgerEntry, LedgerAccount)])], na ordem da cadeia."""
        dto = dict()
        dto["transaction"] = TraceDTO.transaction_to_dict(ledger_transaction, reverses_key)
        dto["entries"] = TraceDTO.entries_to_list_dict(entries)
        dto["chain"] = [TraceDTO.link_to_dict(*link) for link in chain]

        return dto

    @staticmethod
    def link_to_dict(ledger_transaction: LedgerTransaction, reverses_key: str | None, outbox: Outbox | None, entries: list) -> dict:
        """Um elo da cadeia: a transação, o repasse dela, se houver, e as pernas."""
        dto = dict()
        dto["ledger_transaction_key"] = ledger_transaction.ledger_transaction_key
        dto["ledger_transaction_type"] = ledger_transaction.ledger_transaction_type.enumerator
        dto["value_date"] = utc_with_z(ledger_transaction.value_date)
        dto["payer_party_key"] = empty_as_null(ledger_transaction.payer_party_key)
        dto["reverses_transaction_key"] = reverses_key
        dto["outbox_key"] = None
        dto["outbox_status"] = None
        if outbox is not None:
            dto["outbox_key"] = outbox.outbox_key
            dto["outbox_status"] = outbox.outbox_status.enumerator
        dto["entries"] = TraceDTO.entries_to_list_dict(entries)

        return dto

    @staticmethod
    def transaction_to_dict(ledger_transaction: LedgerTransaction, reverses_key: str | None) -> dict:
        dto = dict()
        dto["ledger_transaction_key"] = ledger_transaction.ledger_transaction_key
        dto["ledger_transaction_type"] = ledger_transaction.ledger_transaction_type.enumerator
        dto["value_date"] = utc_with_z(ledger_transaction.value_date)
        dto["contract_key"] = empty_as_null(ledger_transaction.contract_key)
        dto["period_reference"] = empty_as_null(ledger_transaction.period_reference)
        dto["split_version"] = ledger_transaction.split_version
        dto["payer_party_key"] = empty_as_null(ledger_transaction.payer_party_key)
        dto["end_to_end_id"] = ledger_transaction.end_to_end_id
        dto["reverses_transaction_key"] = reverses_key
        dto["actor"] = ledger_transaction.actor
        dto["reason"] = ledger_transaction.reason
        dto["trace_id"] = ledger_transaction.trace_id

        return dto

    @staticmethod
    def entry_to_dict(ledger_entry: LedgerEntry, ledger_account: LedgerAccount) -> dict:
        """O valor sai inteiro: `Numeric` volta do banco como `Decimal`."""
        dto = dict()
        dto["direction"] = ledger_entry.direction
        dto["amount_in_cents"] = int(ledger_entry.amount_in_cents)
        dto["ledger_account_key"] = ledger_account.ledger_account_key
        dto["ledger_account_type"] = ledger_account.ledger_account_type.enumerator
        dto["purpose_code"] = ledger_account.purpose_code.enumerator
        dto["owner_party_key"] = empty_as_null(ledger_account.owner_party_key)
        dto["owner_role"] = empty_as_null(ledger_account.owner_role)

        return dto

    @staticmethod
    def entries_to_list_dict(entries: list) -> list:
        return [TraceDTO.entry_to_dict(ledger_entry, ledger_account) for ledger_entry, ledger_account in entries]
