from datetime import datetime
from uuid import uuid4

from database import Context
from models import ProviderEvent


class ProviderEventRepository:
    """Os avisos do provedor, guardados como chegaram (G:270-281). Só se
    inserem: o banco recusa UPDATE e DELETE."""

    def __init__(self, context: Context) -> None:
        self.session = context.db_session

    def create(
        self,
        provider_reference: str,
        event_type: str,
        outbox_id: int | None,
        raw_payload: dict,
        received_at: datetime,
    ) -> ProviderEvent:
        """Grava o aviso com uma chave nova. O `flush` manda o INSERT agora:
        a UNIQUE(provider_reference) dispara aqui, como `IntegrityError`, e
        não no commit."""
        provider_event = ProviderEvent()
        provider_event.provider_event_key = str(uuid4())
        provider_event.provider_reference = provider_reference
        provider_event.event_type = event_type
        provider_event.outbox_id = outbox_id
        provider_event.raw_payload = raw_payload
        provider_event.received_at = received_at

        self.session.add(provider_event)
        self.session.flush()

        return provider_event
