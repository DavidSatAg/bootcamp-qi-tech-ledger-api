import hashlib
from datetime import datetime, timezone
from uuid import uuid4

from tests.utils import ObjectGenerator, RequestGenerator

TX1_VALUE_DATE = "2026-09-05T14:22:00Z"
# Instante com fração: prova que o texto do hash leva os microssegundos (A2).
LATER_VALUE_DATE = "2026-09-12T08:00:00.250000Z"


def a2_instant(value: str) -> str:
    """O instante da resposta no formato do texto do hash: UTC,
    microssegundos e `Z` (spec 13, decisão A2)."""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def a2_field(value) -> str:
    """Nulo vira vazio (RN-02)."""
    return "" if value is None else str(value)


def recompute_content_hash(statement: dict, previous_content_hash: str) -> str:
    """O hash do extrato refeito como um verificador externo faria, só com a
    resposta HTTP e a spec 13 (RN-02, RN-03, A1, A2): cabeçalho e linhas em
    ordem `(value_date, id)`, `|` sem espaços, `\\n` sem final, UTF-8,
    SHA-256 em hex minúsculo."""
    header = [
        statement["ledger_account_key"],
        a2_instant(statement["period_start"]),
        a2_instant(statement["period_end"]),
        previous_content_hash,
    ]
    text_lines = ["|".join(header)]
    ordered = sorted(statement["lines"], key=lambda line: (a2_instant(line["value_date"]), line["id"]))

    for line in ordered:
        fields = [
            a2_field(line["id"]),
            line["direction"],
            a2_field(line["amount_in_cents"]),
            a2_instant(line["value_date"]),
            line["ledger_transaction_key"],
            line["transaction_type"],
            a2_field(line["contract_key"]),
            a2_field(line["period_reference"]),
            a2_field(line["split_version"]),
            a2_field(line["payer_party_key"]),
        ]
        text_lines.append("|".join(fields))

    return hashlib.sha256("\n".join(text_lines).encode("utf-8")).hexdigest()


def provision_with_tx1() -> tuple:
    """Um contrato novo com a TX1 de setembro; devolve (contract_key, chave da COLLECTION)."""
    status, contract_ledger = ObjectGenerator.create_contract_ledger()
    assert status == 201, contract_ledger

    accounts = {account["purpose_code"]: account["ledger_account_key"] for account in contract_ledger["accounts"]}

    status, inflow, _payload = ObjectGenerator.create_inflow(contract_ledger["contract_key"], value_date=TX1_VALUE_DATE)
    assert status == 201, inflow

    return contract_ledger["contract_key"], accounts["COLLECTION"]


class TestStatementGet:
    def test_statement_get_hash_is_reproducible(self):
        _contract_key, collection_key = provision_with_tx1()

        status, august, _payload = ObjectGenerator.create_statement(
            collection_key, period_start="2026-08-01T00:00:00Z", period_end="2026-09-01T00:00:00Z"
        )
        assert status == 201, august
        status, september, _payload = ObjectGenerator.create_statement(collection_key)
        assert status == 201, september

        assert september["previous_statement_key"] == august["statement_key"]

        first_status, first_response = RequestGenerator.GET_statement(september["statement_key"])
        second_status, second_response = RequestGenerator.GET_statement(september["statement_key"])

        assert first_status == 200, first_response
        assert second_status == 200, second_response
        assert first_response == second_response
        assert first_response["content_hash"] == september["content_hash"]
        assert first_response["content_hash_matches"] is True

    def test_statement_get_original_unchanged_after_late_entry(self):
        contract_key, collection_key = provision_with_tx1()
        status, original, _payload = ObjectGenerator.create_statement(collection_key)
        assert status == 201, original

        status, late_inflow, _payload = ObjectGenerator.create_inflow(contract_key, value_date=TX1_VALUE_DATE)
        assert status == 201, late_inflow

        status, response = RequestGenerator.GET_statement(original["statement_key"])

        assert status == 200, response
        assert len(response["lines"]) == 1
        assert response["content_hash"] == original["content_hash"]
        assert response["content_hash_matches"] is True

    def test_statement_get_hash_recomputable_from_response(self):
        contract_key, collection_key = provision_with_tx1()
        for value_date, amount_in_cents in ((TX1_VALUE_DATE, 120000), (LATER_VALUE_DATE, 98765)):
            status, inflow, _payload = ObjectGenerator.create_inflow(
                contract_key, value_date=value_date, amount_in_cents=amount_in_cents
            )
            assert status == 201, inflow

        status, august, _payload = ObjectGenerator.create_statement(
            collection_key, period_start="2026-08-01T00:00:00Z", period_end="2026-09-01T00:00:00Z"
        )
        assert status == 201, august
        status, september, _payload = ObjectGenerator.create_statement(collection_key)
        assert status == 201, september

        status, august_response = RequestGenerator.GET_statement(august["statement_key"])
        assert status == 200, august_response
        status, september_response = RequestGenerator.GET_statement(september["statement_key"])
        assert status == 200, september_response
        status, previous = RequestGenerator.GET_statement(september_response["previous_statement_key"])
        assert status == 200, previous

        assert august_response["lines"] == []
        assert len(september_response["lines"]) == 3
        assert september_response["lines"] == september["lines"]
        assert all(isinstance(line["id"], int) for line in september_response["lines"])
        assert recompute_content_hash(august_response, "") == august["content_hash"]
        assert recompute_content_hash(september_response, previous["content_hash"]) == september["content_hash"]

    def test_statement_get_unknown_returns_404(self):
        status, response = RequestGenerator.GET_statement(str(uuid4()))

        assert status == 404, response
        assert response["code"] == "QIT001022"
