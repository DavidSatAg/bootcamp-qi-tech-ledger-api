from fastapi import Request


async def read_raw_body(request: Request) -> bytes:
    """Os bytes do corpo exatamente como chegaram, para a impressão digital
    da idempotência (SHA-256 dos bytes crus, não do JSON relido).

    É `async` porque o `request.body()` é: o FastAPI resolve esta dependência
    no laço de eventos, antes de chamar o resource, que continua `def`. O
    corpo já foi lido para montar o `payload` e o Starlette o guarda, então
    esta leitura não consome nada de novo.
    """
    return await request.body()
