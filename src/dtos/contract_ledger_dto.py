from typing import List

from dtos.ledger_account_dto import empty_as_null
from models import LedgerAccount


class ContractLedgerDTO:
    """A resposta do provisionamento: o contrato e as contas do split.

    O mesmo corpo sai no 201 (criou agora) e no 200 (replay).
    """

    @staticmethod
    def obj_to_dict(contract_key: str, accounts: List[LedgerAccount]) -> dict:
        dto = dict()
        dto["contract_key"] = contract_key
        dto["accounts"] = []

        for ledger_account in accounts:
            account_dto = dict()
            account_dto["purpose_code"] = ledger_account.purpose_code.enumerator
            account_dto["ledger_account_key"] = ledger_account.ledger_account_key
            account_dto["owner_party_key"] = empty_as_null(ledger_account.owner_party_key)
            account_dto["owner_role"] = empty_as_null(ledger_account.owner_role)

            dto["accounts"].append(account_dto)

        return dto
