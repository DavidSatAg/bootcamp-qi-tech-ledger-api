from controllers.base_controller import BaseController
from dtos import LedgerTransactionDTO
from repositories import LedgerTransactionRepository


class TransferController(BaseController):
    """A consulta das transações por pagador ou por competência do
    contrato (fatia 14, RN-10). Só lê: nenhum commit aqui."""

    def __init__(self) -> None:
        super().__init__(__name__)
        self.ledger_transaction_repository = LedgerTransactionRepository(self.context)

    def get_list(self, limit: int, offset: int, filters: dict) -> dict:
        ledger_transactions_list = self.ledger_transaction_repository.list_page(limit, offset, filters)

        # Veio o extra pedido a mais: há próxima página, e ele não entra.
        is_last_page = True
        if len(ledger_transactions_list) > limit:
            is_last_page = False
            ledger_transactions_list = ledger_transactions_list[:-1]

        return {
            "ledger_transactions_list_dto": [
                LedgerTransactionDTO.obj_to_dict(ledger_transaction) for ledger_transaction in ledger_transactions_list
            ],
            "is_last_page": is_last_page,
        }
