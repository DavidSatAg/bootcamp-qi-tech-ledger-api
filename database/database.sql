CREATE TABLE sample_entity_status(
    id		                        SERIAL PRIMARY KEY,
    enumerator                      VARCHAR(50) NOT NULL,
    created_at                      TIMESTAMP NOT NULL DEFAULT(NOW()),
    UNIQUE(enumerator)
);

INSERT INTO sample_entity_status (enumerator) VALUES
('created'),
('pending'),
('success'),
('failed');

CREATE TABLE sample_entity(
    id                              SERIAL PRIMARY KEY,
    sample_entity_key               CHAR(36) NOT NULL,
    status_id                       INTEGER NOT NULL REFERENCES sample_entity_status(id),
    sample_entity_data              JSONB NOT NULL,
    name                            VARCHAR(255) NOT NULL,
    email                           VARCHAR(255) NOT NULL,
    document_number                 CHAR(14) NOT NULL,
    birthdate                       DATE NOT NULL,
    counter                         INTEGER NOT NULL,
    created_at                      TIMESTAMP NOT NULL DEFAULT(NOW()),
    UNIQUE(sample_entity_key),
    UNIQUE(document_number),
    UNIQUE(email)
);

CREATE TABLE sample_entity_status_event(
    id                              SERIAL PRIMARY KEY,
    sample_entity_id                INTEGER NOT NULL REFERENCES sample_entity(id),
    status_id                       INTEGER NOT NULL REFERENCES sample_entity_status(id),
    event_datetime                  TIMESTAMP NOT NULL,
    created_at                      TIMESTAMP NOT NULL DEFAULT(NOW())
);

-- ====================================================================
-- LEDGER -- acrescentado pelo time. Nada acima desta linha mudou.
-- ====================================================================

CREATE FUNCTION append_only_guard() RETURNS TRIGGER AS $func$
BEGIN
    RAISE EXCEPTION USING MESSAGE = TG_TABLE_NAME || ' e append-only: corrija por lancamento contrario';
END;
$func$ LANGUAGE plpgsql;

-- --- Plano de contas ------------------------------------------------

CREATE TABLE ledger_account_type(
    id          SERIAL PRIMARY KEY,
    enumerator  VARCHAR(50) NOT NULL,
    -- asset: saldo = D - C. liability e equity: saldo = C - D
    side        VARCHAR(10) NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT(NOW()),
    UNIQUE(enumerator),
    CHECK (side IN ('asset', 'liability', 'equity'))
);
INSERT INTO ledger_account_type (enumerator, side) VALUES
('external', 'asset'),       -- a conta real na instituicao
('earmark',  'liability'),   -- dinheiro de terceiro com proposito
('own',      'liability'),   -- recursos livres: taxa da imobiliaria; carteira
('suspense', 'liability'),   -- entrou e nao se sabe de quem e
('clearing', 'liability'),   -- saiu daqui, nao chegou la
('revenue',  'equity');      -- receita da plataforma: e nossa

CREATE TABLE ledger_account_status(
    id          SERIAL PRIMARY KEY,
    enumerator  VARCHAR(50) NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT(NOW()),
    UNIQUE(enumerator)
);
INSERT INTO ledger_account_status (enumerator) VALUES ('active'), ('blocked'), ('closed');

CREATE TABLE purpose_code(
    id          SERIAL PRIMARY KEY,
    enumerator  VARCHAR(50) NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT(NOW()),
    UNIQUE(enumerator)
);
INSERT INTO purpose_code (enumerator) VALUES
('CASH'), ('UNALLOCATED'), ('TRANSIT'), ('OWN'), ('PLATFORM_FEE'), ('WALLET'),
('COLLECTION'), ('RENT'), ('IPTU'), ('CONDO'), ('WATER'), ('ELECTRICITY'), ('DEPOSIT');

