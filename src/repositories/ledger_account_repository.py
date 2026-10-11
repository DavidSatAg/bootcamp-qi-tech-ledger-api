from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import case, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import aliased

from constants import LOCK_TIMEOUT
from database import Context
from models import (
    LedgerAccount,
    LedgerAccountStatus,
    LedgerAccountStatusEvent,
    LedgerAccountType,
    LedgerEntry,
    PurposeCode,
)
from models import LedgerTransaction, LedgerTransactionType


class LedgerAccountRepository:
    """As contas do ledger. Só aqui existe query sobre elas."""

    def __init__(self, context: Context) -> None:
        self.session = context.db_session

    def get_by_key(self, ledger_account_key: str) -> LedgerAccount:
        return (
            self.session.query(LedgerAccount)
            .filter(LedgerAccount.ledger_account_key == ledger_account_key)
            .first()
        )

    def get_balance(self, ledger_account: LedgerAccount) -> int:
        """O saldo, somado dos lançamentos: nunca uma coluna.

        D - C nas contas do lado `asset`; C - D nas demais. Sem trava:
        quem lê não disputa linha com ninguém.
        """
        debit_minus_credit = case(
            (LedgerEntry.direction == LedgerEntry.DEBIT, LedgerEntry.amount_in_cents),
            else_=-LedgerEntry.amount_in_cents,
        )

        total = (
            self.session.query(func.coalesce(func.sum(debit_minus_credit), 0))
            .filter(LedgerEntry.ledger_account_id == ledger_account.id)
            .scalar()
        )

        if ledger_account.ledger_account_type.side != LedgerAccountType.ASSET:
            total = -total

        return int(total)

    def find_by_natural_key(
        self,
        client_key: str,
        ledger_account_type: str,
        purpose_code: str,
        contract_key: str,
        owner_party_key: str,
    ) -> LedgerAccount:
        """A conta pela chave única (client_key, tipo, propósito, contrato, dono).

        É por ela que o provisionamento decide entre reusar e criar.
        """
        return (
            self.session.query(LedgerAccount)
            .join(LedgerAccount.ledger_account_type)
            .join(LedgerAccount.purpose_code)
            .filter(
                LedgerAccount.client_key == client_key,
                LedgerAccountType.enumerator == ledger_account_type,
                PurposeCode.enumerator == purpose_code,
                LedgerAccount.contract_key == contract_key,
                LedgerAccount.owner_party_key == owner_party_key,
            )
            .first()
        )

    def create(
        self,
        client_key: str,
        ledger_account_type: str,
        purpose_code: str,
        contract_key: str,
        owner_party_key: str,
        owner_role: str,
        actor: str,
        reason: str,
        trace_id: str,
    ) -> LedgerAccount:
        """Cria a conta já ativa, com o evento de nascimento null -> active.

        O `flush` manda o INSERT agora, sem commit: o `id` passa a existir
        para quem aponta para a conta, e a próxima busca da mesma
        requisição já a enxerga.
        """
        active_status = self.get_status(LedgerAccountStatus.ACTIVE)

        ledger_account = LedgerAccount()
        ledger_account.ledger_account_key = str(uuid4())
        ledger_account.client_key = client_key
        ledger_account.contract_key = contract_key
        ledger_account.ledger_account_type = self.get_type(ledger_account_type)
        ledger_account.ledger_account_status = active_status
        ledger_account.purpose_code = self.get_purpose_code(purpose_code)
        ledger_account.owner_party_key = owner_party_key
        ledger_account.owner_role = owner_role

        status_event = LedgerAccountStatusEvent()
        status_event.from_status = None
        status_event.to_status = active_status
        status_event.actor = actor
        status_event.reason = reason
        status_event.trace_id = trace_id
        status_event.event_datetime = datetime.now(timezone.utc)

        ledger_account.status_events.append(status_event)

        self.session.add(ledger_account)
        self.session.flush()

        return ledger_account

    def change_status(
        self,
        ledger_account: LedgerAccount,
        status_enumerator: str,
        actor: str,
        reason: str,
        trace_id: str,
    ) -> LedgerAccount:
        """Leva a conta ao novo status, com o evento atual -> novo.

        O `flush` manda o UPDATE e o INSERT agora, sem commit.
        """
        new_status = self.get_status(status_enumerator)

        status_event = LedgerAccountStatusEvent()
        status_event.from_status = ledger_account.ledger_account_status
        status_event.to_status = new_status
        status_event.actor = actor
        status_event.reason = reason
        status_event.trace_id = trace_id
        status_event.event_datetime = datetime.now(timezone.utc)

        ledger_account.ledger_account_status = new_status
        ledger_account.status_events.append(status_event)

        self.session.flush()

        return ledger_account

    def list_page(self, limit: int, offset: int, filters: dict) -> list:
        """A página, estreitada pelo filtro que veio (o schema garante um só).

        Ordenada por `id`, que é a ordem dos índices por cliente: sem
        ordem, `limit` e `offset` podem repetir ou pular linha entre
        páginas. Pede um a mais que o limite para saber se há próxima.
        """
        query = self.session.query(LedgerAccount)

        client_key = filters.get("client_key")
        if client_key is not None:
            query = query.filter(LedgerAccount.client_key == client_key)

        contract_key = filters.get("contract_key")
        if contract_key is not None:
            query = query.filter(LedgerAccount.contract_key == contract_key)

        owner_party_key = filters.get("owner_party_key")
        if owner_party_key is not None:
            query = query.filter(LedgerAccount.owner_party_key == owner_party_key)

        query = query.order_by(LedgerAccount.id)

        return query.limit(limit + 1).offset(offset).all()

    def get_type(self, enumerator: str) -> LedgerAccountType:
        return self.session.query(LedgerAccountType).filter(LedgerAccountType.enumerator == enumerator).one()

    def get_status(self, enumerator: str) -> LedgerAccountStatus:
        return self.session.query(LedgerAccountStatus).filter(LedgerAccountStatus.enumerator == enumerator).one()

    def get_purpose_code(self, enumerator: str) -> PurposeCode:
        return self.session.query(PurposeCode).filter(PurposeCode.enumerator == enumerator).first()

    def lock_contract_accounts(self, contract_key: str) -> list | None:
        """Trava as contas do contrato, em ordem crescente de id, e as devolve.

        `FOR UPDATE`, e não `FOR NO KEY UPDATE`: só ele conflita com o
        `FOR KEY SHARE` que a FK do lançamento pega na conta. O
        `populate_existing` relê o status do banco, por cima do que a
        sessão já tivesse. A espera vai até o `lock_timeout`; estourou,
        devolve None.
        """
        try:
            self.session.execute(select(func.set_config("lock_timeout", LOCK_TIMEOUT, True)))

            return (
                self.session.query(LedgerAccount)
                .filter(LedgerAccount.contract_key == contract_key)
                .order_by(LedgerAccount.id)
                .with_for_update()
                .populate_existing()
                .all()
            )
        except OperationalError as error:
            if getattr(error.orig, "pgcode", None) == "55P03":
                return None
            raise

    def get_statuses(self, ledger_account_ids: list) -> dict:
        """{id: status} das contas, lido agora do banco.

        Colunas, e não entidades: a sessão devolveria o status que já
        guardava das contas, e não o que outra transação acabou de commitar.
        """
        rows = (
            self.session.query(LedgerAccount.id, LedgerAccountStatus.enumerator)
            .join(LedgerAccountStatus, LedgerAccount.ledger_account_status_id == LedgerAccountStatus.id)
            .filter(LedgerAccount.id.in_(ledger_account_ids))
            .all()
        )

        return {ledger_account_id: enumerator for ledger_account_id, enumerator in rows}

    def find_contract_account(self, contract_key: str, purpose_code: str) -> LedgerAccount:
        """A conta do contrato com esse propósito (a COLLECTION, na entrada),
        ou None se o contrato não foi provisionado."""
        return (
            self.session.query(LedgerAccount)
            .join(LedgerAccount.purpose_code)
            .filter(
                LedgerAccount.contract_key == contract_key,
                PurposeCode.enumerator == purpose_code,
            )
            .first()
        )

    def list_negative_without_reversal(self, client_key: str | None) -> list:
        """As contas com saldo orientado negativo e nenhum lançamento em
        transação `reversal`: [(LedgerAccount, saldo)], por `id` (D0005).
        Negativo com estorno no histórico é esperado, não suspeito.
        Com `client_key`, só o livro dele. Sem trava.
        """
        debit_minus_credit = case(
            (LedgerEntry.direction == LedgerEntry.DEBIT, LedgerEntry.amount_in_cents),
            else_=-LedgerEntry.amount_in_cents,
        )
        oriented = case((LedgerAccountType.side == LedgerAccountType.ASSET, debit_minus_credit), else_=-debit_minus_credit)
        balance = func.sum(oriented)

        reversal_entry = aliased(LedgerEntry)
        has_reversal = (
            self.session.query(reversal_entry.id)
            .join(LedgerTransaction, reversal_entry.ledger_transaction_id == LedgerTransaction.id)
            .join(LedgerTransactionType, LedgerTransaction.ledger_transaction_type_id == LedgerTransactionType.id)
            .filter(
                reversal_entry.ledger_account_id == LedgerAccount.id,
                LedgerTransactionType.enumerator == LedgerTransactionType.REVERSAL,
            )
            .exists()
        )

        query = (
            self.session.query(LedgerAccount, balance)
            .join(LedgerEntry, LedgerEntry.ledger_account_id == LedgerAccount.id)
            .join(LedgerAccountType, LedgerAccount.ledger_account_type_id == LedgerAccountType.id)
            .filter(~has_reversal)
        )

        if client_key is not None:
            query = query.filter(LedgerAccount.client_key == client_key)

        rows = query.group_by(LedgerAccount.id).having(balance < 0).order_by(LedgerAccount.id).all()

        return [(ledger_account, int(balance_in_cents)) for ledger_account, balance_in_cents in rows]

    def lock_for_update(self, ledger_account_ids: list, lock_timeout: str) -> list:
        """Trava as contas pedidas, em `id` crescente, esperando no máximo
        `lock_timeout` (passo 4 do motor; D0007 :35-55). Devolve os `id`s.

        O Postgres não liga parâmetro em `SET LOCAL`: o `set_config(..., true)`
        é o mesmo `SET LOCAL`, e vale até o fim da transação (ou do SAVEPOINT
        que o desfizer). Estourar o tempo sobe como está (`55P03`): quem o
        traduz é o motor. As travas soltam no commit ou no rollback.
        """
        self.session.query(func.set_config("lock_timeout", lock_timeout, True)).scalar()

        rows = (
            self.session.query(LedgerAccount.id)
            .filter(LedgerAccount.id.in_(ledger_account_ids))
            .order_by(LedgerAccount.id)
            .with_for_update()
            .all()
        )

        return [ledger_account_id for (ledger_account_id,) in rows]

    def lock_for_statement(self, ledger_account: LedgerAccount) -> datetime:
        """Trava a linha da conta e devolve o corte do extrato (RN-06, A9).

        O corte é o `clock_timestamp()` lido DEPOIS da trava: com o `NOW()`
        do início da transação, quem esperou na trava teria um corte anterior
        ao do extrato que esperou, e a cadeia poderia bifurcar. A espera vai
        até o `lock_timeout`, como no `lock_for_update`: estourar sobe como
        está (`55P03`), e quem o traduz é o controller.
        """
        self.session.query(func.set_config("lock_timeout", LOCK_TIMEOUT, True)).scalar()

        (
            self.session.query(LedgerAccount.id)
            .filter(LedgerAccount.id == ledger_account.id)
            .with_for_update()
            .one()
        )

        return self.session.query(func.clock_timestamp()).scalar()
