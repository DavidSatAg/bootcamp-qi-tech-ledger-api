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

    @staticmethod
    def create_suspense_inflow_payload(
        client_key: str = "c1c1c1c1-c1c1-4c1c-8c1c-c1c1c1c1c1c1",
        amount_in_cents: int = 640000,
        end_to_end_id: str = None,
        value_date: str = None,
        actor: str = "erp-alfa",
    ) -> dict:
        """A entrada por Pix sem identificação (CU-B2): o valor da TX1 que
        chega só com o `client_key`, sem contrato, competência nem pagador.

        O `end_to_end_id` segue a regra do `create_inflow_payload`.
        """
        if end_to_end_id is None:
            end_to_end_id = "E00000000202609051422" + uuid4().hex[:11]

        payload = {
            "amount_in_cents": amount_in_cents,
            "client_key": client_key,
            "end_to_end_id": end_to_end_id,
            "actor": actor,
        }

        if value_date is not None:
            payload["value_date"] = value_date

        return payload

    @staticmethod
    def create_closure_payload(actor: str = "contract-api", reason: str = "fim da locação ALFA-2026-0042") -> dict:
        """O encerramento do contrato, como o Contrato o manda (01b §4)."""
        return {"actor": actor, "reason": reason}

    @staticmethod
    def create_split_payload(
        contract_key: str,
        period_reference: str = "2026-09",
        value_date: str = None,
        actor: str = "erp-alfa",
        reason: str = None,
    ) -> dict:
        """A divisão da competência do caso do remodelagem/05 (TX2) no
        contrato pedido. `value_date` e `reason` ausentes ficam fora do corpo.
        """
        payload = {
            "contract_key": contract_key,
            "period_reference": period_reference,
            "actor": actor,
        }

        if value_date is not None:
            payload["value_date"] = value_date

        if reason is not None:
            payload["reason"] = reason

        return payload

    @staticmethod
    def create_statement_payload(
        ledger_account_key: str,
        period_start: str = "2026-09-01T00:00:00Z",
        period_end: str = "2026-10-01T00:00:00Z",
        actor: str = "erp-alfa",
    ) -> dict:
        """O fechamento de setembro, a competência do TX1 (remodelagem/05)."""
        return {
            "ledger_account_key": ledger_account_key,
            "period_start": period_start,
            "period_end": period_end,
            "actor": actor,
        }

    @staticmethod
    def create_payout_payload(
        source_account_key: str,
        amount_in_cents: int = 450000,
        destination: str = "pix",
        period_reference: str = "2026-09",
        actor: str = "erp-alfa",
        reason: str = "repasse aluguel 09/2026",
    ) -> dict:
        """O repasse do caso do remodelagem/05: os 450000 da RENT da Ana
        (2222…), por Pix, na competência de setembro."""
        return {
            "source_account_key": source_account_key,
            "amount_in_cents": amount_in_cents,
            "destination": destination,
            "period_reference": period_reference,
            "actor": actor,
            "reason": reason,
        }

    @staticmethod
    def create_internal_payload(
        source_account_key: str,
        target_account_key: str,
        gross_amount_in_cents: int = 45000,
        actor: str = "gerente-financeiro@alfa",
        reason: str = "devolução de taxa — MED 09/2026",
        value_date: str = None,
    ) -> dict:
        """A transferência interna da TX8 do remodelagem/05: a devolução de
        taxa, com uma alocação `remainder` só (fatia 15a, D1).
        `value_date` ausente fica fora do corpo."""
        payload = {
            "source_account_key": source_account_key,
            "gross_amount_in_cents": gross_amount_in_cents,
            "allocations": [{"target_account_key": target_account_key, "type": "remainder"}],
            "actor": actor,
            "reason": reason,
        }

        if value_date is not None:
            payload["value_date"] = value_date

        return payload

    @staticmethod
    def create_internal_allocations_payload(
        source_account_key: str,
        allocations: list,
        gross_amount_in_cents: int = 500000,
        actor: str = "erp-alfa",
        reason: str = "aluguel setembro APT-101",
        value_date: str = None,
    ) -> dict:
        """A transferência interna com rateio (D0013 :41-51; fatia 15b).
        `allocations` vai como veio; `value_date` ausente fica fora do corpo."""
        payload = {
            "source_account_key": source_account_key,
            "gross_amount_in_cents": gross_amount_in_cents,
            "allocations": allocations,
            "actor": actor,
            "reason": reason,
        }

        if value_date is not None:
            payload["value_date"] = value_date

        return payload

    @staticmethod
    def create_webhook_payload(
        outbox_key: str,
        provider_reference: str,
        event_type: str = "settlement_confirmed",
        value_date: str = "2026-09-06T10:00:00Z",
    ) -> dict:
        """O aviso do provedor sobre um repasse (01b :367-374): a liquidação
        confirmada, por padrão, com a data-valor do exemplo do 01b."""
        return {
            "provider_reference": provider_reference,
            "event_type": event_type,
            "outbox_key": outbox_key,
            "value_date": value_date,
        }

    @staticmethod
    def create_reversal_payload(amount_in_cents: int = None, actor: str = "erp-alfa", reason: str = None) -> dict:
        """O estorno de uma transação (RFC :151): total, sem valor. O valor
        e o motivo ausentes ficam fora do corpo."""
        payload = {"actor": actor}

        if amount_in_cents is not None:
            payload["amount_in_cents"] = amount_in_cents

        if reason is not None:
            payload["reason"] = reason

        return payload

    @staticmethod
    def create_med_payload(
        end_to_end_id: str,
        amount_in_cents: int = 640000,
        provider_reference: str = None,
        value_date: str = "2026-09-06T10:00:00Z",
    ) -> dict:
        """O aviso de MED do provedor (01b :375-380): a entrada do
        `end_to_end_id` devolvida, inteira por padrão. A referência padrão é
        "PRV-" + `end_to_end_id` + "-MED", na forma da liquidação."""
        if provider_reference is None:
            provider_reference = "PRV-" + end_to_end_id + "-MED"

        return {
            "provider_reference": provider_reference,
            "event_type": "med_return",
            "end_to_end_id": end_to_end_id,
            "amount_in_cents": amount_in_cents,
            "value_date": value_date,
        }

    @staticmethod
    def create_wallet_payload(
        party_key: str = "22222222-2222-4222-8222-222222222222",
        actor: str = "erp-alfa",
    ) -> dict:
        """A abertura da carteira da Ana (2222…), que o Cadastro dá como
        ativa (RFC :146)."""
        return {
            "party_key": party_key,
            "actor": actor,
        }

    @staticmethod
    def create_wallet_inflow_payload(
        contract_key: str,
        source_wallet_key: str,
        amount_in_cents: int = 300000,
        period_reference: str = "2026-09",
        actor: str = "erp-alfa",
    ) -> dict:
        """O aluguel de setembro pago com a carteira (remodelagem/10
        :104-109): sem pagador e sem `end_to_end_id`, que saem da carteira
        e não do corpo."""
        return {
            "amount_in_cents": amount_in_cents,
            "contract_key": contract_key,
            "period_reference": period_reference,
            "source_wallet_key": source_wallet_key,
            "actor": actor,
        }

    @staticmethod
    def create_deposit_payload(
        wallet_key: str,
        amount_in_cents: int = 450000,
        end_to_end_id: str = None,
        actor: str = "erp-alfa",
    ) -> dict:
        """O depósito por Pix na carteira (G:405-409): sem contrato e sem
        competência. O `end_to_end_id` padrão é o da entrada por Pix, com
        11 caracteres aleatórios no fim: único no ledger."""
        if end_to_end_id is None:
            end_to_end_id = "E00000000202609051422" + uuid4().hex[:11]

        return {
            "amount_in_cents": amount_in_cents,
            "wallet_key": wallet_key,
            "end_to_end_id": end_to_end_id,
            "actor": actor,
        }

    @staticmethod
    def create_status_payload(status: str, actor: str = "erp-alfa", reason: str = None) -> dict:
        """A mudança de status da conta (RFC :145), como o ERP a manda.
        O motivo ausente fica fora do corpo."""
        payload = {"status": status, "actor": actor}

        if reason is not None:
            payload["reason"] = reason

        return payload
