from datetime import datetime, timezone
from decimal import ROUND_DOWN, Decimal

from controllers.base_controller import BaseController
from controllers.posting_controller import PostingController
from dtos import LedgerTransactionDTO
from errors import CrossesClientBooks, InvalidSchema, LedgerAccountNotFound
from models import LedgerEntry, LedgerTransactionType
from repositories import LedgerAccountRepository, LedgerTransactionRepository

ENDPOINT = "POST /transfers/internal"

# O status que o motor guarda no registro de idempotência para o replay.
# O status da resposta HTTP sai do resource, e os dois são o 201 da RFC :149.
SUCCESS_STATUS = 201


class InternalController(BaseController):
    """A transferência interna: o dinheiro entre contas do mesmo cliente, à
    escolha de quem chama (RFC :149; fatia 15a)."""

    def __init__(self) -> None:
        super().__init__(__name__)
        self.ledger_account_repository = LedgerAccountRepository(self.context)
        self.ledger_transaction_repository = LedgerTransactionRepository(self.context)

    def create(self, payload: dict, idempotency_key: str, raw_body: bytes) -> dict:
        """Confere a chave, acha a origem, cada destino e a data-valor, nesta
        ordem (15b RN-01), rateia o bruto e entrega as pernas ao motor."""
        PostingController.require_idempotency_key(idempotency_key)
        source = self._find_account(payload["source_account_key"])
        targets = self._find_targets(payload["allocations"])
        value_date = self._value_date(payload)

        # O escopo da chave é o livro debitado: o da origem (RN-04).
        idempotency = {
            "client_key": source.client_key,
            "endpoint": ENDPOINT,
            "key": idempotency_key,
            "raw_body": raw_body,
        }
        # Sem contrato, sem competência, sem pagador: a interna fica fora da
        # cadeia de contrato (RN-05, D6).
        transaction = {
            "ledger_transaction_type": LedgerTransactionType.INTERNAL,
            "contract_key": "",
            "period_reference": "",
            "split_version": None,
            "payer_party_key": "",
            "end_to_end_id": None,
            "value_date": value_date,
            "actor": payload["actor"],
            "reason": payload["reason"],
        }
        # O débito do bruto e um crédito por alocação de parte > 0, na ordem
        # do array (15b RN-07). A parte 0 não vira perna (G:229), mas o
        # destino dela tem o par conferido (15b RN-06).
        gross_amount_in_cents = payload["gross_amount_in_cents"]
        parts = self._allocate(gross_amount_in_cents, payload["allocations"])
        legs = [(source, LedgerEntry.DEBIT, gross_amount_in_cents)]
        for target, part in zip(targets, parts):
            if part > 0:
                legs.append((target, LedgerEntry.CREDIT, part))
        purpose_pairs = [(source, target) for target in targets]

        posting_controller = PostingController()
        ledger_transaction_key = posting_controller.post(
            idempotency,
            transaction,
            legs,
            purpose_pairs,
            SUCCESS_STATUS,
            after_lock=lambda: self._check_same_client_books(source, legs),
        )

        ledger_transaction = self.ledger_transaction_repository.get_by_key(ledger_transaction_key)

        return LedgerTransactionDTO.obj_to_dict(ledger_transaction)

    @staticmethod
    def _check_same_client_books(source, legs: list) -> None:
        """Nenhuma perna sai do livro da origem (RN-07, D3). Chamada pelo
        motor depois da trava e antes do saldo, com ou sem conta travada:
        o 013 é gravado e sai antes de qualquer escrita."""
        for ledger_account, _direction, _amount_in_cents in legs:
            if ledger_account.client_key != source.client_key:
                raise CrossesClientBooks()

    def _find_targets(self, allocations: list) -> list:
        """Cada destino, na ordem do array: o primeiro inexistente é o 018,
        antes do motor e sem gravar (15b RN-01; S15a D-01)."""
        return [self._find_account(allocation["target_account_key"]) for allocation in allocations]

    @staticmethod
    def _allocate(gross_amount_in_cents: int, allocations: list) -> list:
        """A parte de cada alocação, em centavos, na ordem do array (15b
        RN-04). Em `Decimal`, nunca `float`: `fixed` é o `value`;
        `percentage`, o piso de bruto × value / 100; a `remainder`, o que
        sobra do bruto depois das demais, com o resíduo dos percentuais."""
        parts = []
        remainder_index = None

        for index, allocation in enumerate(allocations):
            if allocation["type"] == "remainder":
                remainder_index = index
                parts.append(0)
            elif allocation["type"] == "fixed":
                parts.append(allocation["value"])
            else:
                nominal = Decimal(gross_amount_in_cents) * Decimal(allocation["value"]) / 100
                parts.append(int(nominal.to_integral_value(rounding=ROUND_DOWN)))

        if remainder_index is not None:
            parts[remainder_index] = gross_amount_in_cents - sum(parts)

        return parts

    def _find_account(self, ledger_account_key: str):
        """A conta pela chave. Sem a origem não há cliente onde guardar a
        chave, e o motor recebe contas já achadas: o 018 sai antes dele e
        não grava (D-01)."""
        ledger_account = self.ledger_account_repository.get_by_key(ledger_account_key)

        if ledger_account is None:
            raise LedgerAccountNotFound(ledger_account_key)

        return ledger_account

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
