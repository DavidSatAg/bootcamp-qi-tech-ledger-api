from controllers.base_controller import BaseController
from dtos import StatementDTO
from errors import StatementNotFound
from repositories import StatementRepository


class StatementController(BaseController):
    """O extrato com hash encadeado de uma conta."""

    def __init__(self) -> None:
        super().__init__(__name__)
        self.statement_repository = StatementRepository(self.context)

    def get_by_key(self, statement_key: str) -> dict:
        self.logger.debug(f"Buscando o extrato de chave {statement_key}")

        statement = self.statement_repository.get_by_key(statement_key)

        if statement is None:
            raise StatementNotFound(statement_key)

        return StatementDTO.obj_to_dict(statement)