-- A REGRA QUE DEFINE O PRODUTO. Negacao por padrao. Estorno NAO consulta.
-- As pernas external -> external de transferencia entre livros tambem nao.
CREATE TABLE purpose_rule(
    id                      SERIAL PRIMARY KEY,
    source_purpose_code_id  INTEGER NOT NULL REFERENCES purpose_code(id),
    target_purpose_code_id  INTEGER NOT NULL REFERENCES purpose_code(id),
    -- origem e destino precisam ter o mesmo contract_key
    requires_same_contract  BOOLEAN NOT NULL DEFAULT FALSE,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT(NOW()),
    UNIQUE(source_purpose_code_id, target_purpose_code_id),
    CHECK (source_purpose_code_id <> target_purpose_code_id)
);
INSERT INTO purpose_rule (source_purpose_code_id, target_purpose_code_id, requires_same_contract)
SELECT o.id, d.id, r.same_contract
FROM (VALUES
    ('CASH','COLLECTION',FALSE), ('CASH','UNALLOCATED',FALSE), ('CASH','DEPOSIT',FALSE), ('CASH','WALLET',FALSE),
    ('UNALLOCATED','COLLECTION',FALSE),
    ('COLLECTION','RENT',TRUE), ('COLLECTION','IPTU',TRUE), ('COLLECTION','CONDO',TRUE),
    ('COLLECTION','WATER',TRUE), ('COLLECTION','ELECTRICITY',TRUE), ('COLLECTION','OWN',FALSE),
    ('OWN','PLATFORM_FEE',FALSE),      -- a imobiliaria paga a plataforma
    ('PLATFORM_FEE','OWN',FALSE),      -- a plataforma devolve, se decidir
    ('OWN','COLLECTION',FALSE),        -- absorcao de prejuizo
    ('DEPOSIT','COLLECTION',TRUE),     -- caucao executada
    ('WALLET','COLLECTION',FALSE),     -- pagar o aluguel com a carteira
    ('RENT','TRANSIT',FALSE), ('IPTU','TRANSIT',FALSE), ('CONDO','TRANSIT',FALSE), ('WATER','TRANSIT',FALSE),
    ('ELECTRICITY','TRANSIT',FALSE), ('OWN','TRANSIT',FALSE), ('PLATFORM_FEE','TRANSIT',FALSE),
    ('DEPOSIT','TRANSIT',FALSE), ('WALLET','TRANSIT',FALSE),
    ('RENT','WALLET',FALSE), ('IPTU','WALLET',FALSE), ('CONDO','WALLET',FALSE), ('WATER','WALLET',FALSE),
    ('ELECTRICITY','WALLET',FALSE), ('OWN','WALLET',FALSE), ('PLATFORM_FEE','WALLET',FALSE), ('DEPOSIT','WALLET',FALSE),
    ('TRANSIT','CASH',FALSE),
    ('TRANSIT','RENT',FALSE), ('TRANSIT','IPTU',FALSE), ('TRANSIT','CONDO',FALSE), ('TRANSIT','WATER',FALSE),
    ('TRANSIT','ELECTRICITY',FALSE), ('TRANSIT','OWN',FALSE), ('TRANSIT','PLATFORM_FEE',FALSE),
    ('TRANSIT','DEPOSIT',FALSE), ('TRANSIT','WALLET',FALSE)
) AS r(origem, destino, same_contract)
JOIN purpose_code o ON o.enumerator = r.origem
JOIN purpose_code d ON d.enumerator = r.destino;     -- 43 pares

