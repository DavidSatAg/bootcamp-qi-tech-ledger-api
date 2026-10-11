import os


SERVICE_ROOT = os.path.abspath(os.path.dirname(__file__))

# Onde moram os arquivos de schema — os .json que descrevem o formato
# que cada requisicao precisa ter. Quem le essa pasta e o
# src/utils/schema_handler.py.
SCHEMA_PATH = os.path.join(SERVICE_ROOT, "schemas")

APP_ENV = os.environ.get("APP_ENV", "local")
SERVICE_NAME = os.environ.get("SERVICE_NAME", "bootcamp-api")

DATABASE_URL = os.environ.get("DATABASE_URL")
INTERNAL_TOKEN = os.environ.get("INTERNAL_TOKEN")

# A API de boletos: o serviço de fora que este projeto chama pra emitir
# uma cobrança (veja src/connectors/). O endereço vem do ambiente, como
# tudo aqui — na sua máquina ele aponta pro mock server do sábado 4; em
# produção, apontaria pro serviço de verdade. O código não sabe a
# diferença, e esse é o ponto.
BANKSLIP_API_URL = os.environ.get("BANKSLIP_API_URL", "http://localhost:8080")
BANKSLIP_API_INTERNAL_TOKEN = os.environ.get("BANKSLIP_API_INTERNAL_TOKEN", "default_token")

# Quantos segundos esperar pelo serviço de boletos antes de desistir.
# Todo connector TEM um timeout — o porquê está em
# src/connectors/rest_connector.py.
BANKSLIP_API_TIMEOUT = int(os.environ.get("BANKSLIP_API_TIMEOUT", "5"))

# Rotas públicas: não exigem o header INTERNAL-TOKEN. São as duas que
# precisam responder pra quem ainda não tem token nenhum: a raiz, que
# diz quem é este serviço, e o health check, que o Docker consulta pra
# saber se a API já está de pé.
BYPASS_ENDPOINTS = [
    "/",
    "/health_check",
    # Acrescentada pelo Ledger: a verificação pública do extrato (RFC :107; D0009 :94-98).
    "/statement/verify",
]

REQUIRED_VARIABLES = ["DATABASE_URL", "INTERNAL_TOKEN"]


def check_variables():
    missing = []
    for name in REQUIRED_VARIABLES:
        if not globals().get(name):
            missing.append(name)

    if missing:
        raise EnvironmentError(
            f"Faltam variáveis de ambiente: {', '.join(missing)}. "
            "Rodando com 'docker compose up' elas já vêm preenchidas. "
            "Fora do Docker, copie o .env.example para .env."
        )


# Ledger: as variaveis que o Ledger acrescenta a base, no mesmo padrao
# de cima (o valor vem do ambiente; o padrao garante que roda sem .env).
# Os padroes sao os de producao; os testes usam timeouts de 1 segundo,
# que vem do .env.example.

# O Cadastro (Contrato): quem diz se a pessoa existe e qual a chave Pix.
PARTY_API_URL = os.environ.get("PARTY_API_URL", "http://party-mock:8080")
PARTY_API_INTERNAL_TOKEN = os.environ.get("PARTY_API_INTERNAL_TOKEN", "default_token")
PARTY_API_TIMEOUT = int(os.environ.get("PARTY_API_TIMEOUT", "3"))

# O provedor de pagamentos, de fora.
PROVIDER_API_URL = os.environ.get("PROVIDER_API_URL", "http://provider-mock:8080")
PROVIDER_API_INTERNAL_TOKEN = os.environ.get("PROVIDER_API_INTERNAL_TOKEN", "default_token")
PROVIDER_API_TIMEOUT = int(os.environ.get("PROVIDER_API_TIMEOUT", "5"))

# As chaves das contas da propria plataforma.
PLATFORM_PARTY_KEY = os.environ.get("PLATFORM_PARTY_KEY", "99999999-9999-4999-8999-999999999999")
PLATFORM_CLIENT_KEY = os.environ.get("PLATFORM_CLIENT_KEY", "9c9c9c9c-9c9c-49c9-89c9-9c9c9c9c9c9c")

# Quanto esperar por um lock no banco. E texto, no formato do Postgres
# (SET LOCAL lock_timeout = '3s'), por isso nao passa por int().
LOCK_TIMEOUT = os.environ.get("LOCK_TIMEOUT", "3s")

# Quantas vezes o outbox tenta entregar uma mensagem antes de desistir.
OUTBOX_MAX_ATTEMPTS = int(os.environ.get("OUTBOX_MAX_ATTEMPTS", "5"))
