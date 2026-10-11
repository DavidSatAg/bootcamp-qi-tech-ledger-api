from datetime import datetime, timezone
from uuid import uuid4

from database import Context
from models import LedgerTransaction, Outbox, OutboxStatus, OutboxStatusEvent


class OutboxRepository:
    """A outbox: o pedido de despacho ao provedor, gravado no mesmo commit
    das pernas do repasse (D0006), e a trilha de status dele."""

    def __init__(self, context: Context) -> None:
        self.session = context.db_session

    def create(
        self,
        ledger_transaction: LedgerTransaction,
        beneficiary_party_key: str,
        dispatch_idempotency_key: str,
        payload: dict,
        actor: str,
        reason: str,
        trace_id: str,
    ) -> Outbox:
        """Grava a outbox em `pending`, com o evento de nascimento
        null -> pending. O `flush` manda os INSERTs agora, sem commit."""
        pending_status = self.get_status(OutboxStatus.PENDING)

        outbox = Outbox()
        outbox.outbox_key = str(uuid4())
        outbox.outbox_status = pending_status
        outbox.ledger_transaction_id = ledger_transaction.id
        outbox.beneficiary_party_key = beneficiary_party_key
        outbox.dispatch_idempotency_key = dispatch_idempotency_key
        outbox.payload = payload
        outbox.attempt_count = 0

        self.session.add(outbox)
        self.session.flush()

        self._add_event(outbox, None, pending_status, actor, reason, trace_id)

        return outbox

    def change_status(
        self,
        outbox: Outbox,
        to_status: str,
        actor: str,
        reason: str,
        trace_id: str,
        increment_attempt: bool = False,
    ) -> Outbox:
        """Leva a outbox ao novo status, com o evento atual -> novo, e conta
        a tentativa quando pedido. O `flush` manda tudo agora, sem commit."""
        new_status = self.get_status(to_status)

        self._add_event(outbox, outbox.outbox_status, new_status, actor, reason, trace_id)

        outbox.outbox_status = new_status
        if increment_attempt:
            outbox.attempt_count = outbox.attempt_count + 1

        self.session.flush()

        return outbox

    def get_by_id(self, outbox_id: int) -> Outbox:
        return self.session.query(Outbox).filter(Outbox.id == outbox_id).first()

    def get_by_transaction(self, ledger_transaction_id: int) -> Outbox:
        """A outbox do repasse: uma por transação (INV-02)."""
        return self.session.query(Outbox).filter(Outbox.ledger_transaction_id == ledger_transaction_id).first()

    def get_status(self, enumerator: str) -> OutboxStatus:
        return self.session.query(OutboxStatus).filter(OutboxStatus.enumerator == enumerator).one()

    def _add_event(self, outbox: Outbox, from_status, to_status: OutboxStatus, actor: str, reason: str, trace_id: str) -> None:
        status_event = OutboxStatusEvent()
        status_event.outbox_id = outbox.id
        status_event.from_status = from_status
        status_event.to_status = to_status
        status_event.actor = actor
        status_event.reason = reason
        status_event.trace_id = trace_id
        status_event.event_datetime = datetime.now(timezone.utc)

        self.session.add(status_event)
        self.session.flush()
