from controllers.base_controller import BaseController
from dtos import LedgerAccountDTO
from errors import LedgerAccountNotFound
from errors import LedgerAccountInvalidTransition
from models import LedgerAccountStatus
from repositories import LedgerAccountRepository
from utils.request_context import get_request_id

# As setas do diagrama da conta (06 :99-104): de onde se pode ir a onde.
# O mesmo estado e tudo a partir de `closed` ficam de fora (fatia 14, D2).
VALID_TRANSITIONS = {
    (LedgerAccountStatus.ACTIVE, LedgerAccountStatus.BLOCKED),
    (LedgerAccountStatus.BLOCKED, LedgerAccountStatus.ACTIVE),
    (LedgerAccountStatus.ACTIVE, LedgerAccountStatus.CLOSED),
    (LedgerAccountStatus.BLOCKED, LedgerAccountStatus.CLOSED),
}


class LedgerAccountController(BaseController):
    """A consulta das contas do ledger, e a mudança de status delas (fatia
    14): só o `change_status` commita."""

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

    def change_status(self, ledger_account_key: str, payload: dict) -> dict:
        """Bloqueia, desbloqueia ou encerra a conta (fatia 14, RN-01): lê a
        conta, confere a seta do diagrama (RN-02), grava o status e o evento,
        e devolve a conta como o GET. O commit é a última linha."""
        ledger_account = self.ledger_account_repository.get_by_key_for_update(ledger_account_key)

        if ledger_account is None:
            raise LedgerAccountNotFound(ledger_account_key)

        to_status = payload["status"]
        from_status = ledger_account.ledger_account_status.enumerator

        if (from_status, to_status) not in VALID_TRANSITIONS:
            raise LedgerAccountInvalidTransition()

        self.ledger_account_repository.change_status(
            ledger_account, to_status, payload["actor"], payload.get("reason"), get_request_id()
        )

        balance_in_cents = self.ledger_account_repository.get_balance(ledger_account)
        ledger_account_dto = LedgerAccountDTO.obj_to_dict(ledger_account, balance_in_cents)

        self.session.commit()

        return ledger_account_dto
