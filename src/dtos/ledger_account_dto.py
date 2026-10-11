from typing import List

from models import LedgerAccount


def empty_as_null(value: str):
    """No banco, conta sem dono guarda ''. Na API, '' sai como null."""
    if value == "":
        return None
    return value


class LedgerAccountDTO:
    """Traduz a conta do ledger no JSON que a API devolve."""

    @staticmethod
    def obj_to_dict(ledger_account: LedgerAccount, balance_in_cents: int) -> dict:
        """A conta inteira: o resumo, o saldo e a trilha de status.

        O evento não tem campo `status`: o que ele registra é a chegada a
        `to_status`, e é esse o status que a trilha mostra.
        """
        dto = LedgerAccountDTO.obj_to_simplified_dict(ledger_account)
        dto["balance_in_cents"] = balance_in_cents
        dto["status_events"] = []

        for status_event in ledger_account.status_events:
            status_event_dto = dict()
            status_event_dto["status"] = status_event.to_status.enumerator
            status_event_dto["event_datetime"] = status_event.event_datetime.isoformat()

            dto["status_events"].append(status_event_dto)

        return dto

    @staticmethod
    def obj_to_simplified_dict(ledger_account: LedgerAccount) -> dict:
        dto = dict()
        dto["ledger_account_key"] = ledger_account.ledger_account_key
        dto["client_key"] = ledger_account.client_key
        dto["contract_key"] = empty_as_null(ledger_account.contract_key)
        dto["ledger_account_type"] = ledger_account.ledger_account_type.enumerator
        dto["purpose_code"] = ledger_account.purpose_code.enumerator
        dto["status"] = ledger_account.ledger_account_status.enumerator
        dto["owner_party_key"] = empty_as_null(ledger_account.owner_party_key)
        dto["owner_role"] = empty_as_null(ledger_account.owner_role)
        dto["currency"] = ledger_account.currency

        return dto

    @staticmethod
    def list_obj_to_list_dict(ledger_accounts_list: List[LedgerAccount]) -> List[dict]:
        """A listagem sai sem saldo e sem trilha: cada um custaria uma
        consulta por conta da página."""
        ledger_accounts_dict_list = []

        for ledger_account in ledger_accounts_list:
            ledger_accounts_dict_list.append(LedgerAccountDTO.obj_to_simplified_dict(ledger_account))

        return ledger_accounts_dict_list
