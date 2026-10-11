from models import Outbox


class OutboxDTO:
    """Traduz a outbox do repasse no JSON que a API devolve."""

    @staticmethod
    def obj_to_dict(outbox: Outbox) -> dict:
        dto = dict()
        dto["outbox_key"] = outbox.outbox_key
        dto["outbox_status"] = outbox.outbox_status.enumerator
        dto["beneficiary_party_key"] = outbox.beneficiary_party_key
        dto["dispatch_idempotency_key"] = outbox.dispatch_idempotency_key
        dto["attempt_count"] = outbox.attempt_count

        return dto
