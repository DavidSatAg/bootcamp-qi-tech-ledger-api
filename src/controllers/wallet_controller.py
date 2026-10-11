from sqlalchemy.exc import IntegrityError

from connectors import PartyConnector
from constants import PLATFORM_CLIENT_KEY, PLATFORM_PARTY_KEY
from controllers.base_controller import BaseController
from controllers.contract_ledger_controller import CLIENT_BOOKS
from dtos import LedgerAccountDTO
from errors import OwnerNotActive, PartyServiceUnavailable
from models import LedgerAccount, LedgerAccountType, PurposeCode
from repositories import LedgerAccountRepository
from utils.request_context import get_request_id

# O Cadastro responde a parte com 200 ou diz que ela não existe com 404;
# qualquer outro status é Cadastro indisponível (S09 D10).
PARTY_ANSWERS = (200, 404)
PARTY_ACTIVE = "active"

# Quem é o dono de cada livro da plataforma, pelo papel (G:376-378):
# a própria plataforma na `own` e na `revenue`, ninguém nas de serviço.
PLATFORM_OWNERS = {
    "": "",
    "administrator": PLATFORM_PARTY_KEY,
    "platform": PLATFORM_PARTY_KEY,
}

WALLET_OWNER_ROLE = "holder"


class WalletController(BaseController):
    """A carteira: a `own/WALLET` de uma parte, nos livros da plataforma
    (RFC :146; guia do Ledger :440-445)."""

    def __init__(self) -> None:
        super().__init__(__name__)
        self.ledger_account_repository = LedgerAccountRepository(self.context)
        self.party_connector = PartyConnector()

    def open(self, payload: dict) -> tuple:
        """Abre a carteira, se falta, e devolve (corpo, criou?) (RN-01).

        O Cadastro vem primeiro, sem transação aberta (01b :86): só uma
        parte ativa ganha carteira. A corrida é a do provisionamento: duas
        aberturas da mesma parte passam juntas pela busca, a segunda
        esbarra na UNIQUE, desfaz e refaz UMA vez, já enxergando a conta
        da outra — e responde 200 com ela.
        """
        self._check_party(payload["party_key"])

        try:
            return self._open_once(payload)
        except IntegrityError:
            self.logger.info("Corrida na abertura da carteira: refazendo sobre o que a outra requisição gravou")
            self.session.rollback()

        return self._open_once(payload)

    def _check_party(self, party_key: str) -> None:
        """A parte no Cadastro (G:442; 01b :162-167). Sem resposta, outro
        status, ou um 200 sem a parte no corpo: 040. Não existe ou não
        está ativa: 038."""
        party_response = self.party_connector.get_party(party_key)

        if party_response is None or party_response.status not in PARTY_ANSWERS:
            raise PartyServiceUnavailable()

        if party_response.status == 200 and not isinstance(party_response.json, dict):
            raise PartyServiceUnavailable()

        if party_response.status == 404 or party_response.json.get("status") != PARTY_ACTIVE:
            raise OwnerNotActive()

    def _open_once(self, payload: dict) -> tuple:
        """Uma tentativa inteira, numa transação só, com o commit no fim.

        Os livros da plataforma nascem com a primeira carteira; a carteira
        que já existe volta como está, sem evento novo.
        """
        for ledger_account_type, purpose_code, owner_role in CLIENT_BOOKS:
            self._find_or_create(payload, ledger_account_type, purpose_code, PLATFORM_OWNERS[owner_role], owner_role)

        wallet = self.ledger_account_repository.find_by_natural_key(
            PLATFORM_CLIENT_KEY, LedgerAccountType.OWN, PurposeCode.WALLET, "", payload["party_key"]
        )
        created = False

        if wallet is None:
            wallet = self._create(payload, LedgerAccountType.OWN, PurposeCode.WALLET, payload["party_key"], WALLET_OWNER_ROLE)
            created = True

        # O DTO sai antes do commit, que expira o ORM.
        wallet_dto = LedgerAccountDTO.obj_to_dict(wallet, self.ledger_account_repository.get_balance(wallet))
        self.session.commit()

        return wallet_dto, created

    def _find_or_create(
        self,
        payload: dict,
        ledger_account_type: str,
        purpose_code: str,
        owner_party_key: str,
        owner_role: str,
    ) -> LedgerAccount:
        """Reusa o livro da plataforma, se já existe; senão, cria."""
        ledger_account = self.ledger_account_repository.find_by_natural_key(
            PLATFORM_CLIENT_KEY, ledger_account_type, purpose_code, "", owner_party_key
        )

        if ledger_account is not None:
            return ledger_account

        return self._create(payload, ledger_account_type, purpose_code, owner_party_key, owner_role)

    def _create(
        self,
        payload: dict,
        ledger_account_type: str,
        purpose_code: str,
        owner_party_key: str,
        owner_role: str,
    ) -> LedgerAccount:
        """Uma conta nova no livro da plataforma. Sem `reason`: a abertura
        não tem motivo no corpo (RFC :146; D1)."""
        return self.ledger_account_repository.create(
            client_key=PLATFORM_CLIENT_KEY,
            ledger_account_type=ledger_account_type,
            purpose_code=purpose_code,
            contract_key="",
            owner_party_key=owner_party_key,
            owner_role=owner_role,
            actor=payload["actor"],
            reason=None,
            trace_id=get_request_id(),
        )
