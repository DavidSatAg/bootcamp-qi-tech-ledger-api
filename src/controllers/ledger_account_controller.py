from controllers.base_controller import BaseController
from dtos import LedgerAccountDTO
from errors import LedgerAccountNotFound
from repositories import LedgerAccountRepository


class LedgerAccountController(BaseController):
    """A consulta das contas do ledger. Só lê: nenhum commit aqui."""

    def __init__(self) -> None:
        super().__init__(__name__)
        self.ledger_account_repository = LedgerAccountRepository(self.context)

    def get_by_key(self, ledger_account_key: str) -> dict:
        self.logger.debug(f"Buscando a conta de chave {ledger_account_key}")

        ledger_account = self.ledger_account_repository.get_by_key(ledger_account_key)

        if ledger_account is None:
            raise LedgerAccountNotFound(ledger_account_key)

        balance_in_cents = self.ledger_account_repository.get_balance(ledger_account)

        return LedgerAccountDTO.obj_to_dict(ledger_account, balance_in_cents)

    def get_list(self, limit: int, offset: int, filters: dict) -> dict:
        ledger_accounts_list = self.ledger_account_repository.list_page(limit, offset, filters)

        # Veio o extra pedido a mais: há próxima página, e ele não entra.
        is_last_page = True
        if len(ledger_accounts_list) > limit:
            is_last_page = False
            ledger_accounts_list = ledger_accounts_list[:-1]

        return {
            "ledger_accounts_list_dto": LedgerAccountDTO.list_obj_to_list_dict(ledger_accounts_list),
            "is_last_page": is_last_page,
        }