CREATE TABLE ledger_account(
    id                       SERIAL PRIMARY KEY,
    ledger_account_key       CHAR(36) NOT NULL,
    client_key               CHAR(36) NOT NULL,          -- de quem sao os livros
    contract_key             VARCHAR(36) NOT NULL DEFAULT '',
    ledger_account_type_id   INTEGER NOT NULL REFERENCES ledger_account_type(id),
    ledger_account_status_id INTEGER NOT NULL REFERENCES ledger_account_status(id),
    purpose_code_id          INTEGER NOT NULL REFERENCES purpose_code(id),
    -- dono economico e papel: copiados no provisionamento, NUNCA alterados
    owner_party_key          VARCHAR(36) NOT NULL DEFAULT '',
    owner_role               VARCHAR(20) NOT NULL DEFAULT '',
    currency                 CHAR(3) NOT NULL DEFAULT 'BRL',
    created_at               TIMESTAMPTZ NOT NULL DEFAULT(NOW()),
    UNIQUE(ledger_account_key),
    UNIQUE(client_key, ledger_account_type_id, purpose_code_id, contract_key, owner_party_key),
    CHECK (owner_role IN ('', 'landlord', 'administrator', 'platform', 'provider', 'holder')),
    CHECK ((owner_party_key = '') = (owner_role = ''))
);

CREATE TABLE ledger_account_status_event(
    id                  SERIAL PRIMARY KEY,
    ledger_account_id   INTEGER NOT NULL REFERENCES ledger_account(id),
    from_status_id      INTEGER REFERENCES ledger_account_status(id),
    to_status_id        INTEGER NOT NULL REFERENCES ledger_account_status(id),
    actor               VARCHAR(255) NOT NULL,
    reason              VARCHAR(255),
    trace_id            VARCHAR(64) NOT NULL,
    event_datetime      TIMESTAMPTZ NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT(NOW())
);

-- a copia imutavel de cada versao do split
CREATE TABLE split_snapshot(
    id                       SERIAL PRIMARY KEY,
    contract_key             VARCHAR(36) NOT NULL,
    split_version            INTEGER NOT NULL,
    -- de onde sai: COLLECTION nos itens; OWN na taxa da plataforma
    source_ledger_account_id INTEGER NOT NULL REFERENCES ledger_account(id),
    ledger_account_id        INTEGER NOT NULL REFERENCES ledger_account(id),
    allocation_type          VARCHAR(20) NOT NULL,
    percentage               NUMERIC(7,4),
    amount_in_cents          NUMERIC(20,0),
    rent_amount_in_cents     NUMERIC(20,0) NOT NULL,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT(NOW()),
    UNIQUE(contract_key, split_version, ledger_account_id),
    CHECK (allocation_type IN ('percentage', 'fixed', 'remainder'))
);

-- --- Nucleo contabil ------------------------------------------------

CREATE TABLE ledger_transaction_type(
    id          SERIAL PRIMARY KEY,
    enumerator  VARCHAR(50) NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT(NOW()),
    UNIQUE(enumerator)
);
INSERT INTO ledger_transaction_type (enumerator) VALUES     -- A ORDEM IMPORTA
('inflow'), ('allocation'), ('split'), ('internal'),
('payout'), ('settlement'), ('dispatch_return'), ('reversal');

CREATE TABLE ledger_transaction(
    id                          SERIAL PRIMARY KEY,
    ledger_transaction_key      CHAR(36) NOT NULL,
    ledger_transaction_type_id  INTEGER NOT NULL REFERENCES ledger_transaction_type(id),
    contract_key                VARCHAR(36) NOT NULL DEFAULT '',
    period_reference            VARCHAR(7)  NOT NULL DEFAULT '',
    split_version               INTEGER,
    -- de quem era: so na entrada. Declarado pelo ERP; verificado na carteira
    payer_party_key             VARCHAR(36) NOT NULL DEFAULT '',
    -- o Pix de entrada: e por ele que o MED acha o original
    end_to_end_id               VARCHAR(64),
    value_date                  TIMESTAMPTZ NOT NULL,
    actor                       VARCHAR(255) NOT NULL,
    reason                      VARCHAR(255),
    trace_id                    VARCHAR(64) NOT NULL,
    reverses_transaction_id     INTEGER REFERENCES ledger_transaction(id),
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT(NOW()),
    UNIQUE(ledger_transaction_key),
    UNIQUE(end_to_end_id)
);

