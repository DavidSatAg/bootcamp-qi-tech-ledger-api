import pytest

from tests.utils import DbUtils

APPEND_ONLY_TABLES = [
    "ledger_entry",
    "provider_event",
    "split_snapshot",
    "ledger_account_status_event",
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
        """As cinco tabelas append-only recusam TRUNCATE, cada uma com o proprio nome."""
        for tabela in APPEND_ONLY_TABLES:
            with pytest.raises(Exception, match=f"{tabela} e append-only"):
                DbUtils.truncate(tabela)

    def test_reset_restores_append_only_triggers(self):
        """O reset derruba o schema e relê o database.sql: os gatilhos voltam."""
        DbUtils.rollback()

        tabela = "ledger_entry"
        with pytest.raises(Exception, match=f"{tabela} e append-only"):
            DbUtils.truncate(tabela)
