from datetime import datetime, timezone

from connectors import PartyConnector
from constants import PLATFORM_CLIENT_KEY
from controllers.base_controller import BaseController
from controllers.outbox_controller import OutboxController
from controllers.posting_controller import PostingController
from dtos import LedgerTransactionDTO, OutboxDTO
from errors import LedgerAccountNotFound, OwnerNotActive, OwnerWithoutPixKey, PartyServiceUnavailable
from errors import OwnerWithoutWallet
from models import LedgerAccountType, LedgerEntry, LedgerTransactionType, PurposeCode
from repositories import (
    IdempotencyRecordRepository,
    LedgerAccountRepository,
    LedgerTransactionRepository,
    OutboxRepository,
)
from utils.request_context import get_request_id

ENDPOINT = "POST /transfers/payout"

# O status que o motor guarda no registro de idempotência para o replay.
# O status da resposta HTTP sai do resource, e os dois são o 202 da RFC :150.
SUCCESS_STATUS = 202

# O Cadastro responde a parte com 200 ou diz que ela não existe com 404;
# qualquer outro status é Cadastro indisponível (D10).
PARTY_ANSWERS = (200, 404)
PARTY_ACTIVE = "active"

# O repasse para a carteira não despacha nada: o dinheiro já chegou, e a
# resposta é 201 (RFC :150; fatia 12, RN-04).
WALLET_SUCCESS_STATUS = 201
WALLET_DESTINATION = "wallet"


