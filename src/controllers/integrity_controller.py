from controllers.base_controller import BaseController
from dtos import IntegrityDTO
from repositories import LedgerAccountRepository, LedgerEntryRepository


class IntegrityController(BaseController):
    """A conferência de integridade do ledger. Só lê: nenhum commit, nenhuma trava."""

    def __init__(self) -> None:
        super().__init__(__name__)
        self.ledger_entry_repository = LedgerEntryRepository(self.context)
        self.ledger_account_repository = LedgerAccountRepository(self.context)

    def get_integrity(self, client_key: str | None) -> dict:
        """Ativo = passivo + patrimônio, no geral ou no livro pedido, e as
        contas negativas sem estorno no histórico (suspeitas)."""
        self.logger.debug(f"Conferindo a integridade do livro {client_key}")

        totals = self.ledger_entry_repository.sum_by_side(client_key)
        totals["difference"] = totals["asset"] - totals["liability"] - totals["equity"]

        negatives = self.ledger_account_repository.list_negative_without_reversal(client_key)

        return IntegrityDTO.obj_to_dict(client_key, totals, negatives)
