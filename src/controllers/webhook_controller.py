from datetime import datetime

from sqlalchemy.exc import OperationalError

from controllers.base_controller import BaseController
from errors import InvalidSchema, LockTimeout, OutboxNotFound
from repositories import OutboxRepository

# O SQLSTATE do Postgres para "lock_not_available": a trava não veio dentro
# do lock_timeout.
LOCK_NOT_AVAILABLE = "55P03"


class WebhookController(BaseController):
    """O aviso do provedor sobre um repasse já enviado: a liquidação
    confirmada ou a falha (guia do Ledger §6; RFC :154)."""

    def __init__(self) -> None:
        super().__init__(__name__)
        self.outbox_repository = OutboxRepository(self.context)

    def handle(self, payload: dict, raw_body: bytes) -> None:
        """Uma transação (RN-01): a data-valor, a outbox travada."""
        self._value_date(payload)
        self._lock_outbox(payload["outbox_key"])

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
