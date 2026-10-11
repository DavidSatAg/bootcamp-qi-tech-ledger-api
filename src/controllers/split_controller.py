from datetime import datetime, timezone
from decimal import ROUND_FLOOR, Decimal

from controllers.base_controller import BaseController
from controllers.posting_controller import PostingController
from dtos import LedgerTransactionDTO
from errors import ContractNotProvisioned, InvalidSchema
from models import LedgerEntry, LedgerTransactionType, PurposeCode, SplitSnapshot
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

        split_rows = self.split_snapshot_repository.list_by_version(payload["contract_key"], split_version)
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
            "split_version": split_version,
            "value_date": value_date,
            "actor": payload["actor"],
            "reason": payload.get("reason"),
        }

        legs, purpose_pairs = self._legs(collection, split_rows)

        posting_controller = PostingController()
        ledger_transaction_key = posting_controller.post(
            idempotency, transaction, legs, purpose_pairs, SUCCESS_STATUS
        )

        ledger_transaction = self.ledger_transaction_repository.get_by_key(ledger_transaction_key)

        return LedgerTransactionDTO.obj_to_dict(ledger_transaction)

    def _legs(self, collection, split_rows: list) -> tuple:
        """As pernas e os pares da divisão, na ordem do remodelagem/05 (RN-04):
        o débito da COLLECTION, o crédito de cada destino em ordem de `id`, e
        a taxa da plataforma, da `own` para a `revenue`.

        Perna de valor 0 não existe (G:229): sai, e o par dela também (D2).
        """
        rent_amount_in_cents = Decimal(split_rows[0][0].rent_amount_in_cents)
        item_rows = [row for row in split_rows if row[1].id == collection.id]
        fee_rows = [row for row in split_rows if row[1].id != collection.id]

        item_amounts = self._item_amounts(rent_amount_in_cents, item_rows)
        fixed_amounts = [
            amount for (split_snapshot, _source, _target), amount in zip(item_rows, item_amounts)
            if split_snapshot.allocation_type == SplitSnapshot.FIXED
        ]
        expected_amount_in_cents = int(rent_amount_in_cents) + sum(fixed_amounts)

        legs = [(collection, LedgerEntry.DEBIT, expected_amount_in_cents)]
        purpose_pairs = []

        for (_split_snapshot, source, target), amount_in_cents in zip(item_rows, item_amounts):
            if amount_in_cents > 0:
                legs.append((target, LedgerEntry.CREDIT, amount_in_cents))
                purpose_pairs.append((source, target))

        for split_snapshot, source, target in fee_rows:
            fee_amount_in_cents = self._percentage_of(rent_amount_in_cents, split_snapshot.percentage)
            if fee_amount_in_cents > 0:
                legs.append((source, LedgerEntry.DEBIT, fee_amount_in_cents))
                legs.append((target, LedgerEntry.CREDIT, fee_amount_in_cents))
                purpose_pairs.append((source, target))

        return legs, purpose_pairs

    def _item_amounts(self, rent_amount_in_cents: Decimal, item_rows: list) -> list:
        """O valor de cada linha que sai da COLLECTION (RN-03; 01b :242-255):
        `percentage` é o piso do percentual do aluguel; `fixed`, o valor da
        linha; `remainder`, o aluguel menos os `percentage` destas linhas."""
        amounts = []
        percentage_total = 0

        for split_snapshot, _source, _target in item_rows:
            amount_in_cents = None

            if split_snapshot.allocation_type == SplitSnapshot.PERCENTAGE:
                amount_in_cents = self._percentage_of(rent_amount_in_cents, split_snapshot.percentage)
                percentage_total = percentage_total + amount_in_cents

            if split_snapshot.allocation_type == SplitSnapshot.FIXED:
                amount_in_cents = int(split_snapshot.amount_in_cents)

            amounts.append(amount_in_cents)

        remainder_amount_in_cents = int(rent_amount_in_cents) - percentage_total

        for index, (split_snapshot, _source, _target) in enumerate(item_rows):
            if split_snapshot.allocation_type == SplitSnapshot.REMAINDER:
                amounts[index] = remainder_amount_in_cents

        return amounts

    @staticmethod
    def _percentage_of(rent_amount_in_cents: Decimal, percentage: Decimal) -> int:
        """O piso de aluguel × p / 100, em centavos inteiros, só com `Decimal`."""
        amount = rent_amount_in_cents * Decimal(percentage) / Decimal(100)

        return int(amount.to_integral_value(rounding=ROUND_FLOOR))

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
