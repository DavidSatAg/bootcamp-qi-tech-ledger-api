from dtos.ledger_account_dto import empty_as_null


class IntegrityDTO:
    """Traduz a conferência de integridade no JSON que a API devolve."""

    @staticmethod
    def obj_to_dict(client_key: str | None, totals: dict, negatives: list) -> dict:
        """`totals` = {asset, liability, equity, difference};
        `negatives` = [(LedgerAccount, saldo orientado)]."""
        dto = dict()
        dto["client_key"] = client_key
        dto["asset_in_cents"] = totals["asset"]
        dto["liability_in_cents"] = totals["liability"]
        dto["equity_in_cents"] = totals["equity"]
        dto["difference_in_cents"] = totals["difference"]
        dto["negative_accounts"] = []

        for ledger_account, balance_in_cents in negatives:
            negative_dto = dict()
            negative_dto["ledger_account_key"] = ledger_account.ledger_account_key
            negative_dto["client_key"] = ledger_account.client_key
            negative_dto["contract_key"] = empty_as_null(ledger_account.contract_key)
            negative_dto["purpose_code"] = ledger_account.purpose_code.enumerator
            negative_dto["balance_in_cents"] = balance_in_cents

            dto["negative_accounts"].append(negative_dto)

        return dto
