import pytest

from tests.utils import DbUtils, ObjectGenerator

APPEND_ONLY_TABLES = [
    "ledger_entry",
    "provider_event",
    "split_snapshot",
    "ledger_account_status_event",
    "outbox_status_event",
    "statement",
]
# A `ledger_transaction` fica fora daqui: outras tabelas a referenciam, e o
# Postgres recusa o TRUNCATE pela chave estrangeira antes de chegar ao
# gatilho `_no_truncate`. A prova dela é por linha, em ROW_GUARDED_TABLES.

# Todas as append-only, povoadas por HTTP no cenário do teste (CU-F9).
ROW_GUARDED_TABLES = [
    "ledger_entry",
    "split_snapshot",
    "ledger_account_status_event",
    "ledger_transaction",
    "statement",
    "provider_event",
    "outbox_status_event",
]


class TestAppendOnlyTriggers:
    def test_ledger_entry_truncate_is_refused(self):
        """CU-F10: nem o TRUNCATE apaga um lancamento.

        Quem recusa e o gatilho `ledger_entry_no_truncate` do
        database/database.sql: correcao e lancamento contrario.
        """
        tabela = "ledger_entry"
        with pytest.raises(Exception, match=f"{tabela} e append-only"):
            DbUtils.truncate(tabela)

    def test_append_only_tables_refuse_truncate(self):
        """As tabelas append-only recusam TRUNCATE, cada uma com o proprio nome."""
        for tabela in APPEND_ONLY_TABLES:
            with pytest.raises(Exception, match=f"{tabela} e append-only"):
                DbUtils.truncate(tabela)

    def test_reset_restores_append_only_triggers(self):
        """O reset derruba o schema e relê o database.sql: os gatilhos voltam."""
        DbUtils.rollback()

        tabela = "ledger_entry"
        with pytest.raises(Exception, match=f"{tabela} e append-only"):
            DbUtils.truncate(tabela)

    def test_append_only_rows_refuse_update_and_delete(self):
        """CU-F9: nem UPDATE nem DELETE mudam uma linha gravada.

        O gatilho `<tabela>_no_change` só dispara com linha, por isso o
        cenário vem antes: um contrato provisionado, uma entrada, o extrato
        da conta de arrecadação e um repasse liquidado pelo provedor (o
        aviso grava `provider_event`; o repasse, `outbox_status_event`).
        """
        status, contract_ledger = ObjectGenerator.create_contract_ledger()
        assert status == 201, contract_ledger
        status, response, _payload = ObjectGenerator.create_inflow(contract_ledger["contract_key"])
        assert status == 201, response
        accounts = {account["purpose_code"]: account["ledger_account_key"] for account in contract_ledger["accounts"]}
        status, response, _payload = ObjectGenerator.create_statement(accounts["COLLECTION"])
        assert status == 201, response

        _contract_ledger, payout = ObjectGenerator.create_paid_out_contract()
        status, response, _payload = ObjectGenerator.create_settlement(payout["outbox"])
        assert status == 204, response

        for tabela in ROW_GUARDED_TABLES:
            with pytest.raises(Exception, match=f"{tabela} e append-only"):
                DbUtils.update_first_row(tabela)
            with pytest.raises(Exception, match=f"{tabela} e append-only"):
                DbUtils.delete_first_row(tabela)
