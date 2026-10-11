from datetime import timezone

from models import LedgerTransaction


def utc_with_z(value) -> str:
    """O instante em UTC, com `Z` no lugar de `+00:00` (01b :50)."""
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class LedgerTransactionDTO:
    """Traduz a transação do ledger no JSON que a API devolve."""

    @staticmethod
    def obj_to_dict(ledger_transaction: LedgerTransaction) -> dict:
        dto = dict()
        dto["ledger_transaction_key"] = ledger_transaction.ledger_transaction_key
        dto["ledger_transaction_type"] = ledger_transaction.ledger_transaction_type.enumerator
        dto["contract_key"] = ledger_transaction.contract_key
        dto["period_reference"] = ledger_transaction.period_reference
        dto["payer_party_key"] = ledger_transaction.payer_party_key
        dto["end_to_end_id"] = ledger_transaction.end_to_end_id
        dto["value_date"] = utc_with_z(ledger_transaction.value_date)

        return dto
