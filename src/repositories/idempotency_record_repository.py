from database import Context
from models import IdempotencyRecord


class IdempotencyRecordRepository:
    """O registro de cada `Idempotency-Key`: a impressão do pedido e a resposta (D0003)."""

    def __init__(self, context: Context) -> None:
        self.session = context.db_session

    def create(
        self,
        client_key: str,
        endpoint: str,
        idempotency_key: str,
        request_fingerprint: str,
        expires_at,
    ) -> IdempotencyRecord:
        """Grava o registro com a resposta provisória (status 0, sem chaves).

        O `flush` manda o INSERT agora: é nele que a UNIQUE do escopo
        (client_key, endpoint, idempotency_key) espera pela outra transação
        com a mesma chave e, quando ela commita, dispara.
        """
        idempotency_record = IdempotencyRecord()
        idempotency_record.client_key = client_key
        idempotency_record.endpoint = endpoint
        idempotency_record.idempotency_key = idempotency_key
        idempotency_record.request_fingerprint = request_fingerprint
        idempotency_record.response_status = 0
        idempotency_record.response_keys = []
        idempotency_record.expires_at = expires_at

        self.session.add(idempotency_record)
        self.session.flush()

        return idempotency_record

    def set_response(self, idempotency_record: IdempotencyRecord, response_status: int, response_keys: list) -> None:
        idempotency_record.response_status = response_status
        idempotency_record.response_keys = response_keys

        self.session.flush()

    def get(self, client_key: str, endpoint: str, idempotency_key: str) -> IdempotencyRecord:
        """O registro da chave, ou None, sem trava: só uma espiada antes da
        chamada externa (fatia 09, RN-02). Quem decide é o INSERT do motor."""
        return (
            self.session.query(IdempotencyRecord)
            .filter(
                IdempotencyRecord.client_key == client_key,
                IdempotencyRecord.endpoint == endpoint,
                IdempotencyRecord.idempotency_key == idempotency_key,
            )
            .first()
        )

    def get_for_update(self, client_key: str, endpoint: str, idempotency_key: str) -> IdempotencyRecord:
        """O registro que colidiu, travado até o fim da transação: quem chega
        com a mesma chave espera aqui, e não lê uma resposta pela metade."""
        return (
            self.session.query(IdempotencyRecord)
            .filter(
                IdempotencyRecord.client_key == client_key,
                IdempotencyRecord.endpoint == endpoint,
                IdempotencyRecord.idempotency_key == idempotency_key,
            )
            .with_for_update()
            .one()
        )

    def renew(self, idempotency_record: IdempotencyRecord, request_fingerprint: str, expires_at) -> None:
        """A chave venceu: o registro passa a ser do pedido novo, com a
        resposta provisória de novo (D0003 :54)."""
        idempotency_record.request_fingerprint = request_fingerprint
        idempotency_record.response_status = 0
        idempotency_record.response_keys = []
        idempotency_record.expires_at = expires_at

        self.session.flush()