class PayoutController(BaseController):
    """O repasse por Pix: o dinheiro de uma conta com dono vai para a
    `clearing/TRANSIT` do cliente, e a outbox o despacha ao provedor
    (guia do Ledger §6, payout; D0006)."""

    def __init__(self) -> None:
        super().__init__(__name__)
        self.ledger_account_repository = LedgerAccountRepository(self.context)
        self.ledger_transaction_repository = LedgerTransactionRepository(self.context)
        self.outbox_repository = OutboxRepository(self.context)
        self.idempotency_record_repository = IdempotencyRecordRepository(self.context)
        self.party_connector = PartyConnector()
        # O 038/039 do Cadastro, lido antes do BEGIN e levantado pelo
        # `after_lock`, depois do passo 1: gravado na chave (D1).
        self.owner_error = None
        # A outbox que ESTA requisição gravou; vazia no replay (RN-06, D4).
        self.outbox = None

    def create(self, payload: dict, idempotency_key: str, raw_body: bytes) -> dict:
        """Confere a chave, acha a origem, fecha a leitura, confere o dono no
        Cadastro e entrega as pernas ao motor (RN-01); depois do commit
        dele, despacha a outbox que gravou (RN-07)."""
        PostingController.require_idempotency_key(idempotency_key)
        source = self._find_source(payload)

        # O commit expira o ORM: o que se lê da origem depois dele vem
        # destas variáveis, e não reabre transação na chamada externa.
        owner_party_key = source.owner_party_key
        client_key = source.client_key
        contract_key = source.contract_key
        # Para a carteira do dono, antes do Cadastro e do commit D2: o
        # Ledger só consulta o Cadastro no Pix e na abertura (fatia 12,
        # RN-03). Sem dono, segue o Pix, que dá o 008 no motor.
        if payload["destination"] == WALLET_DESTINATION and owner_party_key != "":
            return self._create_to_wallet(payload, idempotency_key, raw_body, source)

        replay = self._is_replay(client_key, idempotency_key)

        # Fecha a leitura antes do Cadastro, sem escrita (D2).
        self.session.commit()

        # Conta sem dono não tem par para a TRANSIT: o motor dá o 008. No
        # replay, o motor responde o que gravou, e o Cadastro seria inútil.
        if owner_party_key != "" and not replay:
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
            after_write=lambda ledger_transaction: self._create_outbox(ledger_transaction, owner_party_key, payload),
        )

        # Só despacha a outbox criada agora: o replay não reenvia (D4).
        outbox = None
        if self.outbox is not None:
            outbox_controller = OutboxController()
            outbox = outbox_controller.dispatch(self.outbox)

        ledger_transaction = self.ledger_transaction_repository.get_by_key(ledger_transaction_key)

        if outbox is None:
            outbox = self.outbox_repository.get_by_transaction(ledger_transaction.id)

        payout = LedgerTransactionDTO.obj_to_dict(ledger_transaction)
        payout["outbox"] = OutboxDTO.obj_to_dict(outbox)

        return payout

    def _create_to_wallet(self, payload: dict, idempotency_key: str, raw_body: bytes, source) -> dict:
        """O repasse para a carteira do dono: quatro pernas em dois livros
        (fatia 12, RN-04; remodelagem/10 :73-76). A origem sai do livro do
        cliente e entra na carteira, no livro da plataforma; o par `external`
        leva o dinheiro de um livro ao outro, e cada livro fecha em zero.

        Sem carteira, o 041 sai pelo motor, com pernas vazias, e fica
        gravado na chave (RN-04a): a repetição devolve o mesmo 041.
        """
        client_key = source.client_key
        idempotency = {
            "client_key": client_key,
            "endpoint": ENDPOINT,
            "key": idempotency_key,
            "raw_body": raw_body,
        }
        transaction = {
            "ledger_transaction_type": LedgerTransactionType.PAYOUT,
            "contract_key": source.contract_key,
            "period_reference": payload["period_reference"],
            "value_date": datetime.now(timezone.utc),
            "actor": payload["actor"],
            "reason": payload.get("reason"),
        }

        wallet = self.ledger_account_repository.find_by_natural_key(
            PLATFORM_CLIENT_KEY, LedgerAccountType.OWN, PurposeCode.WALLET, "", source.owner_party_key
        )

        posting_controller = PostingController()

        if wallet is None:
            posting_controller.post(
                idempotency,
                transaction,
                [],
                [],
                WALLET_SUCCESS_STATUS,
                after_lock=self._raise_owner_without_wallet,
            )

        platform_cash = self.ledger_account_repository.find_by_natural_key(
            PLATFORM_CLIENT_KEY, LedgerAccountType.EXTERNAL, PurposeCode.CASH, "", ""
        )
        client_cash = self.ledger_account_repository.find_by_natural_key(
            client_key, LedgerAccountType.EXTERNAL, PurposeCode.CASH, "", ""
        )

        amount_in_cents = payload["amount_in_cents"]
        legs = [
            (source, LedgerEntry.DEBIT, amount_in_cents),
            (wallet, LedgerEntry.CREDIT, amount_in_cents),
            (platform_cash, LedgerEntry.DEBIT, amount_in_cents),
            (client_cash, LedgerEntry.CREDIT, amount_in_cents),
        ]
        # As pernas `external` não consultam a `purpose_rule` (G:354).
        purpose_pairs = [(source, wallet)]

        ledger_transaction_key = posting_controller.post(
            idempotency,
            transaction,
            legs,
            purpose_pairs,
            WALLET_SUCCESS_STATUS,
        )

        ledger_transaction = self.ledger_transaction_repository.get_by_key(ledger_transaction_key)

        payout = LedgerTransactionDTO.obj_to_dict(ledger_transaction)
        payout["outbox"] = None

        return payout

    @staticmethod
    def _raise_owner_without_wallet() -> None:
        """Passo 5 do motor, sem pernas: o 041 sai depois do registro da
        chave, e o motor o grava (fatia 12, RN-04a)."""
        raise OwnerWithoutWallet()

    def _create_outbox(self, ledger_transaction, owner_party_key: str, payload: dict) -> None:
        """Depois do passo 8, no SAVEPOINT do motor: a outbox entra no mesmo
        commit das pernas (RN-06; D0006 :44-46). O payload leva só valor e
        referência: a chave Pix é lida do Cadastro a cada envio."""
        ledger_transaction_key = ledger_transaction.ledger_transaction_key

        self.outbox = self.outbox_repository.create(
            ledger_transaction,
            beneficiary_party_key=owner_party_key,
            dispatch_idempotency_key=f"{ledger_transaction_key}-outbox-1",
            payload={
                "amount_in_cents": payload["amount_in_cents"],
                "ledger_transaction_key": ledger_transaction_key,
            },
            actor=payload["actor"],
            reason=payload.get("reason"),
            trace_id=get_request_id(),
        )

    def _is_replay(self, client_key: str, idempotency_key: str) -> bool:
        """Se a chave já tem registro vivo, com qualquer impressão (RN-02):
        aí o motor responde o replay ou o 010 antes do `after_lock`, e o
        Cadastro não pode trocar essa resposta por um 503 ou um 038."""
        idempotency_record = self.idempotency_record_repository.get(client_key, ENDPOINT, idempotency_key)

        if idempotency_record is None:
            return False

        return idempotency_record.expires_at > datetime.now(timezone.utc)

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
