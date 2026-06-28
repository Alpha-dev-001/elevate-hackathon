-- Sprint 4: per-brand customer accounts (RBAC role=customer). Idempotent.
CREATE TABLE IF NOT EXISTS customers (
    id              VARCHAR PRIMARY KEY,
    merchant_id     VARCHAR NOT NULL REFERENCES merchants(id),
    email           VARCHAR NOT NULL,
    hashed_password VARCHAR NOT NULL,
    name            VARCHAR NOT NULL DEFAULT '',
    created_at      BIGINT,
    CONSTRAINT uq_customer_store_email UNIQUE (merchant_id, email)
);
CREATE INDEX IF NOT EXISTS ix_customers_merchant_id ON customers (merchant_id);
CREATE INDEX IF NOT EXISTS ix_customers_email ON customers (email);
