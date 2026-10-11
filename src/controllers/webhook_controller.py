from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError, OperationalError

from controllers.base_controller import BaseController
from controllers.posting_controller import PostingController
from errors import InvalidSchema, LockTimeout, OutboxNotFound
from models import LedgerAccountType, LedgerEntry, LedgerTransactionType, OutboxStatus, PurposeCode
from repositories import (
    LedgerAccountRepository,
    LedgerEntryRepository,
    LedgerTransactionRepository,
    OutboxRepository,
    ProviderEventRepository,
)
from utils.request_context import get_request_id

ENDPOINT = "POST /webhooks/provider"

# O status que o motor guarda no registro de idempotência. O status da
# resposta HTTP sai do resource, e os dois são o 204 da RFC :154.
SUCCESS_STATUS = 204

# Quem move o dinheiro na liquidação é o provedor (06:35-37; G:454).
PROVIDER_ACTOR = "provider"

# O SQLSTATE do Postgres para "lock_not_available": a trava não veio dentro
# do lock_timeout.
LOCK_NOT_AVAILABLE = "55P03"


class WebhookController(BaseController):
    """O aviso do provedor sobre um repasse já enviado: a liquidação
    confirmada ou a falha (guia do Ledger §6; RFC :154)."""

    def __init__(self) -> None:
        super().__init__(__name__)
        self.outbox_repository = OutboxRepository(self.context)
        self.provider_event_repository = ProviderEventRepository(self.context)
        self.ledger_entry_repository = LedgerEntryRepository(self.context)
        self.ledger_account_repository = LedgerAccountRepository(self.context)
        self.ledger_transaction_repository = LedgerTransactionRepository(self.context)

    def handle(self, payload: dict, raw_body: bytes) -> None:
        """Uma transação (RN-01): a data-valor, a outbox travada, o aviso
        guardado e, por fim, o motor, cujo commit é o desta requisição.
        Nada se lê do ORM depois dele."""
        value_date = self._value_date(payload)
        outbox = self._lock_outbox(payload["outbox_key"])

        # O mesmo `provider_reference` já guardado é o reenvio: 204, sem
        # mais nada (RN-03; RFC :419-421).
        if not self._register_event(payload, outbox):
            return

        self._settle(payload, outbox, value_date, raw_body)

    def _register_event(self, payload: dict, outbox) -> bool:
        """O aviso guardado antes de tudo (RN-03; G:449): SAVEPOINT + INSERT.
        A colisão da UNIQUE(provider_reference) desfaz só o SAVEPOINT e
        devolve False."""
        savepoint = self.session.begin_nested()
        try:
            self.provider_event_repository.create(
                provider_reference=payload["provider_reference"],
                event_type=payload["event_type"],
                outbox_id=outbox.id,
                raw_payload=payload,
                received_at=datetime.now(timezone.utc),
            )
        except IntegrityError:
            savepoint.rollback()
            return False

        savepoint.commit()

        return True

    def _settle(self, payload: dict, outbox, value_date: datetime, raw_body: bytes) -> None:
        """As pernas do repasse dizem de onde o dinheiro saiu e quanto
        (RN-05): a confirmação tira o valor da `clearing` para o `external`
        do cliente; o motor posta e leva a outbox a `settled` (RN-06, RN-07)."""
        _source, clearing, amount_in_cents = self._payout_legs(outbox)
        payout = self.ledger_transaction_repository.get_by_key(
            self.ledger_transaction_repository.get_key_by_id(outbox.ledger_transaction_id)
        )

        external = self.ledger_account_repository.find_by_natural_key(
            clearing.client_key, LedgerAccountType.EXTERNAL, PurposeCode.CASH, "", ""
        )

        # O escopo da chave é o livro da `clearing`, que é o debitado (D1).
        idempotency = {
            "client_key": clearing.client_key,
            "endpoint": ENDPOINT,
            "key": payload["provider_reference"],
            "raw_body": raw_body,
        }
        transaction = {
            "ledger_transaction_type": LedgerTransactionType.SETTLEMENT,
            "contract_key": payout.contract_key,
            "period_reference": payout.period_reference,
            "value_date": value_date,
            "actor": PROVIDER_ACTOR,
            "reason": payload["event_type"],
        }
        legs = [
            (clearing, LedgerEntry.DEBIT, amount_in_cents),
            (external, LedgerEntry.CREDIT, amount_in_cents),
        ]
        purpose_pairs = [(clearing, external)]

        posting_controller = PostingController()
        posting_controller.post(
            idempotency,
            transaction,
            legs,
            purpose_pairs,
            SUCCESS_STATUS,
            after_write=lambda ledger_transaction: self._close_outbox(outbox, OutboxStatus.SETTLED, payload),
            # O erro não fica gravado: o provedor repete o mesmo aviso, e
            # ele tem de rodar de novo (RN-06, D-02).
            record_error=False,
        )

    def _payout_legs(self, outbox) -> tuple:
        """(origem, clearing, valor) do repasse da outbox: a perna D é a
        origem, a C é a `clearing` (RN-05)."""
        source = None
        clearing = None
        amount_in_cents = None

        for ledger_entry, ledger_account in self.ledger_entry_repository.list_by_transactions(
            [outbox.ledger_transaction_id]
        ):
            if ledger_entry.direction == LedgerEntry.DEBIT:
                source = ledger_account
                amount_in_cents = int(ledger_entry.amount_in_cents)
            else:
                clearing = ledger_account

        return source, clearing, amount_in_cents

    def _close_outbox(self, outbox, to_status: str, payload: dict) -> None:
        """Depois do passo 8, no SAVEPOINT do motor: o estado da outbox e o
        evento dele entram no mesmo commit das pernas (RN-07; 06:28-29)."""
        self.outbox_repository.change_status(outbox, to_status, PROVIDER_ACTOR, payload["event_type"], get_request_id())

    def _lock_outbox(self, outbox_key: str):
        """A outbox do aviso, travada (RN-02). Sem ela não há cliente que
        escope o registro: o 031 sai aqui e nada se grava (D-01)."""
        try:
            outbox = self.outbox_repository.get_by_key_for_update(outbox_key)
        except OperationalError as error:
            if getattr(error.orig, "pgcode", None) == LOCK_NOT_AVAILABLE:
                raise LockTimeout() from error
            raise

        if outbox is None:
            raise OutboxNotFound(outbox_key)

        return outbox

    def _value_date(self, payload: dict) -> datetime:
        """A data-valor do corpo. O `pattern` do schema conta dígitos, não
        dias: "2026-02-30" passa por ele e morre aqui, como pedido malformado
        (400)."""
        value_date = payload["value_date"]

        try:
            return datetime.fromisoformat(value_date)
        except ValueError:
            raise InvalidSchema(f"value_date {value_date} is not a real date")