CREATE TABLE ledger_entry(
    id                      SERIAL PRIMARY KEY,
    ledger_transaction_id   INTEGER NOT NULL REFERENCES ledger_transaction(id),
    ledger_account_id       INTEGER NOT NULL REFERENCES ledger_account(id),
    direction               CHAR(1) NOT NULL,
    amount_in_cents         NUMERIC(20,0) NOT NULL,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT(NOW()),
    CHECK (direction IN ('D', 'C')),
    CHECK (amount_in_cents > 0)
);

-- --- Trilho externo -------------------------------------------------

CREATE TABLE outbox_status(
    id          SERIAL PRIMARY KEY,
    enumerator  VARCHAR(50) NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT(NOW()),
    UNIQUE(enumerator)
);
INSERT INTO outbox_status (enumerator) VALUES
('pending'), ('in_flight'), ('sent'), ('settled'), ('failed'), ('dead');

CREATE TABLE outbox(
    id                          SERIAL PRIMARY KEY,
    outbox_key                  CHAR(36) NOT NULL,
    outbox_status_id            INTEGER NOT NULL REFERENCES outbox_status(id),
    ledger_transaction_id       INTEGER NOT NULL REFERENCES ledger_transaction(id),
    -- o dono da conta debitada. A chave Pix e lida do Cadastro a cada envio
    beneficiary_party_key       VARCHAR(36) NOT NULL,
    dispatch_idempotency_key    VARCHAR(255) NOT NULL,
    payload                     JSONB NOT NULL,             -- so valor e referencias
    attempt_count               INTEGER NOT NULL DEFAULT 0,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT(NOW()),
    UNIQUE(outbox_key),
    UNIQUE(dispatch_idempotency_key)
);

CREATE TABLE outbox_status_event(
    id              SERIAL PRIMARY KEY,
    outbox_id       INTEGER NOT NULL REFERENCES outbox(id),
    from_status_id  INTEGER REFERENCES outbox_status(id),
    to_status_id    INTEGER NOT NULL REFERENCES outbox_status(id),
    actor           VARCHAR(255) NOT NULL,
    reason          VARCHAR(255),
    trace_id        VARCHAR(64) NOT NULL,
    event_datetime  TIMESTAMPTZ NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT(NOW())
);

CREATE TABLE provider_event(
    id                  SERIAL PRIMARY KEY,
    provider_event_key  CHAR(36) NOT NULL,
    provider_reference  VARCHAR(255) NOT NULL,
    event_type          VARCHAR(50) NOT NULL,
    outbox_id           INTEGER REFERENCES outbox(id),      -- nulo no MED
    raw_payload         JSONB NOT NULL,
    received_at         TIMESTAMPTZ NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT(NOW()),
    UNIQUE(provider_event_key),
    UNIQUE(provider_reference)
);

-- --- Suporte --------------------------------------------------------

CREATE TABLE idempotency_record(
    id                  SERIAL PRIMARY KEY,
    client_key          CHAR(36) NOT NULL,
    endpoint            VARCHAR(255) NOT NULL,
    idempotency_key     VARCHAR(255) NOT NULL,
    request_fingerprint CHAR(64) NOT NULL,          -- SHA-256 dos bytes crus
    response_status     INTEGER NOT NULL,
    response_keys       JSONB NOT NULL DEFAULT '[]'::jsonb,
    expires_at          TIMESTAMPTZ NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT(NOW()),
    UNIQUE(client_key, endpoint, idempotency_key)
);

CREATE TABLE statement(
    id                      SERIAL PRIMARY KEY,
    statement_key           CHAR(36) NOT NULL,
    ledger_account_id       INTEGER NOT NULL REFERENCES ledger_account(id),
    period_start            TIMESTAMPTZ NOT NULL,
    period_end              TIMESTAMPTZ NOT NULL,
    previous_statement_id   INTEGER REFERENCES statement(id),
    supersedes_statement_id INTEGER REFERENCES statement(id),
    content_hash            CHAR(64) NOT NULL,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT(NOW()),
    UNIQUE(statement_key),
    UNIQUE(supersedes_statement_id)
);

