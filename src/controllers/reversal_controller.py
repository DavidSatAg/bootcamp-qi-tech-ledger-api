from datetime import datetime, timezone

from controllers.base_controller import BaseController
from controllers.posting_controller import PostingController
from dtos import LedgerTransactionDTO
from errors import LedgerTransactionNotFound
from models import LedgerEntry, LedgerTransactionType
from repositories import LedgerEntryRepository, LedgerTransactionRepository

# O status que o motor guarda no registro de idempotência para o replay.
# O status da resposta HTTP sai do resource, e os dois são o 201 da RFC :151.
SUCCESS_STATUS = 201

INVERTED_DIRECTION = {LedgerEntry.DEBIT: LedgerEntry.CREDIT, LedgerEntry.CREDIT: LedgerEntry.DEBIT}


class ReversalController(BaseController):
    """O estorno: a transação original de novo, com as pernas invertidas
    (guia do Ledger §6, reversal; D0005)."""

    def __init__(self) -> None:
        super().__init__(__name__)
        self.ledger_transaction_repository = LedgerTransactionRepository(self.context)
        self.ledger_entry_repository = LedgerEntryRepository(self.context)

    def create(self, ledger_transaction_key: str, payload: dict, idempotency_key: str, raw_body: bytes) -> dict:
        """Confere a chave e acha a original, nesta ordem (RN-01), e a
        estorna. Sem a original não há livro que escope o registro: o 020
        sai antes do motor e nada se grava (D-01).

        A chave da original é copiada antes do motor: o commit expira o ORM
        (`expire_on_commit`)."""
        PostingController.require_idempotency_key(idempotency_key)
        original = self.ledger_transaction_repository.get_by_key(ledger_transaction_key)

        if original is None:
            raise LedgerTransactionNotFound()

        original_key = original.ledger_transaction_key

        # A impressão digital é só do corpo, que não cita a original: o
        # endpoint com a chave dela separa os estornos de originais
        # diferentes sob a mesma chave (RN-02, D3).
        idempotency = {
            "endpoint": f"POST /transfers/{original_key}/reversal",
            "key": idempotency_key,
            "raw_body": raw_body,
        }
        header = {
            "value_date": datetime.now(timezone.utc),
            "actor": payload["actor"],
            "reason": payload.get("reason"),
        }

        reversal_key = self.reverse(original, payload.get("amount_in_cents"), idempotency, header, SUCCESS_STATUS)

        reversal = self.ledger_transaction_repository.get_by_key(reversal_key)
        dto = LedgerTransactionDTO.obj_to_dict(reversal)
        dto["reverses_transaction_key"] = original_key

        return dto

    def reverse(
        self,
        original,
        amount_in_cents: int | None,
        idempotency: dict,
        header: dict,
        success_status: int,
        record_error=True,
    ) -> str:
        """Posta o estorno da `original` e devolve a chave dele (RN-02).

        `idempotency` = {endpoint, key, raw_body}: o livro do escopo sai
        daqui, da 1ª perna D do estorno; `header` = {value_date, actor,
        reason}. Sem `amount_in_cents`, o estorno é total (RN-04a).
        """
        original_id = original.id
        contract_key = original.contract_key
        period_reference = original.period_reference

        legs = self._inverted_legs(original_id, amount_in_cents)

        first_debit = next(ledger_account for ledger_account, direction, _amount in legs if direction == LedgerEntry.DEBIT)
        scope = dict(idempotency, client_key=first_debit.client_key)

        # Contrato e competência herdados; sem `split_version`, sem
        # `end_to_end_id` e sem pagador (RN-07; G :207-210, :462).
        transaction = {
            "ledger_transaction_type": LedgerTransactionType.REVERSAL,
            "reverses_transaction_id": original_id,
            "contract_key": contract_key,
            "period_reference": period_reference,
            "value_date": header["value_date"],
            "actor": header["actor"],
            "reason": header["reason"],
        }

        # Sem pares: o estorno não consulta a `purpose_rule` (RN-06; G :354).
        posting_controller = PostingController()
        return posting_controller.post(scope, transaction, legs, [], success_status, record_error=record_error)

    def _inverted_legs(self, original_id: int, amount_in_cents: int | None) -> list:
        """As pernas da original, débitos primeiro e em `id`, cada uma com a
        direção trocada; com `amount_in_cents`, todas com esse valor
        (RN-02, RN-04a)."""
        legs = []

        for ledger_entry, ledger_account in self.ledger_entry_repository.list_by_transactions([original_id]):
            leg_amount_in_cents = int(ledger_entry.amount_in_cents)
            if amount_in_cents is not None:
                leg_amount_in_cents = amount_in_cents
            legs.append((ledger_account, INVERTED_DIRECTION[ledger_entry.direction], leg_amount_in_cents))

        return legs
