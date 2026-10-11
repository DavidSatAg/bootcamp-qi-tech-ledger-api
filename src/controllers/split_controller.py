from datetime import datetime, timezone

from controllers.base_controller import BaseController
from controllers.posting_controller import PostingController
from dtos import LedgerTransactionDTO
from errors import ContractNotProvisioned, InvalidSchema
from models import LedgerTransactionType, PurposeCode
from repositories import LedgerAccountRepository, LedgerTransactionRepository, SplitSnapshotRepository

ENDPOINT = "POST /transfers/split"

# O status que o motor guarda no registro de idempotência para o replay.
# O status da resposta HTTP sai do resource, e os dois são o 201 da RFC :148.
SUCCESS_STATUS = 201


class SplitController(BaseController):
    """A divisão de uma competência: o dinheiro da COLLECTION do contrato vai
    para os destinos da cópia do split (guia do Ledger §6, split)."""

    def __init__(self) -> None:
        super().__init__(__name__)
        self.ledger_account_repository = LedgerAccountRepository(self.context)
        self.ledger_transaction_repository = LedgerTransactionRepository(self.context)
        self.split_snapshot_repository = SplitSnapshotRepository(self.context)

    def create(self, payload: dict, idempotency_key: str, raw_body: bytes) -> dict:
        """Confere a chave, acha a COLLECTION e a versão vigente do split, lê
        as linhas dela e a data-valor, nesta ordem (RN-02), e entrega as
        pernas ao motor."""
        PostingController.require_idempotency_key(idempotency_key)
        collection = self._find_collection(payload)
        split_version = self.split_snapshot_repository.get_max_version(payload["contract_key"])

        if split_version == 0:
            raise ContractNotProvisioned(payload["contract_key"])

        self.split_snapshot_repository.list_by_version(payload["contract_key"], split_version)
        value_date = self._value_date(payload)

        # O escopo da chave é o livro da COLLECTION, que é o debitado.
        idempotency = {
            "client_key": collection.client_key,
            "endpoint": ENDPOINT,
            "key": idempotency_key,
            "raw_body": raw_body,
        }
        transaction = {
            "ledger_transaction_type": LedgerTransactionType.SPLIT,
            "contract_key": payload["contract_key"],
            "period_reference": payload["period_reference"],
            "value_date": value_date,
            "actor": payload["actor"],
            "reason": payload.get("reason"),
        }

        posting_controller = PostingController()
        ledger_transaction_key = posting_controller.post(idempotency, transaction, [], [], SUCCESS_STATUS)

        ledger_transaction = self.ledger_transaction_repository.get_by_key(ledger_transaction_key)

        return LedgerTransactionDTO.obj_to_dict(ledger_transaction)

    def _find_collection(self, payload: dict):
        """A COLLECTION do contrato. Sem ela não há cliente, e sem cliente não
        há onde guardar a chave: o 035 sai antes do motor e não grava nada."""
        collection = self.ledger_account_repository.find_contract_account(
            payload["contract_key"], PurposeCode.COLLECTION
        )

        if collection is None:
            raise ContractNotProvisioned(payload["contract_key"])

        return collection

    def _value_date(self, payload: dict) -> datetime:
        """A data-valor do corpo, ou o agora quando ela não veio.

        O `pattern` do schema conta dígitos, não dias: "2026-02-30" passa por
        ele e morre aqui, como pedido malformado (400).
        """
        value_date = payload.get("value_date")

        if value_date is None:
            return datetime.now(timezone.utc)

        try:
            return datetime.fromisoformat(value_date)
        except ValueError:
            raise InvalidSchema(f"value_date {value_date} is not a real date")
