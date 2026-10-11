from fastapi import status as http_status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from controllers import ContractLedgerController
from utils.schema_handler import SchemaHandler


class ContractLedgerResource:
    """A porta de entrada HTTP do provisionamento de um contrato no ledger.

    É a rota com dois sucessos: 201 quando criou agora, 200 quando a
    versão já estava provisionada com o mesmo conteúdo. Quem sabe qual
    dos dois aconteceu é o controller; quem transforma isso em status é
    este resource, como em toda rota.
    """

    @SchemaHandler.validate("post_contract_ledgers.json")
    def on_post(self, payload: dict) -> JSONResponse:
        controller = ContractLedgerController()
        contract_ledger, created = controller.provision(payload)

        status_code = http_status.HTTP_200_OK
        if created:
            status_code = http_status.HTTP_201_CREATED

        return JSONResponse(
            content=jsonable_encoder(contract_ledger),
            status_code=status_code,
        )
