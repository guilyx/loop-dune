-- Loop indexer: core schema.
--
-- Long ("tidy") fact table: one row per (series, hour). Adding a metric is a registry
-- change, never a schema migration, and no two markets can drift into different
-- column layouts. Wide, analysis-friendly shapes are provided as views (next migration).
--
-- Idempotent on purpose: safe to apply with `supabase db push` *and* with
-- `loop-indexer db migrate` against a plain Postgres.

create schema if not exists loop;
comment on schema loop is 'Loop Protocol on-chain state, sampled hourly by loop-indexer.';

-- ---------------------------------------------------------------------------- catalogue

create table if not exists loop.markets (
    market_id           text primary key,
    name                text not null,
    chain               text not null,
    chain_id            integer not null,
    underlying_symbol   text not null,
    underlying_address  text not null,
    underlying_decimals smallint not null,
    pool_address        text not null,
    pool_symbol         text not null,
    staking_address     text,
    staking_symbol      text,
    start_block         bigint not null,
    updated_at          timestamptz not null default now()
);

create table if not exists loop.vaults (
    market_id           text not null references loop.markets (market_id),
    vault_id            text not null,
    name                text not null,
    address             text not null,
    collateral_symbol   text not null,
    collateral_address  text not null,
    collateral_decimals smallint not null,
    registered          boolean not null,
    deployed_block      bigint not null,
    notes               text,
    updated_at          timestamptz not null default now(),
    primary key (market_id, vault_id)
);

create table if not exists loop.series (
    series_id          text primary key,
    chain              text not null,
    chain_id           integer not null,
    market_id          text not null references loop.markets (market_id),
    entity_type        text not null check (entity_type in ('pool', 'staking', 'vault')),
    entity_id          text not null,
    metric             text not null,
    contract_address   text not null,
    function_signature text not null,
    call_args          jsonb not null default '[]',
    decimals           smallint not null,
    unit               text not null,
    description        text not null,
    active_from_block  bigint not null,
    updated_at         timestamptz not null default now(),
    unique (market_id, entity_type, entity_id, metric)
);

-- ---------------------------------------------------------------------------- facts

-- One row per (chain, grid timestamp) that was fully sampled. Gap detection is
-- "grid minus snapshots"; block numbers double as anchors for the block resolver.
create table if not exists loop.snapshots (
    chain_id        integer not null,
    ts              timestamptz not null,
    block_number    bigint not null,
    block_timestamp timestamptz not null,
    series_count    integer not null,
    failed_count    integer not null default 0,
    failed_series   text[] not null default '{}',
    ingested_at     timestamptz not null default now(),
    primary key (chain_id, ts),
    check (block_timestamp <= ts)
);

create table if not exists loop.observations (
    series_id    text not null references loop.series (series_id),
    ts           timestamptz not null,
    block_number bigint not null,
    raw          numeric(78, 0) not null,  -- exact uint256 as returned on-chain
    value        numeric not null,         -- raw / 10^decimals
    ingested_at  timestamptz not null default now(),
    primary key (series_id, ts)
);

create index if not exists observations_ts_idx on loop.observations (ts);
-- Keyset pagination for exporters: (ingested_at, series_id, ts) is unique and ordered.
create index if not exists observations_export_idx
    on loop.observations (ingested_at, series_id, ts);

-- ---------------------------------------------------------------------------- operations

create table if not exists loop.runs (
    run_id      bigint generated always as identity primary key,
    command     text not null,
    started_at  timestamptz not null default now(),
    finished_at timestamptz,
    status      text not null default 'running'
                check (status in ('running', 'succeeded', 'partial', 'failed')),
    params      jsonb not null default '{}',
    stats       jsonb not null default '{}',
    error       text
);

create table if not exists loop.export_cursors (
    destination    text primary key,
    ingested_at    timestamptz,
    series_id      text,
    ts             timestamptz,
    rows_exported  bigint not null default 0,
    updated_at     timestamptz not null default now()
);

-- ---------------------------------------------------------------------------- access

-- Read-only role for the dashboard and analysts. Create a login that inherits it:
--   create role dashboard login password '...' in role loop_reader;
do $$
begin
    if not exists (select 1 from pg_roles where rolname = 'loop_reader') then
        create role loop_reader nologin;
    end if;
end
$$;

grant usage on schema loop to loop_reader;
grant select on all tables in schema loop to loop_reader;
alter default privileges in schema loop grant select on tables to loop_reader;
