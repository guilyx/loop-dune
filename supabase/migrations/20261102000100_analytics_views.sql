-- Loop indexer: analysis views.
--
-- Wide, typed (float8) shapes for dashboards and notebooks. Derived metrics are
-- defined here, once, so the dashboard, ad-hoc SQL and the Dune queries in
-- dune/queries/ all agree on what "utilization" or "LTV" means.

-- One row per observation, with its catalogue context.
create or replace view loop.observations_enriched as
select
    o.ts,
    s.chain,
    s.chain_id,
    s.market_id,
    s.entity_type,
    s.entity_id,
    s.metric,
    s.unit,
    o.value,
    o.raw,
    o.block_number,
    o.series_id,
    o.ingested_at
from loop.observations o
join loop.series s using (series_id);

-- One row per (vault, hour).
create or replace view loop.vault_hourly as
with pivot as (
    select
        o.ts,
        s.market_id,
        s.entity_id as vault_id,
        max(o.value) filter (where s.metric = 'collateral_balance') as collateral_balance,
        max(o.value) filter (where s.metric = 'spot_price')         as spot_price,
        max(o.value) filter (where s.metric = 'total_debt')         as total_debt,
        max(o.value) filter (where s.metric = 'debt_ceiling')       as debt_ceiling,
        max(o.value) filter (where s.metric = 'pool_borrowed')      as pool_borrowed
    from loop.observations o
    join loop.series s using (series_id)
    where s.entity_type = 'vault'
    group by o.ts, s.market_id, s.entity_id
)
select
    ts,
    market_id,
    vault_id,
    collateral_balance::float8                 as collateral_balance,
    spot_price::float8                         as spot_price,
    (collateral_balance * spot_price)::float8  as collateral_value,   -- in underlying
    total_debt::float8                         as total_debt,          -- in underlying
    debt_ceiling::float8                       as debt_ceiling,
    pool_borrowed::float8                      as pool_borrowed,
    case
        when collateral_balance * spot_price > 0
        then (total_debt / (collateral_balance * spot_price))::float8
    end                                        as ltv
from pivot;

-- One row per (market, hour). Amounts are in the market's underlying token.
create or replace view loop.market_hourly as
with pivot as (
    select
        o.ts,
        s.market_id,
        max(o.value) filter (where s.entity_type = 'pool' and s.metric = 'total_supply')        as lp_supply,
        max(o.value) filter (where s.entity_type = 'pool' and s.metric = 'expected_liquidity')  as expected_liquidity,
        max(o.value) filter (where s.entity_type = 'pool' and s.metric = 'available_liquidity') as available_liquidity,
        max(o.value) filter (where s.entity_type = 'pool' and s.metric = 'total_borrowed')      as total_borrowed,
        max(o.value) filter (where s.entity_type = 'pool' and s.metric = 'borrow_rate')         as borrow_rate,
        max(o.value) filter (where s.entity_type = 'pool' and s.metric = 'supply_rate')         as supply_rate,
        max(o.value) filter (where s.entity_type = 'pool' and s.metric = 'locked_shares')       as locked_lp,
        max(o.value) filter (where s.entity_type = 'staking' and s.metric = 'total_supply')     as slp_supply,
        max(o.value) filter (where s.entity_type = 'staking' and s.metric = 'total_assets')     as staked_lp
    from loop.observations o
    join loop.series s using (series_id)
    where s.entity_type in ('pool', 'staking')
    group by o.ts, s.market_id
),
vaults as (
    select
        ts,
        market_id,
        sum(collateral_value) as collateral_value,
        sum(total_debt)       as vault_debt,
        count(*) filter (where collateral_balance > 0) as active_vaults
    from loop.vault_hourly
    group by ts, market_id
),
priced as (
    select
        p.*,
        case when lp_supply > 0 then expected_liquidity / lp_supply end as lp_price
    from pivot p
)
select
    p.ts,
    p.market_id,
    p.expected_liquidity::float8                                        as tvl,
    p.available_liquidity::float8                                       as available_liquidity,
    p.total_borrowed::float8                                            as total_borrowed,
    case when p.expected_liquidity > 0
         then (p.total_borrowed / p.expected_liquidity)::float8 end     as utilization,
    p.borrow_rate::float8                                               as borrow_apr,
    p.supply_rate::float8                                               as supply_apr,
    p.lp_supply::float8                                                 as lp_supply,
    p.lp_price::float8                                                  as lp_price,
    p.slp_supply::float8                                                as slp_supply,
    case when p.slp_supply > 0 then (p.staked_lp / p.slp_supply)::float8 end as slp_price,
    (p.staked_lp * p.lp_price)::float8                                  as staked_tvl,
    (p.locked_lp * p.lp_price)::float8                                  as locked_tvl,
    v.collateral_value                                                  as collateral_value,
    v.vault_debt                                                        as vault_debt,
    coalesce(v.active_vaults, 0)                                        as active_vaults
from priced p
left join vaults v using (ts, market_id);

-- End-of-day state (last hourly sample of each UTC day).
create or replace view loop.market_daily as
select distinct on (market_id, date_trunc('day', ts))
    date_trunc('day', ts) as day,
    m.*
from loop.market_hourly m
order by market_id, date_trunc('day', ts), ts desc;

create or replace view loop.vault_daily as
select distinct on (market_id, vault_id, date_trunc('day', ts))
    date_trunc('day', ts) as day,
    v.*
from loop.vault_hourly v
order by market_id, vault_id, date_trunc('day', ts), ts desc;

-- Latest value of every series.
create or replace view loop.series_latest as
select distinct on (o.series_id)
    o.series_id,
    s.market_id,
    s.entity_type,
    s.entity_id,
    s.metric,
    s.unit,
    o.ts,
    o.value,
    o.block_number
from loop.observations o
join loop.series s using (series_id)
order by o.series_id, o.ts desc;

-- Pipeline health: how far behind is each chain?
create or replace view loop.chain_freshness as
select
    chain_id,
    max(ts)                as last_snapshot,
    now() - max(ts)        as lag,
    count(*)               as snapshots,
    sum(failed_count)      as failed_calls
from loop.snapshots
group by chain_id;

grant select on all tables in schema loop to loop_reader;
