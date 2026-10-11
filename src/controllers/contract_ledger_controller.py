from decimal import Decimal

from sqlalchemy.exc import IntegrityError

from constants import PLATFORM_PARTY_KEY
from controllers.base_controller import BaseController
from dtos import ContractLedgerDTO
from errors import (
    InvalidSchema,
    PurposePairNotAllowed,
    SplitDoesNotClose,
    SplitVersionConflict,
    SplitVersionOutOfSequence,
    UnknownPurposeCode,
)
from models import LedgerAccount, LedgerAccountType, PurposeCode, SplitSnapshot
from repositories import LedgerAccountRepository, PurposeRuleRepository, SplitSnapshotRepository
from utils.request_context import get_request_id

# Os cinco livros do cliente: (tipo, propósito, papel do dono). O dono
# sai do papel: o cliente na `own`, a plataforma na `revenue`, ninguém
# nas três contas de serviço.
CLIENT_BOOKS = [
    (LedgerAccountType.EXTERNAL, PurposeCode.CASH, ""),
    (LedgerAccountType.SUSPENSE, PurposeCode.UNALLOCATED, ""),
    (LedgerAccountType.CLEARING, PurposeCode.TRANSIT, ""),
    (LedgerAccountType.OWN, PurposeCode.OWN, "administrator"),
    (LedgerAccountType.REVENUE, PurposeCode.PLATFORM_FEE, "platform"),
]

FOUR_PLACES = Decimal("0.0001")
HUNDRED_PERCENT = Decimal(100)


def four_places(percentage) -> str:
    """O percentual com 4 casas: "10", "10.0" e Decimal("10.0000") são o mesmo."""
    return str(Decimal(percentage).quantize(FOUR_PLACES))


def split_item(purpose_code: str, owner_party_key: str, allocation_type: str, value) -> tuple:
    """Um item do split como se compara: propósito, dono, tipo e valor."""
    if allocation_type == SplitSnapshot.PERCENTAGE:
        value = four_places(value)
    elif allocation_type == SplitSnapshot.FIXED:
        value = str(value)
    else:
        value = ""

    return (purpose_code, owner_party_key, allocation_type, value)


