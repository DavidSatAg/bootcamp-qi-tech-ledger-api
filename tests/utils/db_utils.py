import re
from contextlib import contextmanager
from os import environ
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy import text
from sqlalchemy.exc import OperationalError


RESET_QUERIES = [
    "DROP SCHEMA public CASCADE;",
    "CREATE SCHEMA public;",
    "GRANT ALL ON SCHEMA public TO CURRENT_USER;",
    "GRANT ALL ON SCHEMA public TO public;",
]

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_FILE = PROJECT_ROOT / "database" / "database.sql"

DEFAULT_DATABASE_URL = "postgresql+psycopg2://bootcamp:bootcamp@localhost:5432/bootcamp"

DATABASE_OFFLINE = (
    "Não consegui falar com o banco em {host}:{port}.\n"
    "Ele precisa estar de pé pros testes rodarem. Suba com:  docker compose up\n"
    "Se ele já está de pé, confira a porta na DATABASE_URL do seu .env."
)


class DbUtils:
    """Apaga o banco inteiro e o recria do zero — quando alguém chama.

    Não existe limpeza automática neste projeto. O `rollback()` roda no
    teste que o chamar, na linha em que for chamado, e em mais lugar
    nenhum. Todos os testes dividem o mesmo banco, e cada um enxerga o
    que os anteriores deixaram pra trás.

    O nome engana um pouco: isto não desfaz uma transação. Ele derruba
    o schema `public` com tudo que estiver dentro e roda o
    `database/database.sql` de novo — tabelas vazias e os quatro status
    do INSERT de volta.

    Quando o seu teste precisa chamar: sempre que alguma asserção
    depender de QUANTAS linhas existem no banco — contar, listar,
    paginar, filtrar. Nesses casos `DbUtils.rollback()` é a primeira
    linha do teste, antes de criar qualquer coisa (o exemplo está em
    `tests/integration/test_sample_entities.py`). Um teste que só olha
    as entidades que ele mesmo criou, pela chave que recebeu de volta,
    não precisa de limpeza nenhuma — e fica mais rápido sem ela.

    A limpeza acontece pela mesma conexão que a aplicação usa (a
    DATABASE_URL), e não por um programa externo: quem tem Docker
    rodando já tem tudo que precisa.
    """

    @staticmethod
    def database_url() -> str:
        return environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)

    @staticmethod
    def rollback() -> None:
        engine = create_engine(DbUtils.database_url(), isolation_level="AUTOCOMMIT")

        try:
            with engine.connect() as connection:
                for query in RESET_QUERIES:
                    connection.exec_driver_sql(query)

                connection.exec_driver_sql(SCHEMA_FILE.read_text())
        except OperationalError:
            message = DATABASE_OFFLINE.format(host=engine.url.host, port=engine.url.port)
            raise RuntimeError(message) from None
        finally:
            engine.dispose()

    @staticmethod
    def truncate(table: str) -> None:
        """Manda `TRUNCATE <table>` ao banco e deixa o erro dele subir.

        Peça acrescentada pelo Ledger (fatia 03), com as quatro linhas:
        1. Princípio tocado: "`db_utils` só zera, nunca monta cenário".
        2. Por que não funciona sem: `TRUNCATE`/`UPDATE` em `ledger_entry`
           não existem por HTTP, e CU-F9/F10 e a D0005 ("Como se verifica")
           exigem a prova de que o banco os recusa.
        3. A peça, e por que é a menor: um método que só faz `TRUNCATE` de
           uma tabela e deixa o erro subir — o mínimo que prova CU-F10.
        4. O que não faz: não executa SQL livre, não insere, não atualiza,
           não lê resultado, não monta cenário.
        """
        if not re.fullmatch(r"[a-z_]+", table):
            raise ValueError(f"nome de tabela invalido: {table!r}")

        engine = create_engine(DbUtils.database_url(), isolation_level="AUTOCOMMIT")

        try:
            with engine.connect() as connection:
                connection.exec_driver_sql(f"TRUNCATE {table}")
        finally:
            engine.dispose()

    @staticmethod
    def update_first_row(table: str) -> None:
        """Manda `UPDATE <table> SET id = id` na primeira linha e deixa o erro
        do banco subir.

        Peça acrescentada pelo Ledger (fatia 05a), com as quatro linhas:
        1. Princípio tocado: "`db_utils` só zera, nunca monta cenário".
        2. Por que não funciona sem: `UPDATE`/`DELETE` nas tabelas
           append-only não existem por HTTP, e o gatilho só dispara com
           linha; CU-F9 exige a prova de que o banco os recusa.
        3. A peça, e por que é a menor: dois métodos de SQL fixo (este e o
           `delete_first_row`), sobre a linha de menor `id`, com o nome da
           tabela validado como no `truncate`.
        4. O que não faz: não executa SQL livre, não insere, não lê
           resultado, não monta cenário (o cenário nasce por HTTP).
        """
        if not re.fullmatch(r"[a-z_]+", table):
            raise ValueError(f"nome de tabela invalido: {table!r}")

        engine = create_engine(DbUtils.database_url(), isolation_level="AUTOCOMMIT")

        try:
            with engine.connect() as connection:
                connection.exec_driver_sql(f"UPDATE {table} SET id = id WHERE id = (SELECT MIN(id) FROM {table})")
        finally:
            engine.dispose()

    @staticmethod
    def delete_first_row(table: str) -> None:
        """Manda `DELETE FROM <table>` na primeira linha e deixa o erro do
        banco subir. As quatro linhas estão no `update_first_row`."""
        if not re.fullmatch(r"[a-z_]+", table):
            raise ValueError(f"nome de tabela invalido: {table!r}")

        engine = create_engine(DbUtils.database_url(), isolation_level="AUTOCOMMIT")

        try:
            with engine.connect() as connection:
                connection.exec_driver_sql(f"DELETE FROM {table} WHERE id = (SELECT MIN(id) FROM {table})")
        finally:
            engine.dispose()

    @staticmethod
    @contextmanager
    def hold_row_lock(ledger_account_key: str):
        """Trava uma conta com `FOR UPDATE`, numa conexão própria, pelo tempo
        do `with`; na saída, `ROLLBACK` solta a trava.

        Peça acrescentada pelo Ledger (fatia 08), com as quatro linhas:
        1. Princípio tocado: "`db_utils` só zera, nunca monta cenário".
        2. Por que não funciona sem: a ordem "entrada passa o passo 2 →
           encerramento commita → entrada grava o passo 7" não se produz por
           HTTP; o `Barrier` (CA-07) só a sorteia, e sem ela a RN-08 não tem
           vermelho.
        3. A peça, e por que é a menor: trava uma linha, em conexão própria,
           pelo tempo do `with`; não muda nada, e o `ROLLBACK` a solta.
        4. O que não faz: não escreve (`INSERT`, `UPDATE`, `DELETE`), não
           executa SQL livre, não lê dado para asserção, não monta cenário —
           o cenário nasce por `POST`.
        """
        engine = create_engine(DbUtils.database_url())

        try:
            with engine.connect() as connection:
                transaction = connection.begin()
                try:
                    connection.execute(
                        text("SELECT id FROM ledger_account WHERE ledger_account_key = :k FOR UPDATE"),
                        {"k": ledger_account_key},
                    )
                    yield
                finally:
                    transaction.rollback()
        finally:
            engine.dispose()

    @staticmethod
    @contextmanager
    def hold_transaction_lock(ledger_transaction_key: str):
        """Trava uma transação do ledger com `FOR UPDATE`, numa conexão
        própria, pelo tempo do `with`; na saída, `ROLLBACK` solta a trava.

        Peça acrescentada pelo Ledger (fatia 11), com as quatro linhas:
        1. Princípio tocado: "`db_utils` só zera, nunca monta cenário".
        2. Por que não funciona sem: a trava da original no estorno (G :460)
           só seria exposta por HTTP num estorno sem conta travável (ex.: o
           de uma liquidação), e só por sorteio; com a `COLLECTION`
           ordenando, nenhum vermelho determinístico.
        3. A peça, e por que é a menor: o `hold_row_lock` sobre
           `ledger_transaction`: uma linha, em conexão própria, pelo `with`;
           o `ROLLBACK` a solta.
        4. O que não faz: não escreve (`INSERT`, `UPDATE`, `DELETE`), não
           executa SQL livre, não lê dado para asserção, não monta cenário —
           o cenário nasce por `POST`.
        """
        engine = create_engine(DbUtils.database_url())

        try:
            with engine.connect() as connection:
                transaction = connection.begin()
                try:
                    connection.execute(
                        text("SELECT id FROM ledger_transaction WHERE ledger_transaction_key = :k FOR UPDATE"),
                        {"k": ledger_transaction_key},
                    )
                    yield
                finally:
                    transaction.rollback()
        finally:
            engine.dispose()
