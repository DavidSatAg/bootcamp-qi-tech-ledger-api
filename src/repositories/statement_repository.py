from database import Context
from models import Statement


class StatementRepository:
    """Os extratos. Só aqui existe query sobre eles."""

    def __init__(self, context: Context) -> None:
        self.session = context.db_session

    def get_by_key(self, statement_key: str) -> Statement:
        return self.session.query(Statement).filter(Statement.statement_key == statement_key).first()
