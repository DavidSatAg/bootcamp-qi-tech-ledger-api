from dtos.ledger_account_dto import empty_as_null
from dtos.ledger_transaction_dto import utc_with_z
from models import Statement


class StatementDTO:
    """Traduz o extrato no JSON que a API devolve."""

    @staticmethod
    def obj_to_dict(
        statement: Statement,
        content_hash_matches: bool,
        lines: list,
        balances: dict,
        previous_statement_key: str | None,
        supersedes_statement_key: str | None,
        superseded_by_statement_key: str | None,
    ) -> dict:
        """`lines` = [(LedgerEntry, LedgerTransaction)]; `balances` = os
        quatro saldos da RN-09, em centavos."""
        dto = dict()
        dto["statement_key"] = statement.statement_key
        dto["ledger_account_key"] = statement.ledger_account.ledger_account_key
        dto["period_start"] = utc_with_z(statement.period_start)
        dto["period_end"] = utc_with_z(statement.period_end)
        dto["created_at"] = utc_with_z(statement.created_at)
        dto["content_hash"] = statement.content_hash
        dto["content_hash_matches"] = content_hash_matches
        dto["previous_statement_key"] = previous_statement_key
        dto["supersedes_statement_key"] = supersedes_statement_key
        dto["superseded_by_statement_key"] = superseded_by_statement_key
        dto["opening_balance_in_cents"] = balances["opening_balance_in_cents"]
        dto["total_debit_in_cents"] = balances["total_debit_in_cents"]
        dto["total_credit_in_cents"] = balances["total_credit_in_cents"]
        dto["closing_balance_in_cents"] = balances["closing_balance_in_cents"]
        dto["lines"] = [
            StatementDTO.line_to_dict(ledger_entry, ledger_transaction) for ledger_entry, ledger_transaction in lines
        ]

        return dto

    @staticmethod
    def verification_to_dict(statement: Statement | None) -> dict:
        """A resposta da verificação pública: só se casa e quando foi emitido,
        nada mais (D0009 :100-103)."""
        if statement is None:
            return {"match": False}

        return {"match": True, "issued_at": utc_with_z(statement.created_at)}

    @staticmethod
    def line_to_dict(ledger_entry, ledger_transaction) -> dict:
        dto = dict()
        dto["ledger_transaction_key"] = ledger_transaction.ledger_transaction_key
        dto["transaction_type"] = ledger_transaction.ledger_transaction_type.enumerator
        dto["direction"] = ledger_entry.direction
        dto["amount_in_cents"] = int(ledger_entry.amount_in_cents)
        dto["value_date"] = utc_with_z(ledger_transaction.value_date)
        dto["contract_key"] = empty_as_null(ledger_transaction.contract_key)
        dto["period_reference"] = empty_as_null(ledger_transaction.period_reference)
        dto["split_version"] = ledger_transaction.split_version
        dto["payer_party_key"] = empty_as_null(ledger_transaction.payer_party_key)

        return dto
