from connectors import PartyConnector, ProviderConnector
from controllers.base_controller import BaseController
from models import Outbox, OutboxStatus
from repositories import OutboxRepository
from utils.request_context import get_request_id

DISPATCHER_ACTOR = "ledger-api:dispatcher"
PARTY_ACTIVE = "active"
REASON_MAX_LENGTH = 255


class OutboxController(BaseController):
    """O despacho da outbox ao provedor, depois do commit das pernas
    (D0006). Cada mudança de estado é um commit, e nenhuma chamada externa
    acontece com transação aberta."""

    def __init__(self) -> None:
        super().__init__(__name__)
        self.outbox_repository = OutboxRepository(self.context)
        self.party_connector = PartyConnector()
        self.provider_connector = ProviderConnector()

    def dispatch(self, outbox: Outbox, reason: str = "despacho inline") -> Outbox:
        """Uma tentativa da outbox (fatia 09 RN-07; fatia 14 RN-08), pela
        mesma reivindicação da fila: devolve a outbox relida. Pode voltar
        sem despachar, no estado atual, se outro a reivindicou antes."""
        # O commit expira o ORM: o `id` sai daqui antes.
        outbox_id = outbox.id

        self._attempt(outbox_id, reason)

        return self.outbox_repository.get_by_id(outbox_id)

    def dispatch_pending(self, limit: int) -> dict:
        """A varredura da fila (fatia 14, RN-09): as `pending` mais antigas,
        até `limit`, uma tentativa cada, com a mesma
        `dispatch_idempotency_key` (D0006 :71-73). Conta os desfechos desta
        chamada; a linha que outro reivindicou não conta.

        A fila é o acréscimo da fatia 14, com as quatro linhas:
        1. Princípio tocado: "commit na última linha" do controller.
        2. Por que não funciona sem: o `pending` de queda ou de falha nunca
           sairia da outbox (D0006 :53-55; CU-E3).
        3. A peça, e por que é a menor: uma tentativa por linha, dois commits
           por tentativa (a reivindicação e o desfecho) e o que fecha a
           leitura; a linha travada por outro é pulada; `dead` no limite.
        4. O que não faz: não tem backoff nem relógio, não estorna o `dead`,
           não segura trava durante a chamada de rede.
        """
        outbox_ids = self.outbox_repository.list_pending_ids(limit)
        self.session.commit()

        outcomes = {OutboxStatus.SENT: 0, OutboxStatus.PENDING: 0, OutboxStatus.DEAD: 0}
        for outbox_id in outbox_ids:
            outcome = self._attempt(outbox_id, "despacho pela fila")
            if outcome is not None:
                outcomes[outcome] = outcomes[outcome] + 1

        return outcomes

    def _attempt(self, outbox_id: int, reason: str) -> str | None:
        """Uma tentativa (fatia 14, RN-07): reivindica a linha; se outro a
        tem, ou ela saiu de `pending`, commit e None, sem despachar. Senão,
        `in_flight` e commit; relê a chave Pix no Cadastro; manda o Pix;
        `sent` se o provedor aceitou, senão volta a `pending` com mais uma
        tentativa; commit. Devolve o status final. Não repete."""
        outbox = self.outbox_repository.claim_pending(outbox_id)

        if outbox is None:
            self.session.commit()
            return None

        # O commit expira o ORM: o que a chamada externa usa sai daqui antes.
        beneficiary_party_key = outbox.beneficiary_party_key
        dispatch_idempotency_key = outbox.dispatch_idempotency_key
        amount_in_cents = outbox.payload["amount_in_cents"]
        trace_id = get_request_id()

        self.outbox_repository.change_status(outbox, OutboxStatus.IN_FLIGHT, DISPATCHER_ACTOR, reason, trace_id)
        self.session.commit()

        pix_key, failure_reason = self._read_pix_key(beneficiary_party_key)

        provider_reference = None
        if pix_key is not None:
            provider_reference, failure_reason = self._send_pix(dispatch_idempotency_key, pix_key, amount_in_cents)

        outbox = self.outbox_repository.get_by_id(outbox_id)

        if failure_reason is None:
            # A referência vem do provedor e pode ser longa: o motivo cabe
            # em 255 (G :264).
            sent_reason = f"provedor aceitou {provider_reference}"[:REASON_MAX_LENGTH]
            self.outbox_repository.change_status(outbox, OutboxStatus.SENT, DISPATCHER_ACTOR, sent_reason, trace_id)
        else:
            self.outbox_repository.change_status(
                outbox, OutboxStatus.PENDING, DISPATCHER_ACTOR, failure_reason, trace_id, increment_attempt=True
            )

        outcome = outbox.outbox_status.enumerator
        self.session.commit()

        return outcome

    def _read_pix_key(self, beneficiary_party_key: str) -> tuple:
        """A chave Pix vigente do dono (01b :331-332), ou (None, motivo):
        Cadastro fora, dono inativo ou sem chave são tentativa falha (D6)."""
        party_response = self.party_connector.get_party(beneficiary_party_key)

        if party_response is None or party_response.status not in (200, 404):
            return None, "cadastro indisponível"

        if party_response.status == 200 and not isinstance(party_response.json, dict):
            return None, "cadastro indisponível"

        if party_response.status == 404 or party_response.json.get("status") != PARTY_ACTIVE:
            return None, "dono não está ativo no cadastro"

        pix_key = party_response.json.get("pix_key")
        if pix_key is None:
            return None, "dono sem chave Pix"

        return pix_key, None

    def _send_pix(self, dispatch_idempotency_key: str, pix_key: str, amount_in_cents: int) -> tuple:
        """(referência do provedor, None) no `2xx`; (None, motivo) sem
        resposta ou com outro status (D9)."""
        provider_response = self.provider_connector.send_pix(dispatch_idempotency_key, pix_key, amount_in_cents)

        if provider_response is None:
            return None, "timeout"

        if not 200 <= provider_response.status < 300:
            return None, f"provedor {provider_response.status}"

        provider_reference = None
        if isinstance(provider_response.json, dict):
            provider_reference = provider_response.json.get("provider_reference")

        return provider_reference, None
