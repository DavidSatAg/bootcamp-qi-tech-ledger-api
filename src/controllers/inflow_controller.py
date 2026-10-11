from datetime import datetime, timezone

from controllers.base_controller import BaseController
from controllers.posting_controller import PostingController
from dtos import LedgerTransactionDTO
from errors import ContractNotProvisioned, InvalidSchema
from models import LedgerAccountType, LedgerEntry, LedgerTransactionType, PurposeCode
from repositories import LedgerAccountRepository, LedgerTransactionRepository

ENDPOINT = "POST /transfers/inflow"

# O status que o motor guarda no registro de idempotência para o replay.
# O status da resposta HTTP sai do resource, e os dois são o 201 da RFC :147.
SUCCESS_STATUS = 201


class InflowController(BaseController):
    """A entrada por Pix: o dinheiro que chega de fora para a COLLECTION de
    um contrato (guia do Ledger §6, inflow)."""

    def __init__(self) -> None:
        super().__init__(__name__)
        self.ledger_account_repository = LedgerAccountRepository(self.context)
        self.ledger_transaction_repository = LedgerTransactionRepository(self.context)

    def create(self, payload: dict, idempotency_key: str, raw_body: bytes) -> dict:
        """Confere a chave, acha as duas contas e a data-valor, nesta ordem
        (RN-02), e entrega as pernas ao motor."""
        PostingController.require_idempotency_key(idempotency_key)
        collection, external = self._find_accounts(payload)
        value_date = self._value_date(payload)

        # O escopo da chave é o livro debitado: o `external` do cliente.
        idempotency = {
            "client_key": external.client_key,
            "endpoint": ENDPOINT,
            "key": idempotency_key,
            "raw_body": raw_body,
        }
        transaction = {
            "ledger_transaction_type": LedgerTransactionType.INFLOW,
            "contract_key": payload["contract_key"],
            "period_reference": payload["period_reference"],
            "payer_party_key": payload["payer_party_key"],
            "end_to_end_id": payload["end_to_end_id"],
            "value_date": value_date,
            "actor": payload["actor"],
            "reason": payload.get("reason"),
        }
        amount_in_cents = payload["amount_in_cents"]
        legs = [
            (external, LedgerEntry.DEBIT, amount_in_cents),
            (collection, LedgerEntry.CREDIT, amount_in_cents),
        ]
        purpose_pairs = [(external, collection)]

        posting_controller = PostingController()
        ledger_transaction_key = posting_controller.post(
            idempotency, transaction, legs, purpose_pairs, SUCCESS_STATUS
        )

        ledger_transaction = self.ledger_transaction_repository.get_by_key(ledger_transaction_key)

        return LedgerTransactionDTO.obj_to_dict(ledger_transaction)

    def _find_accounts(self, payload: dict) -> tuple:
        """A COLLECTION do contrato e o `external/CASH` do mesmo cliente.

        Sem COLLECTION não há cliente, e sem cliente não há onde guardar a
        chave de idempotência: o 035 sai antes do motor e não grava nada.
        O `external` existe sempre que há contrato (provisionamento, S04 RN-07).
        """
        collection = self.ledger_account_repository.find_contract_account(
            payload["contract_key"], PurposeCode.COLLECTION
        )

        if collection is None:
            raise ContractNotProvisioned(payload["contract_key"])

        external = self.ledger_account_repository.find_by_natural_key(
            collection.client_key, LedgerAccountType.EXTERNAL, PurposeCode.CASH, "", ""
        )

        return collection, external

    def _value_date(self, payload: dict) -> datetime:
        """A data-valor do corpo, ou o agora quando ela não veio (CU-J10).

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