-- --- Imutabilidade imposta pelo banco: dois gatilhos por tabela ------

CREATE TRIGGER ledger_entry_no_change BEFORE UPDATE OR DELETE ON ledger_entry FOR EACH ROW EXECUTE FUNCTION append_only_guard();
CREATE TRIGGER ledger_entry_no_truncate BEFORE TRUNCATE ON ledger_entry FOR EACH STATEMENT EXECUTE FUNCTION append_only_guard();
CREATE TRIGGER provider_event_no_change BEFORE UPDATE OR DELETE ON provider_event FOR EACH ROW EXECUTE FUNCTION append_only_guard();
CREATE TRIGGER provider_event_no_truncate BEFORE TRUNCATE ON provider_event FOR EACH STATEMENT EXECUTE FUNCTION append_only_guard();
CREATE TRIGGER split_snapshot_no_change BEFORE UPDATE OR DELETE ON split_snapshot FOR EACH ROW EXECUTE FUNCTION append_only_guard();
CREATE TRIGGER split_snapshot_no_truncate BEFORE TRUNCATE ON split_snapshot FOR EACH STATEMENT EXECUTE FUNCTION append_only_guard();
CREATE TRIGGER ledger_account_status_event_no_change BEFORE UPDATE OR DELETE ON ledger_account_status_event FOR EACH ROW EXECUTE FUNCTION append_only_guard();
CREATE TRIGGER ledger_account_status_event_no_truncate BEFORE TRUNCATE ON ledger_account_status_event FOR EACH STATEMENT EXECUTE FUNCTION append_only_guard();
CREATE TRIGGER outbox_status_event_no_change BEFORE UPDATE OR DELETE ON outbox_status_event FOR EACH ROW EXECUTE FUNCTION append_only_guard();
CREATE TRIGGER outbox_status_event_no_truncate BEFORE TRUNCATE ON outbox_status_event FOR EACH STATEMENT EXECUTE FUNCTION append_only_guard();
CREATE TRIGGER ledger_transaction_no_change BEFORE UPDATE OR DELETE ON ledger_transaction FOR EACH ROW EXECUTE FUNCTION append_only_guard();
CREATE TRIGGER ledger_transaction_no_truncate BEFORE TRUNCATE ON ledger_transaction FOR EACH STATEMENT EXECUTE FUNCTION append_only_guard();
CREATE TRIGGER statement_no_change BEFORE UPDATE OR DELETE ON statement FOR EACH ROW EXECUTE FUNCTION append_only_guard();
CREATE TRIGGER statement_no_truncate BEFORE TRUNCATE ON statement FOR EACH STATEMENT EXECUTE FUNCTION append_only_guard();

-- --- Indices: so os das consultas que existem ------------------------

CREATE INDEX ledger_entry_by_account     ON ledger_entry (ledger_account_id, id);
CREATE INDEX ledger_entry_by_transaction ON ledger_entry (ledger_transaction_id);
CREATE INDEX ledger_account_by_client    ON ledger_account (client_key, id);
CREATE INDEX ledger_account_by_contract  ON ledger_account (contract_key) WHERE contract_key <> '';
CREATE INDEX ledger_account_by_owner     ON ledger_account (owner_party_key) WHERE owner_party_key <> '';
CREATE INDEX ledger_transaction_by_contract ON ledger_transaction (contract_key, period_reference, value_date);
CREATE INDEX ledger_transaction_by_payer ON ledger_transaction (payer_party_key) WHERE payer_party_key <> '';
CREATE INDEX outbox_by_status            ON outbox (outbox_status_id, id);
CREATE INDEX statement_by_account        ON statement (ledger_account_id, created_at DESC, id DESC);
-- uma divisao por contrato e competencia; 3 = 'split' pela ordem do seed
CREATE UNIQUE INDEX one_split_per_period ON ledger_transaction (contract_key, period_reference)
    WHERE ledger_transaction_type_id = 3;
