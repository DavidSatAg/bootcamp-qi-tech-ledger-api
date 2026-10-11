from controllers.base_controller import BaseController
from errors import InvalidSchema

IDEMPOTENCY_KEY_MAX_LENGTH = 255


class PostingController(BaseController):
    """O motor de postagem: o único caminho por onde o dinheiro se move
    (guia do Ledger §5; D0001)."""

    def __init__(self) -> None:
        super().__init__(__name__)

    @staticmethod
    def require_idempotency_key(idempotency_key: str) -> None:
        """Toda rota que move dinheiro exige a `Idempotency-Key` (RFC :107-110).

        Faltar a chave é pedido malformado, como o schema: 400, e nada se
        grava (D0003 :62-63).
        """
        if not idempotency_key:
            raise InvalidSchema("Idempotency-Key header is required")

        if len(idempotency_key) > IDEMPOTENCY_KEY_MAX_LENGTH:
            raise InvalidSchema(
                f"Idempotency-Key header is longer than {IDEMPOTENCY_KEY_MAX_LENGTH} characters"
            )
