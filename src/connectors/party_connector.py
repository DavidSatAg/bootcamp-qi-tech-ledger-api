import requests

from connectors.rest_connector import BaseConnectorResponse, RestConnector
from constants import PARTY_API_INTERNAL_TOKEN, PARTY_API_TIMEOUT, PARTY_API_URL
from utils.request_context import get_request_id


class PartyConnector(RestConnector):
    """Fala com o Cadastro: quem diz se o dono de uma conta está ativo e
    qual é a chave Pix dele (01b §5). O Ledger não guarda a chave: lê aqui
    a cada repasse e a cada tentativa de despacho.

    Devolve a resposta como veio; o que um 404 ou um 5xx significa, quem
    decide é o controller. A falha de rede (timeout, conexão recusada)
    vira None: o `send` da base a deixa subir, e o `requests` só pode ser
    nomeado aqui, em `connectors/`.
    """

    def __init__(self) -> None:
        super().__init__(
            class_name=__name__,
            base_url=PARTY_API_URL,
            timeout=PARTY_API_TIMEOUT,
            internal_token=PARTY_API_INTERNAL_TOKEN,
        )

    def get_party(self, party_key: str) -> BaseConnectorResponse | None:
        """A parte, pela chave (`GET /parties/{party_key}`)."""
        try:
            return self.send(
                endpoint=f"/parties/{party_key}",
                method="GET",
                headers={"X-Request-ID": get_request_id()},
            )
        except requests.RequestException:
            self.logger.exception(f"Cadastro sem resposta para a parte {party_key}")
            return None
