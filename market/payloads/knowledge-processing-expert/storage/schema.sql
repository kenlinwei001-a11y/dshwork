-- 知识抽取项目 PG schema（9 张表，对应 spec.py 的 PG_TABLES）
CREATE TABLE IF NOT EXISTS corpus (
    id            TEXT PRIMARY KEY,
    manifest_json JSONB NOT NULL,
    created_at    TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS corpus_meta (
    id          TEXT PRIMARY KEY,
    title       TEXT,
    doc_type    TEXT,
    data_cutoff TEXT,
    lang        TEXT,
    source_sha  TEXT
);

CREATE TABLE IF NOT EXISTS corpus_provenance (
    id           TEXT PRIMARY KEY,
    obj_type     TEXT,
    obj_id       TEXT,
    derived_from JSONB,
    stage        TEXT,
    ts           TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS evidence (
    id       TEXT PRIMARY KEY,
    claim_id TEXT,
    doc      TEXT,
    page     INTEGER,
    span     JSONB,
    kind     TEXT,
    status   TEXT
);

CREATE TABLE IF NOT EXISTS decisions (
    id            TEXT PRIMARY KEY,
    derivation_id TEXT,
    decision      TEXT,
    rationale     TEXT,
    ts            TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS gate_report (
    id        TEXT PRIMARY KEY,
    corpus_id TEXT,
    gate      TEXT,
    blockers  JSONB,
    ts        TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS style_profile (
    id            TEXT PRIMARY KEY,
    corpus_id     TEXT,
    features_json JSONB,
    version       INTEGER
);

CREATE TABLE IF NOT EXISTS node_mention (
    node_id  TEXT,
    chunk_id TEXT,
    span     JSONB,
    role     TEXT,
    PRIMARY KEY (node_id, chunk_id)
);

CREATE TABLE IF NOT EXISTS term (
    id        TEXT PRIMARY KEY,
    surface   TEXT,
    canonical TEXT,
    domain    TEXT,
    freq      INTEGER
);
