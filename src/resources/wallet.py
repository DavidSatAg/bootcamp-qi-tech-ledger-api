from fastapi import status as http_status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from controllers import WalletController
from utils.schema_handler import SchemaHandler


class WalletResource:
    """A porta de entrada HTTP da abertura da carteira.

    Dois sucessos, como no provisionamento: 201 quando abriu agora, 200
    quando a parte já tinha carteira. O controller diz qual aconteceu; o
    status sai daqui.
    """

    @SchemaHandler.validate("post_wallets.json")
    def on_post(self, payload: dict) -> JSONResponse:
        controller = WalletController()
        wallet, created = controller.open(payload)

        status_code = http_status.HTTP_200_OK
        if created:
            status_code = http_status.HTTP_201_CREATED

        return JSONResponse(
            content=jsonable_encoder(wallet),
            status_code=status_code,
        )
