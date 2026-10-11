from sqlalchemy.orm import aliased

from database import Context
from models import PurposeCode, PurposeRule


class PurposeRuleRepository:
    """A tabela de pares de propósito permitidos. Negação por padrão."""

    def __init__(self, context: Context) -> None:
        self.session = context.db_session

    def exists_pair(self, source_purpose_code: str, target_purpose_code: str) -> bool:
        source = aliased(PurposeCode)
        target = aliased(PurposeCode)

        purpose_rule = (
            self.session.query(PurposeRule)
            .join(source, PurposeRule.source_purpose_code_id == source.id)
            .join(target, PurposeRule.target_purpose_code_id == target.id)
            .filter(source.enumerator == source_purpose_code, target.enumerator == target_purpose_code)
            .first()
        )

        return purpose_rule is not None
