-- Microsoft 365 Integration Schema
-- File: microsoft_integration/sql/001_microsoft_schema.sql
--
-- Safe to run multiple times (uses CREATE TABLE IF NOT EXISTS).
-- Never modifies Milo tables.
-- All Microsoft tables use the ms_ prefix.

SET NAMES utf8mb4;
SET CHARACTER SET utf8mb4;

-- -------------------------------------------------------------------------
-- ms_schema_version — tracks applied Microsoft migrations
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ms_schema_version (
    version     INT NOT NULL PRIMARY KEY,
    applied_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    description VARCHAR(200)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- -------------------------------------------------------------------------
-- ms_accounts — one row per connected Microsoft account
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ms_accounts (
    id                       INT          NOT NULL AUTO_INCREMENT PRIMARY KEY,
    microsoft_user_id        VARCHAR(100) NOT NULL UNIQUE,
    tenant_id                VARCHAR(100),
    display_name             VARCHAR(200) NOT NULL DEFAULT '',
    email                    VARCHAR(200) NOT NULL DEFAULT '',
    account_type             VARCHAR(20)  NOT NULL DEFAULT 'personal',
    enabled                  TINYINT(1)   NOT NULL DEFAULT 1,
    needs_reauthentication   TINYINT(1)   NOT NULL DEFAULT 0,
    created_at               DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at               DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    last_login_at            DATETIME,
    INDEX ix_ms_accounts_email  (email),
    INDEX ix_ms_accounts_enabled (enabled)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- -------------------------------------------------------------------------
-- ms_token_cache — encrypted MSAL token cache (one row per account)
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ms_token_cache (
    id              INT      NOT NULL AUTO_INCREMENT PRIMARY KEY,
    account_id      INT      NOT NULL UNIQUE,
    encrypted_cache LONGTEXT NOT NULL,
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_ms_token_cache_account
        FOREIGN KEY (account_id) REFERENCES ms_accounts(id) ON DELETE CASCADE,
    INDEX ix_ms_token_cache_account_id (account_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- -------------------------------------------------------------------------
-- ms_sync_targets — which Microsoft resources to sync per account
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ms_sync_targets (
    id             INT          NOT NULL AUTO_INCREMENT PRIMARY KEY,
    account_id     INT          NOT NULL,
    target_type    VARCHAR(20)  NOT NULL,
    remote_id      VARCHAR(400) NOT NULL,
    remote_name    VARCHAR(200) NOT NULL DEFAULT '',
    enabled        TINYINT(1)   NOT NULL DEFAULT 1,
    sync_direction VARCHAR(30)  NOT NULL DEFAULT 'bidirectional',
    created_at     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_ms_sync_targets_account
        FOREIGN KEY (account_id) REFERENCES ms_accounts(id) ON DELETE CASCADE,
    UNIQUE KEY uq_ms_sync_targets (account_id, target_type, remote_id),
    INDEX ix_ms_sync_targets_account_id (account_id),
    INDEX ix_ms_sync_targets_type (target_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- -------------------------------------------------------------------------
-- ms_entity_links — maps Milo entities ↔ Microsoft remote entities
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ms_entity_links (
    id                    INT          NOT NULL AUTO_INCREMENT PRIMARY KEY,
    account_id            INT          NOT NULL,
    local_entity_type     VARCHAR(20)  NOT NULL,
    local_entity_id       INT          NOT NULL,
    remote_entity_type    VARCHAR(30)  NOT NULL,
    remote_entity_id      VARCHAR(400) NOT NULL,
    remote_container_id   VARCHAR(400),
    remote_etag           VARCHAR(200),
    remote_last_modified  DATETIME,
    local_last_modified   DATETIME,
    sync_hash             VARCHAR(64),
    last_synced_at        DATETIME,
    remote_deleted        TINYINT(1)   NOT NULL DEFAULT 0,
    local_deleted         TINYINT(1)   NOT NULL DEFAULT 0,
    created_at            DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at            DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_ms_entity_links_account
        FOREIGN KEY (account_id) REFERENCES ms_accounts(id) ON DELETE CASCADE,
    UNIQUE KEY uq_ms_entity_links_local  (account_id, local_entity_type,  local_entity_id),
    UNIQUE KEY uq_ms_entity_links_remote (account_id, remote_entity_type, remote_entity_id),
    INDEX ix_ms_entity_links_account_id (account_id),
    INDEX ix_ms_entity_links_local       (local_entity_type,  local_entity_id),
    INDEX ix_ms_entity_links_remote      (remote_entity_type, remote_entity_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- -------------------------------------------------------------------------
-- ms_sync_state — delta tokens and incremental sync windows
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ms_sync_state (
    id                  INT          NOT NULL AUTO_INCREMENT PRIMARY KEY,
    account_id          INT          NOT NULL,
    resource_type       VARCHAR(20)  NOT NULL,
    resource_id         VARCHAR(400) NOT NULL,
    delta_link          LONGTEXT,
    last_sync_at        DATETIME,
    last_full_sync_at   DATETIME,
    sync_window_start   DATETIME,
    sync_window_end     DATETIME,
    created_at          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_ms_sync_state_account
        FOREIGN KEY (account_id) REFERENCES ms_accounts(id) ON DELETE CASCADE,
    UNIQUE KEY uq_ms_sync_state (account_id, resource_type, resource_id),
    INDEX ix_ms_sync_state_account_id (account_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- -------------------------------------------------------------------------
-- ms_sync_runs — history of sync operations
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ms_sync_runs (
    id                  INT         NOT NULL AUTO_INCREMENT PRIMARY KEY,
    account_id          INT         NOT NULL,
    started_at          DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at         DATETIME,
    status              VARCHAR(20) NOT NULL DEFAULT 'running',
    is_full_sync        TINYINT(1)  NOT NULL DEFAULT 0,
    is_dry_run          TINYINT(1)  NOT NULL DEFAULT 0,
    calendar_created    INT         NOT NULL DEFAULT 0,
    calendar_updated    INT         NOT NULL DEFAULT 0,
    calendar_deleted    INT         NOT NULL DEFAULT 0,
    tasks_created       INT         NOT NULL DEFAULT 0,
    tasks_updated       INT         NOT NULL DEFAULT 0,
    tasks_deleted       INT         NOT NULL DEFAULT 0,
    conflicts_detected  INT         NOT NULL DEFAULT 0,
    errors_count        INT         NOT NULL DEFAULT 0,
    CONSTRAINT fk_ms_sync_runs_account
        FOREIGN KEY (account_id) REFERENCES ms_accounts(id) ON DELETE CASCADE,
    INDEX ix_ms_sync_runs_account_id  (account_id),
    INDEX ix_ms_sync_runs_started_at  (started_at),
    INDEX ix_ms_sync_runs_status      (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- -------------------------------------------------------------------------
-- ms_sync_errors — per-entity errors during sync
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ms_sync_errors (
    id               INT          NOT NULL AUTO_INCREMENT PRIMARY KEY,
    sync_run_id      INT,
    account_id       INT          NOT NULL,
    entity_type      VARCHAR(30),
    local_entity_id  INT,
    remote_entity_id VARCHAR(400),
    error_code       VARCHAR(50),
    safe_message     TEXT         NOT NULL DEFAULT '',
    created_at       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved         TINYINT(1)   NOT NULL DEFAULT 0,
    CONSTRAINT fk_ms_sync_errors_account
        FOREIGN KEY (account_id) REFERENCES ms_accounts(id) ON DELETE CASCADE,
    CONSTRAINT fk_ms_sync_errors_run
        FOREIGN KEY (sync_run_id) REFERENCES ms_sync_runs(id) ON DELETE SET NULL,
    INDEX ix_ms_sync_errors_account_id   (account_id),
    INDEX ix_ms_sync_errors_sync_run_id  (sync_run_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- -------------------------------------------------------------------------
-- ms_sync_conflicts — both-sides-changed conflicts awaiting resolution
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ms_sync_conflicts (
    id                  INT          NOT NULL AUTO_INCREMENT PRIMARY KEY,
    account_id          INT          NOT NULL,
    entity_link_id      INT,
    entity_type         VARCHAR(30)  NOT NULL,
    local_entity_id     INT          NOT NULL,
    remote_entity_id    VARCHAR(400) NOT NULL,
    local_snapshot      LONGTEXT,
    remote_snapshot     LONGTEXT,
    local_modified_at   DATETIME,
    remote_modified_at  DATETIME,
    status              VARCHAR(20)  NOT NULL DEFAULT 'pending',
    resolution          VARCHAR(30),
    created_at          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_at         DATETIME,
    CONSTRAINT fk_ms_sync_conflicts_account
        FOREIGN KEY (account_id) REFERENCES ms_accounts(id) ON DELETE CASCADE,
    CONSTRAINT fk_ms_sync_conflicts_entity_link
        FOREIGN KEY (entity_link_id) REFERENCES ms_entity_links(id) ON DELETE SET NULL,
    INDEX ix_ms_sync_conflicts_account_id (account_id),
    INDEX ix_ms_sync_conflicts_status     (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- -------------------------------------------------------------------------
-- ms_subscriptions — Graph change notification subscriptions
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ms_subscriptions (
    id                    INT          NOT NULL AUTO_INCREMENT PRIMARY KEY,
    account_id            INT          NOT NULL,
    subscription_id       VARCHAR(200) NOT NULL UNIQUE,
    resource              VARCHAR(400) NOT NULL,
    change_type           VARCHAR(100) NOT NULL DEFAULT 'created,updated,deleted',
    expiration_datetime   DATETIME,
    client_state          VARCHAR(128) NOT NULL DEFAULT '',
    status                VARCHAR(20)  NOT NULL DEFAULT 'active',
    created_at            DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at            DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_ms_subscriptions_account
        FOREIGN KEY (account_id) REFERENCES ms_accounts(id) ON DELETE CASCADE,
    INDEX ix_ms_subscriptions_account_id (account_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- -------------------------------------------------------------------------
-- ms_auth_flows — in-progress device code authentication flows
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ms_auth_flows (
    id               INT          NOT NULL AUTO_INCREMENT PRIMARY KEY,
    flow_id          VARCHAR(64)  NOT NULL UNIQUE,
    device_code      LONGTEXT     NOT NULL,
    user_code        VARCHAR(20)  NOT NULL,
    verification_uri VARCHAR(300) NOT NULL,
    expires_at       DATETIME     NOT NULL,
    status           VARCHAR(20)  NOT NULL DEFAULT 'pending',
    account_id       INT,
    created_at       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_ms_auth_flows_account
        FOREIGN KEY (account_id) REFERENCES ms_accounts(id) ON DELETE SET NULL,
    INDEX ix_ms_auth_flows_flow_id  (flow_id),
    INDEX ix_ms_auth_flows_status   (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- -------------------------------------------------------------------------
-- Register schema version 1
-- -------------------------------------------------------------------------
INSERT IGNORE INTO ms_schema_version (version, description)
VALUES (1, 'Initial Microsoft integration schema');
