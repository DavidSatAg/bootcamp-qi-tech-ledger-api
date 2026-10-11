from uuid import uuid4

from tests.utils.random_generator import RandomGenerator


class PayloadGenerator:
    @staticmethod
    def create_sample_entity_payload(
        hello: str = None,
        name: str = None,
        email: str = None,
        document_number: str = None,
        birthdate: str = None,
    ) -> dict:
        """Um cadastro valido, com qualquer campo trocado a pedido.

        Sem argumento nenhum o payload sai aleatorio no que precisa ser
        unico (e-mail e CPF), pra que dois cadastros seguidos nao batam
        na regra de duplicidade. Quem testa FILTRO precisa do contrario
        disso: um valor conhecido, pra poder procurar por ele depois.
        """
        if hello is None:
            hello = "world"

        if name is None:
            name = "Maria da Silva"

        if email is None:
            email = f"maria.silva.{uuid4()}@exemplo.com.br"

        if document_number is None:
            document_number = RandomGenerator.generate_cpf()

        if birthdate is None:
            birthdate = "1990-05-17"

        payload = {
            "hello": hello,
            "name": name,
            "email": email,
            "document_number": document_number,
            "birthdate": birthdate,
        }
        return payload

    @staticmethod
    def create_new_status_payload(new_status: str = None) -> dict:
        payload = {"status": new_status}
        return payload

    @staticmethod
    def create_contract_ledger_payload(
        contract_key: str = None,
        split_version: int = None,
        rent_amount_in_cents: int = None,
        platform_fee_percentage: str = None,
        items: list = None,
        actor: str = None,
    ) -> dict:
        """O provisionamento do caso do remodelagem/05 (o exemplo do 01b §3).

        Só o `contract_key` muda a cada chamada: um `uuid4` novo, para
        que cada teste tenha o seu contrato. O cliente é sempre a
        Imobiliária Alfa (c1c1…), e os beneficiários são as chaves
        mágicas do guia 00 §2.
        """
        if contract_key is None:
            contract_key = str(uuid4())

        if split_version is None:
            split_version = 1

        if rent_amount_in_cents is None:
            rent_amount_in_cents = 500000

        if platform_fee_percentage is None:
            platform_fee_percentage = "1.0000"

        if items is None:
            items = [
                {
                    "purpose_code": "RENT",
                    "beneficiary_party_key": "22222222-2222-4222-8222-222222222222",
                    "beneficiary_role": "landlord",
                    "type": "remainder",
                },
                {
                    "purpose_code": "OWN",
                    "beneficiary_party_key": "11111111-1111-4111-8111-111111111111",
                    "beneficiary_role": "administrator",
                    "type": "percentage",
                    "value": "10.0000",
                },
                {
                    "purpose_code": "IPTU",
                    "beneficiary_party_key": "44444444-4444-4444-8444-444444444444",
                    "beneficiary_role": "provider",
                    "type": "fixed",
                    "value": 30000,
                },
                {
                    "purpose_code": "CONDO",
                    "beneficiary_party_key": "55555555-5555-4555-8555-555555555555",
                    "beneficiary_role": "provider",
                    "type": "fixed",
                    "value": 80000,
                },
                {
                    "purpose_code": "WATER",
                    "beneficiary_party_key": "66666666-6666-4666-8666-666666666666",
                    "beneficiary_role": "provider",
                    "type": "fixed",
                    "value": 12000,
                },
                {
                    "purpose_code": "ELECTRICITY",
                    "beneficiary_party_key": "77777777-7777-4777-8777-777777777777",
                    "beneficiary_role": "provider",
                    "type": "fixed",
                    "value": 18000,
                },
            ]

        if actor is None:
            actor = "contract-api"

        payload = {
            "contract_key": contract_key,
            "client_key": "c1c1c1c1-c1c1-4c1c-8c1c-c1c1c1c1c1c1",
            "client_party_key": "11111111-1111-4111-8111-111111111111",
            "split_version": split_version,
            "rent_amount_in_cents": rent_amount_in_cents,
            "platform_fee_percentage": platform_fee_percentage,
            "items": items,
            "actor": actor,
            "reason": "ativação do contrato ALFA-2026-0042",
        }

        return payload

    @staticmethod
    def create_inflow_payload(
        contract_key: str,
        amount_in_cents: int = 640000,
        period_reference: str = "2026-09",
        payer_party_key: str = "33333333-3333-4333-8333-333333333333",
        end_to_end_id: str = None,
        value_date: str = None,
        actor: str = "erp-alfa",
    ) -> dict:
        """A entrada por Pix do caso do remodelagem/05 (TX1): o aluguel de
        setembro pago pelo Bruno (3333…) no contrato pedido.

        O `end_to_end_id` é o do exemplo com 11 caracteres aleatórios no
        fim: ele é único no ledger, e cada entrada precisa do seu.
        `value_date` ausente fica fora do corpo: o ledger usa o agora.
        """
        if end_to_end_id is None:
            end_to_end_id = "E00000000202609051422" + uuid4().hex[:11]

        payload = {
            "amount_in_cents": amount_in_cents,
            "contract_key": contract_key,
            "period_reference": period_reference,
            "payer_party_key": payer_party_key,
            "end_to_end_id": end_to_end_id,
            "actor": actor,
        }

        if value_date is not None:
            payload["value_date"] = value_date

        return payload
