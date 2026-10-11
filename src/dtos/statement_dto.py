from dtos.ledger_transaction_dto import utc_with_z
from models import Statement


class StatementDTO:
    """Traduz o extrato no JSON que a API devolve."""

    @staticmethod
    def obj_to_dict(statement: Statement) -> dict:
        dto = dict()
        dto["statement_key"] = statement.statement_key
        dto["period_start"] = utc_with_z(statement.period_start)
        dto["period_end"] = utc_with_z(statement.period_end)
        dto["created_at"] = utc_with_z(statement.created_at)
        dto["content_hash"] = statement.content_hash

        return dto