class ContractLedgerController(BaseController):
    """O provisionamento: os livros do cliente e os earmarks do contrato."""

    def __init__(self) -> None:
        super().__init__(__name__)
        self.ledger_account_repository = LedgerAccountRepository(self.context)
        self.split_snapshot_repository = SplitSnapshotRepository(self.context)
        self.purpose_rule_repository = PurposeRuleRepository(self.context)

    def provision(self, payload: dict) -> tuple:
        """Abre o que falta e devolve (corpo, criou?).

        A corrida: duas requisições com o mesmo contrato (ou o mesmo
        cliente) podem passar juntas pela busca e tentar criar a mesma
        linha. Quem chega depois esbarra numa UNIQUE do banco, e não numa
        trava: não há saldo em jogo. Essa requisição desfaz a sua
        transação e refaz o provisionamento UMA vez, já enxergando o que a
        outra gravou — o replay vira 200, o conflito vira 409 e o livro de
        outro contrato é reusado. Esbarrar de novo sobe como 500.
        """
        try:
            return self._provision_once(payload)
        except IntegrityError:
            self.logger.info("Corrida no provisionamento: refazendo sobre o que a outra requisição gravou")
            self.session.rollback()

        return self._provision_once(payload)

    def _provision_once(self, payload: dict) -> tuple:
        """Uma tentativa inteira, numa transação só, com o commit no fim.

        A versão pedida decide o caminho (RN-05): uma versão que já existe
        é replay ou conflito, e nada se grava; só a próxima cria.
        """
        self._check_split(payload)

        contract_key = payload["contract_key"]
        split_version = payload["split_version"]
        latest_split_version = self.split_snapshot_repository.get_max_version(contract_key)

        if split_version <= latest_split_version:
            return self._replay(payload, latest_split_version), False

        if split_version > latest_split_version + 1:
            raise SplitVersionOutOfSequence(contract_key, split_version, latest_split_version)

        client_books = self._open_client_books(payload)
        collection = self._find_or_create(
            payload, LedgerAccountType.EARMARK, PurposeCode.COLLECTION, payload["contract_key"], "", ""
        )

        item_accounts = []
        for item in payload["items"]:
            item_accounts.append(self._open_item_account(payload, item, client_books))

        self._write_split_snapshot(payload, collection, item_accounts, client_books)

        accounts = self._split_accounts(collection, item_accounts, client_books)

        contract_ledger_dto = ContractLedgerDTO.obj_to_dict(
            payload["contract_key"],
            payload["split_version"],
            self._expected_amount_in_cents(payload),
            accounts,
        )
        self.session.commit()

        return contract_ledger_dto, True

    def _check_split(self, payload: dict) -> None:
        """As conferências que vêm antes de qualquer escrita, nesta ordem
        (RN-02): item repetido, propósito desconhecido, par proibido e
        split que não fecha. Recusa aqui não grava nada.

        O propósito desconhecido vem antes do par: sem o código, não há
        par a consultar.
        """
        seen_items = set()
        for item in payload["items"]:
            # O dono da conta de destino, não o beneficiário: todo OWN cai na
            # mesma own/OWN do cliente (desvio 5).
            item_owner = self._item_owner(payload, item)
            item_key = (item["purpose_code"], item_owner)
            if item_key in seen_items:
                # Colidiriam na mesma linha do split_snapshot: é pedido
                # malformado, e por isso 400, como o schema.
                raise InvalidSchema(
                    f"items has {item['purpose_code']} for {item_owner} more than once"
                )
            seen_items.add(item_key)

        for item in payload["items"]:
            if self.ledger_account_repository.get_purpose_code(item["purpose_code"]) is None:
                raise UnknownPurposeCode(item["purpose_code"])

        pairs = [(PurposeCode.COLLECTION, item["purpose_code"]) for item in payload["items"]]
        pairs.append((PurposeCode.OWN, PurposeCode.PLATFORM_FEE))
        for source_purpose_code, target_purpose_code in pairs:
            if not self.purpose_rule_repository.exists_pair(source_purpose_code, target_purpose_code):
                raise PurposePairNotAllowed(source_purpose_code, target_purpose_code)

        percentage_sum = Decimal(0)
        administration_fee = Decimal(0)
        for item in payload["items"]:
            if item["type"] == SplitSnapshot.PERCENTAGE:
                percentage_sum = percentage_sum + Decimal(item["value"])
                if item["purpose_code"] == PurposeCode.OWN:
                    administration_fee = administration_fee + Decimal(item["value"])

        if percentage_sum >= HUNDRED_PERCENT:
            raise SplitDoesNotClose(f"the percentages add up to {percentage_sum}%")

        platform_fee_percentage = Decimal(payload["platform_fee_percentage"])
        if platform_fee_percentage > administration_fee:
            raise SplitDoesNotClose(
                f"the platform fee {platform_fee_percentage}% is above the administration fee {administration_fee}%"
            )

    def _replay(self, payload: dict, latest_split_version: int) -> dict:
        """A versão já existe: mesmo conteúdo devolve as contas dela; outro
        conteúdo é 032 se ela é a atual, e 033 se é anterior."""
        contract_key = payload["contract_key"]
        split_version = payload["split_version"]
        rows = self.split_snapshot_repository.list_by_version(contract_key, split_version)

        if self._content_of_rows(rows) != self._content_of_payload(payload):
            if split_version == latest_split_version:
                raise SplitVersionConflict(contract_key, split_version)
            raise SplitVersionOutOfSequence(contract_key, split_version, latest_split_version)

        targets = dict()
        for split_snapshot, source_ledger_account, ledger_account in rows:
            if source_ledger_account.purpose_code.enumerator == PurposeCode.OWN:
                client_books = {PurposeCode.OWN: source_ledger_account, PurposeCode.PLATFORM_FEE: ledger_account}
            else:
                collection = source_ledger_account
                targets[(ledger_account.purpose_code.enumerator, ledger_account.owner_party_key)] = ledger_account

        item_accounts = []
        for item in payload["items"]:
            item_accounts.append(targets[(item["purpose_code"], self._item_owner(payload, item))])

        return ContractLedgerDTO.obj_to_dict(
            contract_key,
            split_version,
            self._expected_amount_in_cents(payload),
            self._split_accounts(collection, item_accounts, client_books),
        )

    def _content_of_payload(self, payload: dict) -> tuple:
        """O conteúdo do pedido, na forma em que o split_snapshot o guarda (RN-06)."""
        items = []
        for item in payload["items"]:
            items.append(
                split_item(item["purpose_code"], self._item_owner(payload, item), item["type"], item.get("value"))
            )

        return (
            payload["rent_amount_in_cents"],
            four_places(payload["platform_fee_percentage"]),
            sorted(items),
        )

    def _content_of_rows(self, rows: list) -> tuple:
        """O conteúdo gravado de uma versão: os itens saem da COLLECTION; a
        taxa da plataforma é a linha que sai da `own`."""
        rent_amount_in_cents = None
        platform_fee_percentage = None
        items = []

        for split_snapshot, source_ledger_account, ledger_account in rows:
            rent_amount_in_cents = int(split_snapshot.rent_amount_in_cents)

            if source_ledger_account.purpose_code.enumerator == PurposeCode.OWN:
                platform_fee_percentage = four_places(split_snapshot.percentage)
                continue

            value = split_snapshot.percentage
            if split_snapshot.allocation_type == SplitSnapshot.FIXED:
                value = int(split_snapshot.amount_in_cents)

            items.append(
                split_item(
                    ledger_account.purpose_code.enumerator,
                    ledger_account.owner_party_key,
                    split_snapshot.allocation_type,
                    value,
                )
            )

        return (rent_amount_in_cents, platform_fee_percentage, sorted(items))

    def _item_owner(self, payload: dict, item: dict) -> str:
        """O dono da conta de destino do item. O item OWN vai para a `own/OWN`
        do cliente, cujo dono é o `client_party_key`."""
        if item["purpose_code"] == PurposeCode.OWN:
            return payload["client_party_key"]

        return item["beneficiary_party_key"]

    def _expected_amount_in_cents(self, payload: dict) -> int:
        """O valor esperado da competência: o aluguel mais os itens `fixed`."""
        expected_amount_in_cents = payload["rent_amount_in_cents"]

        for item in payload["items"]:
            if item["type"] == SplitSnapshot.FIXED:
                expected_amount_in_cents = expected_amount_in_cents + item["value"]

        return expected_amount_in_cents

    def _write_split_snapshot(self, payload: dict, collection: LedgerAccount, item_accounts: list, client_books: dict) -> None:
        """Uma linha por item, saindo da COLLECTION, e uma da taxa da
        plataforma, saindo da `own` para a `revenue`. O aluguel vai em todas."""
        for item, item_account in zip(payload["items"], item_accounts):
            percentage = None
            amount_in_cents = None

            if item["type"] == SplitSnapshot.PERCENTAGE:
                percentage = Decimal(item["value"])

            if item["type"] == SplitSnapshot.FIXED:
                amount_in_cents = item["value"]

            self.split_snapshot_repository.create(
                contract_key=payload["contract_key"],
                split_version=payload["split_version"],
                source_ledger_account=collection,
                ledger_account=item_account,
                allocation_type=item["type"],
                percentage=percentage,
                amount_in_cents=amount_in_cents,
                rent_amount_in_cents=payload["rent_amount_in_cents"],
            )

        self.split_snapshot_repository.create(
            contract_key=payload["contract_key"],
            split_version=payload["split_version"],
            source_ledger_account=client_books[PurposeCode.OWN],
            ledger_account=client_books[PurposeCode.PLATFORM_FEE],
            allocation_type=SplitSnapshot.PERCENTAGE,
            percentage=Decimal(payload["platform_fee_percentage"]),
            amount_in_cents=None,
            rent_amount_in_cents=payload["rent_amount_in_cents"],
        )

    def _split_accounts(self, collection: LedgerAccount, item_accounts: list, client_books: dict) -> list:
        """As contas do split, na ordem do 01b: COLLECTION, os earmarks na
        ordem dos itens, OWN e PLATFORM_FEE."""
        accounts = [collection]

        for item_account in item_accounts:
            if item_account.purpose_code.enumerator != PurposeCode.OWN:
                accounts.append(item_account)

        accounts.append(client_books[PurposeCode.OWN])
        accounts.append(client_books[PurposeCode.PLATFORM_FEE])

        return accounts

    def _open_client_books(self, payload: dict) -> dict:
        owners = {
            "": "",
            "administrator": payload["client_party_key"],
            "platform": PLATFORM_PARTY_KEY,
        }

        client_books = dict()
        for ledger_account_type, purpose_code, owner_role in CLIENT_BOOKS:
            client_books[purpose_code] = self._find_or_create(
                payload, ledger_account_type, purpose_code, "", owners[owner_role], owner_role
            )

        return client_books

    def _open_item_account(self, payload: dict, item: dict, client_books: dict) -> LedgerAccount:
        """O destino de um item: a `own/OWN` do cliente, ou um earmark do contrato."""
        if item["purpose_code"] == PurposeCode.OWN:
            return client_books[PurposeCode.OWN]

        return self._find_or_create(
            payload,
            LedgerAccountType.EARMARK,
            item["purpose_code"],
            payload["contract_key"],
            item["beneficiary_party_key"],
            item["beneficiary_role"],
        )

    def _find_or_create(
        self,
        payload: dict,
        ledger_account_type: str,
        purpose_code: str,
        contract_key: str,
        owner_party_key: str,
        owner_role: str,
    ) -> LedgerAccount:
        """Reusa a conta, se já existe; senão, cria. Só a criada ganha evento."""
        ledger_account = self.ledger_account_repository.find_by_natural_key(
            payload["client_key"], ledger_account_type, purpose_code, contract_key, owner_party_key
        )

        if ledger_account is not None:
            return ledger_account

        return self.ledger_account_repository.create(
            client_key=payload["client_key"],
            ledger_account_type=ledger_account_type,
            purpose_code=purpose_code,
            contract_key=contract_key,
            owner_party_key=owner_party_key,
            owner_role=owner_role,
            actor=payload["actor"],
            reason=payload.get("reason"),
            trace_id=get_request_id(),
        )
