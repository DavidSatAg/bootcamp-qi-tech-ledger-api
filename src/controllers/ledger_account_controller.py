from sqlalchemy.exc import OperationalError

from controllers.base_controller import BaseController
from dtos import LedgerAccountDTO
from errors import LedgerAccountNotFound
from errors import LedgerAccountInvalidTransition
from errors import LedgerAccountHasBalance
from errors import LockTimeout
from models import LedgerAccountStatus
from repositories import LedgerAccountRepository
from utils.request_context import get_request_id

# O SQLSTATE do Postgres para "lock_not_available": a trava não veio dentro
# do lock_timeout.
LOCK_NOT_AVAILABLE = "55P03"

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
        conta com trava (RN-04), confere a seta do diagrama (RN-02) e, no
        encerramento, o saldo somado depois da trava (RN-03); grava o status
        e o evento, e devolve a conta como o GET. O commit é a última linha."""
        try:
            ledger_account = self.ledger_account_repository.get_by_key_for_update(ledger_account_key)
        except OperationalError as error:
            if getattr(error.orig, "pgcode", None) == LOCK_NOT_AVAILABLE:
                raise LockTimeout() from error
            raise

        if ledger_account is None:
            raise LedgerAccountNotFound(ledger_account_key)

        to_status = payload["status"]
        from_status = ledger_account.ledger_account_status.enumerator

        if (from_status, to_status) not in VALID_TRANSITIONS:
            raise LedgerAccountInvalidTransition()

        # Somado depois da trava (D0007 :46-47): nenhum lançamento entra no
        # meio. Com saldo, nada foi escrito, e o middleware desfaz.
        if to_status == LedgerAccountStatus.CLOSED and self.ledger_account_repository.get_balance(ledger_account) != 0:
            raise LedgerAccountHasBalance()

        self.ledger_account_repository.change_status(
            ledger_account, to_status, payload["actor"], payload.get("reason"), get_request_id()
        )

        balance_in_cents = self.ledger_account_repository.get_balance(ledger_account)
        ledger_account_dto = LedgerAccountDTO.obj_to_dict(ledger_account, balance_in_cents)

        self.session.commit()

        return ledger_account_dto
