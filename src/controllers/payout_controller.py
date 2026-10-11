from datetime import datetime, timezone

from connectors import PartyConnector
from controllers.base_controller import BaseController
from controllers.posting_controller import PostingController
from dtos import LedgerTransactionDTO
from errors import LedgerAccountNotFound, OwnerNotActive, OwnerWithoutPixKey, PartyServiceUnavailable
from models import LedgerAccountType, LedgerEntry, LedgerTransactionType, PurposeCode
from repositories import LedgerAccountRepository, LedgerTransactionRepository

ENDPOINT = "POST /transfers/payout"

# O status que o motor guarda no registro de idempotência para o replay.
# O status da resposta HTTP sai do resource, e os dois são o 202 da RFC :150.
SUCCESS_STATUS = 202

# O Cadastro responde a parte com 200 ou diz que ela não existe com 404;
# qualquer outro status é Cadastro indisponível (D10).
PARTY_ANSWERS = (200, 404)
PARTY_ACTIVE = "active"


class PayoutController(BaseController):
    """O repasse por Pix: o dinheiro de uma conta com dono vai para a
    `clearing/TRANSIT` do cliente, e a outbox o despacha ao provedor
    (guia do Ledger §6, payout; D0006)."""

    def __init__(self) -> None:
        super().__init__(__name__)
        self.ledger_account_repository = LedgerAccountRepository(self.context)
        self.ledger_transaction_repository = LedgerTransactionRepository(self.context)
        self.party_connector = PartyConnector()
        # O 038/039 do Cadastro, lido antes do BEGIN e levantado pelo
        # `after_lock`, depois do passo 1: gravado na chave (D1).
        self.owner_error = None

    def create(self, payload: dict, idempotency_key: str, raw_body: bytes) -> dict:
        """Confere a chave, acha a origem, fecha a leitura e entrega as
        pernas ao motor (RN-01)."""
        PostingController.require_idempotency_key(idempotency_key)
        source = self._find_source(payload)

        # O commit expira o ORM: o que se lê da origem depois dele vem
        # destas variáveis, e não reabre transação na chamada externa.
        owner_party_key = source.owner_party_key
        client_key = source.client_key
        contract_key = source.contract_key

        # Fecha a leitura antes do Cadastro, sem escrita (D2).
        self.session.commit()

        # Conta sem dono não tem par para a TRANSIT: o motor dá o 008.
        if owner_party_key != "":
            self.owner_error = self._check_owner(owner_party_key)

        # A `clearing/TRANSIT` do cliente existe sempre (G:375-377). As contas
        # recarregam aqui, já na transação do motor.
        clearing = self.ledger_account_repository.find_by_natural_key(
            client_key, LedgerAccountType.CLEARING, PurposeCode.TRANSIT, "", ""
        )

        # O escopo da chave é o livro da origem, que é o debitado.
        idempotency = {
            "client_key": client_key,
            "endpoint": ENDPOINT,
            "key": idempotency_key,
            "raw_body": raw_body,
        }
        transaction = {
            "ledger_transaction_type": LedgerTransactionType.PAYOUT,
            "contract_key": contract_key,
            "period_reference": payload["period_reference"],
            "value_date": datetime.now(timezone.utc),
            "actor": payload["actor"],
            "reason": payload.get("reason"),
        }
        amount_in_cents = payload["amount_in_cents"]
        legs = [
            (source, LedgerEntry.DEBIT, amount_in_cents),
            (clearing, LedgerEntry.CREDIT, amount_in_cents),
        ]
        purpose_pairs = [(source, clearing)]

        posting_controller = PostingController()
        ledger_transaction_key = posting_controller.post(
            idempotency,
            transaction,
            legs,
            purpose_pairs,
            SUCCESS_STATUS,
            after_lock=self._raise_owner_error,
        )

        ledger_transaction = self.ledger_transaction_repository.get_by_key(ledger_transaction_key)

        return LedgerTransactionDTO.obj_to_dict(ledger_transaction)

    def _check_owner(self, owner_party_key: str):
        """O dono no Cadastro, sem transação aberta (RN-03; 01b :162-167).

        Sem resposta, ou outro status: 040 agora, antes do motor, e nada
        se grava. Não existe ou não está ativo: o 038; ativo sem chave Pix:
        o 039. Esses dois voltam para o motor gravar; o resto, None.
        """
        party_response = self.party_connector.get_party(owner_party_key)

        if party_response is None or party_response.status not in PARTY_ANSWERS:
            raise PartyServiceUnavailable()

        # Um 200 sem a parte no corpo não responde a pergunta: indisponível.
        if party_response.status == 200 and not isinstance(party_response.json, dict):
            raise PartyServiceUnavailable()

        if party_response.status == 404 or party_response.json.get("status") != PARTY_ACTIVE:
            return OwnerNotActive()

        if party_response.json.get("pix_key") is None:
            return OwnerWithoutPixKey()

        return None

    def _raise_owner_error(self) -> None:
        """Passo 5 do motor: o 038/039 guardado sai depois do registro da
        chave, e o motor o grava (D1; S05a RN-11)."""
        if self.owner_error is not None:
            raise self.owner_error

    def _find_source(self, payload: dict):
        """A conta de origem. Sem ela não há cliente, e sem cliente não há
        onde guardar a chave: o 018 sai antes do motor e não grava (D-01)."""
        source = self.ledger_account_repository.get_by_key(payload["source_account_key"])

        if source is None:
            raise LedgerAccountNotFound(payload["source_account_key"])

        return source
