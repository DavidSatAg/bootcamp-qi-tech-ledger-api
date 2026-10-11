from constants import PLATFORM_PARTY_KEY
from controllers.base_controller import BaseController
from dtos import ContractLedgerDTO
from models import LedgerAccount, LedgerAccountType, PurposeCode
from repositories import LedgerAccountRepository
from utils.request_context import get_request_id

# Os cinco livros do cliente: (tipo, propósito, papel do dono). O dono
# sai do papel: o cliente na `own`, a plataforma na `revenue`, ninguém
# nas três contas de serviço.
CLIENT_BOOKS = [
    (LedgerAccountType.EXTERNAL, PurposeCode.CASH, ""),
    (LedgerAccountType.SUSPENSE, PurposeCode.UNALLOCATED, ""),
    (LedgerAccountType.CLEARING, PurposeCode.TRANSIT, ""),
    (LedgerAccountType.OWN, PurposeCode.OWN, "administrator"),
    (LedgerAccountType.REVENUE, PurposeCode.PLATFORM_FEE, "platform"),
]


class ContractLedgerController(BaseController):
    """O provisionamento: os livros do cliente e os earmarks do contrato."""

    def __init__(self) -> None:
        super().__init__(__name__)
        self.ledger_account_repository = LedgerAccountRepository(self.context)

    def provision(self, payload: dict) -> tuple:
        """Abre o que falta e devolve (corpo, criou?).

        Tudo numa transação só, com o commit na última linha.
        """
        client_books = self._open_client_books(payload)
        collection = self._find_or_create(
            payload, LedgerAccountType.EARMARK, PurposeCode.COLLECTION, payload["contract_key"], "", ""
        )

        item_accounts = []
        for item in payload["items"]:
            item_accounts.append(self._open_item_account(payload, item, client_books))

        accounts = self._split_accounts(collection, item_accounts, client_books)

        contract_ledger_dto = ContractLedgerDTO.obj_to_dict(payload["contract_key"], accounts)
        self.session.commit()

        return contract_ledger_dto, True

    def _split_accounts(self, collection: LedgerAccount, item_accounts: list, client_books: dict) -> list:
        """As contas do split, na ordem do 01b: COLLECTION, os earmarks na
        ordem dos itens, OWN e PLATFORM_FEE."""
        accounts = [collection]

        for item_account in item_accounts:
            if item_account.purpose_code.enumerator != PurposeCode.OWN:
                accounts.append(item_account)

        accounts.append(client_books[PurposeCode.OWN])
        accounts.append(client_books[PurposeCode.PLATFORM_FEE])

        return accounts

    def _open_client_books(self, payload: dict) -> dict:
        owners = {
            "": "",
            "administrator": payload["client_party_key"],
            "platform": PLATFORM_PARTY_KEY,
        }

        client_books = dict()
        for ledger_account_type, purpose_code, owner_role in CLIENT_BOOKS:
            client_books[purpose_code] = self._find_or_create(
                payload, ledger_account_type, purpose_code, "", owners[owner_role], owner_role
            )

        return client_books

    def _open_item_account(self, payload: dict, item: dict, client_books: dict) -> LedgerAccount:
        """O destino de um item: a `own/OWN` do cliente, ou um earmark do contrato."""
        if item["purpose_code"] == PurposeCode.OWN:
            return client_books[PurposeCode.OWN]

        return self._find_or_create(
            payload,
            LedgerAccountType.EARMARK,
            item["purpose_code"],
            payload["contract_key"],
            item["beneficiary_party_key"],
            item["beneficiary_role"],
        )

    def _find_or_create(
        self,
        payload: dict,
        ledger_account_type: str,
        purpose_code: str,
        contract_key: str,
        owner_party_key: str,
        owner_role: str,
    ) -> LedgerAccount:
        """Reusa a conta, se já existe; senão, cria. Só a criada ganha evento."""
        ledger_account = self.ledger_account_repository.find_by_natural_key(
            payload["client_key"], ledger_account_type, purpose_code, contract_key, owner_party_key
        )

        if ledger_account is not None:
            return ledger_account

        return self.ledger_account_repository.create(
            client_key=payload["client_key"],
            ledger_account_type=ledger_account_type,
            purpose_code=purpose_code,
            contract_key=contract_key,
            owner_party_key=owner_party_key,
            owner_role=owner_role,
            actor=payload["actor"],
            reason=payload.get("reason"),
            trace_id=get_request_id(),
        )
