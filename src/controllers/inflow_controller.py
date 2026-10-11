from datetime import datetime, timezone

from constants import PLATFORM_CLIENT_KEY
from controllers.base_controller import BaseController
from controllers.posting_controller import PostingController
from dtos import LedgerTransactionDTO
from errors import ClientBooksNotFound, ContractNotProvisioned, InvalidSchema
from errors import LedgerAccountNotFound
from models import LedgerAccountType, LedgerEntry, LedgerTransactionType, PurposeCode
from repositories import LedgerAccountRepository, LedgerTransactionRepository

ENDPOINT = "POST /transfers/inflow"

# O status que o motor guarda no registro de idempotência para o replay.
# O status da resposta HTTP sai do resource, e os dois são o 201 da RFC :147.
SUCCESS_STATUS = 201


class InflowController(BaseController):
    """A entrada por Pix: o dinheiro que chega de fora para a COLLECTION de
    um contrato (guia do Ledger §6, inflow)."""

    def __init__(self) -> None:
        super().__init__(__name__)
        self.ledger_account_repository = LedgerAccountRepository(self.context)
        self.ledger_transaction_repository = LedgerTransactionRepository(self.context)

    def create(self, payload: dict, idempotency_key: str, raw_body: bytes) -> dict:
        """Confere a chave, acha as duas contas e a data-valor, nesta ordem
        (RN-02), e entrega as pernas ao motor."""
        PostingController.require_idempotency_key(idempotency_key)

        # O pagamento com a carteira: o schema já garantiu que veio sem
        # pagador e sem `end_to_end_id` (fatia 12, RN-06).
        if "source_wallet_key" in payload:
            return self._create_from_wallet(payload, idempotency_key, raw_body)

        # O depósito por Pix na carteira: sem contrato nem competência
        # (fatia 12, RN-07).
        if "wallet_key" in payload:
            return self._create_deposit(payload, idempotency_key, raw_body)

        if "client_key" in payload:
            self._suspense_destination(payload)

        collection, external = self._find_accounts(payload)
        value_date = self._value_date(payload)

        # O escopo da chave é o livro debitado: o `external` do cliente.
        idempotency = {
            "client_key": external.client_key,
            "endpoint": ENDPOINT,
            "key": idempotency_key,
            "raw_body": raw_body,
        }
        transaction = {
            "ledger_transaction_type": LedgerTransactionType.INFLOW,
            "contract_key": payload["contract_key"],
            "period_reference": payload["period_reference"],
            "payer_party_key": payload["payer_party_key"],
            "end_to_end_id": payload["end_to_end_id"],
            "value_date": value_date,
            "actor": payload["actor"],
            "reason": payload.get("reason"),
        }
        amount_in_cents = payload["amount_in_cents"]
        legs = [
            (external, LedgerEntry.DEBIT, amount_in_cents),
            (collection, LedgerEntry.CREDIT, amount_in_cents),
        ]
        purpose_pairs = [(external, collection)]

        posting_controller = PostingController()
        ledger_transaction_key = posting_controller.post(
            idempotency, transaction, legs, purpose_pairs, SUCCESS_STATUS
        )

        ledger_transaction = self.ledger_transaction_repository.get_by_key(ledger_transaction_key)

        return LedgerTransactionDTO.obj_to_dict(ledger_transaction)

    def _create_from_wallet(self, payload: dict, idempotency_key: str, raw_body: bytes) -> dict:
        """O aluguel pago com a carteira: quatro pernas em dois livros
        (fatia 12, RN-06; remodelagem/10 :109-112). A carteira sai do livro
        da plataforma e entra na COLLECTION, no livro do cliente; o par
        `external` leva o dinheiro de um livro ao outro.

        Só a carteira trava (o `external` é ativo), e o saldo dela é somado
        depois da trava: o 009 é o do motor. Sem carteira — ou com uma
        conta que não é `own/WALLET` —, o 018 sai pelo motor, com pernas
        vazias, e fica gravado na chave (RN-04a).
        """
        collection, external = self._find_accounts(payload)
        wallet = self._find_wallet(payload["source_wallet_key"])
        value_date = self._value_date(payload)

        # O escopo da chave é o livro do cliente, o do `external` debitado.
        idempotency = {
            "client_key": external.client_key,
            "endpoint": ENDPOINT,
            "key": idempotency_key,
            "raw_body": raw_body,
        }
        transaction = {
            "ledger_transaction_type": LedgerTransactionType.INFLOW,
            "contract_key": payload["contract_key"],
            "period_reference": payload["period_reference"],
            "value_date": value_date,
            "actor": payload["actor"],
            "reason": payload.get("reason"),
        }

        posting_controller = PostingController()

        if wallet is None:
            posting_controller.post(
                idempotency, transaction, [], [], SUCCESS_STATUS, after_lock=self._raise_wallet_not_found
            )

        # Quem paga é o dono da carteira (G:407; RFC :400).
        transaction["payer_party_key"] = wallet.owner_party_key

        platform_cash = self.ledger_account_repository.find_by_natural_key(
            PLATFORM_CLIENT_KEY, LedgerAccountType.EXTERNAL, PurposeCode.CASH, "", ""
        )

        amount_in_cents = payload["amount_in_cents"]
        legs = [
            (wallet, LedgerEntry.DEBIT, amount_in_cents),
            (collection, LedgerEntry.CREDIT, amount_in_cents),
            (external, LedgerEntry.DEBIT, amount_in_cents),
            (platform_cash, LedgerEntry.CREDIT, amount_in_cents),
        ]
        # As pernas `external` não consultam a `purpose_rule` (G:354).
        purpose_pairs = [(wallet, collection)]

        ledger_transaction_key = posting_controller.post(
            idempotency, transaction, legs, purpose_pairs, SUCCESS_STATUS
        )

        ledger_transaction = self.ledger_transaction_repository.get_by_key(ledger_transaction_key)

        return LedgerTransactionDTO.obj_to_dict(ledger_transaction)

    def _create_deposit(self, payload: dict, idempotency_key: str, raw_body: bytes) -> dict:
        """O depósito por Pix: o dinheiro que chega de fora para a carteira,
        tudo no livro da plataforma (fatia 12, RN-07; G:405-409).

        O escopo da chave é o livro debitado, o da plataforma, conhecido
        mesmo sem conta. Sem carteira — ou com uma conta que não é
        `own/WALLET` —, o 018 sai pelo motor, com pernas vazias, e fica
        gravado na chave (RN-04a).
        """
        wallet = self._find_wallet(payload["wallet_key"])
        value_date = self._value_date(payload)

        idempotency = {
            "client_key": PLATFORM_CLIENT_KEY,
            "endpoint": ENDPOINT,
            "key": idempotency_key,
            "raw_body": raw_body,
        }
        transaction = {
            "ledger_transaction_type": LedgerTransactionType.INFLOW,
            "contract_key": "",
            "period_reference": "",
            "end_to_end_id": payload["end_to_end_id"],
            "value_date": value_date,
            "actor": payload["actor"],
            "reason": payload.get("reason"),
        }

        posting_controller = PostingController()

        if wallet is None:
            posting_controller.post(
                idempotency, transaction, [], [], SUCCESS_STATUS, after_lock=self._raise_wallet_not_found
            )

        # Quem deposita é o dono da carteira (G:407).
        transaction["payer_party_key"] = wallet.owner_party_key

        platform_cash = self.ledger_account_repository.find_by_natural_key(
            PLATFORM_CLIENT_KEY, LedgerAccountType.EXTERNAL, PurposeCode.CASH, "", ""
        )

        amount_in_cents = payload["amount_in_cents"]
        legs = [
            (platform_cash, LedgerEntry.DEBIT, amount_in_cents),
            (wallet, LedgerEntry.CREDIT, amount_in_cents),
        ]
        purpose_pairs = [(platform_cash, wallet)]

        ledger_transaction_key = posting_controller.post(
            idempotency, transaction, legs, purpose_pairs, SUCCESS_STATUS
        )

        ledger_transaction = self.ledger_transaction_repository.get_by_key(ledger_transaction_key)

        return LedgerTransactionDTO.obj_to_dict(ledger_transaction)

    def _find_wallet(self, source_wallet_key: str):
        """A carteira pela chave. Conta que não é `own/WALLET` é carteira
        inexistente (fatia 12, D3): None."""
        wallet = self.ledger_account_repository.get_by_key(source_wallet_key)

        if wallet is None:
            return None

        if wallet.ledger_account_type.enumerator != LedgerAccountType.OWN:
            return None

        if wallet.purpose_code.enumerator != PurposeCode.WALLET:
            return None

        return wallet

    @staticmethod
    def _raise_wallet_not_found() -> None:
        """Passo 5 do motor, sem pernas: o 018 sai depois do registro da
        chave, e o motor o grava (fatia 12, RN-04a; S05a D-03)."""
        raise LedgerAccountNotFound()

    def _find_accounts(self, payload: dict) -> tuple:
        """A COLLECTION do contrato e o `external/CASH` do mesmo cliente.

        Sem COLLECTION não há cliente, e sem cliente não há onde guardar a
        chave de idempotência: o 035 sai antes do motor e não grava nada.
        O `external` existe sempre que há contrato (provisionamento, S04 RN-07).
        """
        collection = self.ledger_account_repository.find_contract_account(
            payload["contract_key"], PurposeCode.COLLECTION
        )

        if collection is None:
            raise ContractNotProvisioned(payload["contract_key"])

        external = self.ledger_account_repository.find_by_natural_key(
            collection.client_key, LedgerAccountType.EXTERNAL, PurposeCode.CASH, "", ""
        )

        return collection, external

    def _suspense_destination(self, payload: dict) -> tuple:
        """O `external/CASH` e o `suspense/UNALLOCATED` do `client_key` do
        corpo: o dinheiro que chegou sem dizer de qual contrato é (CU-B2).

        Os cinco livros nascem juntos (G:376); falta um só por bug. Sem um
        deles, o 019 sai antes do motor e não grava nada (05b D-01).
        """
        client_key = payload["client_key"]
        external = self.ledger_account_repository.find_by_natural_key(
            client_key, LedgerAccountType.EXTERNAL, PurposeCode.CASH, "", ""
        )
        suspense = self.ledger_account_repository.find_by_natural_key(
            client_key, LedgerAccountType.SUSPENSE, PurposeCode.UNALLOCATED, "", ""
        )

        if external is None or suspense is None:
            raise ClientBooksNotFound(client_key)

        return external, suspense

    def _value_date(self, payload: dict) -> datetime:
        """A data-valor do corpo, ou o agora quando ela não veio (CU-J10).

        O `pattern` do schema conta dígitos, não dias: "2026-02-30" passa por
        ele e morre aqui, como pedido malformado (400).
        """
        value_date = payload.get("value_date")

        if value_date is None:
            return datetime.now(timezone.utc)

        try:
            return datetime.fromisoformat(value_date)
        except ValueError:
            raise InvalidSchema(f"value_date {value_date} is not a real date")
