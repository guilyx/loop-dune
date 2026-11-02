-- Loop indexer: advanced analytics.
--
-- Everything here is derived from loop.observations through the earlier views, so the
-- dashboard, ad-hoc SQL and the Dune queries share one definition of each metric.
-- Daily views compare end-of-day states (loop.market_daily / loop.vault_daily).

-- ---------------------------------------------------------------------------- catalogue

-- When a series was first registered. A series added after a snapshot was taken is
-- missing from that snapshot; `loop-indexer run` re-reads it at the stored block.
alter table loop.series add column if not exists created_at timestamptz;
update loop.series set created_at = '-infinity' where created_at is null;
alter table loop.series alter column created_at set default now();
alter table loop.series alter column created_at set not null;

-- ---------------------------------------------------------------------------- vault risk

-- Same columns as before, plus liquidation parameters and how close each vault's
-- aggregate position is to them. Aggregates: individual positions can be riskier.
create or replace view loop.vault_hourly as
with pivot as (
    select
        o.ts,
        s.market_id,
        s.entity_id as vault_id,
        max(o.value) filter (where s.metric = 'collateral_balance')  as collateral_balance,
        max(o.value) filter (where s.metric = 'spot_price')          as spot_price,
        max(o.value) filter (where s.metric = 'total_debt')          as total_debt,
        max(o.value) filter (where s.metric = 'debt_ceiling')        as debt_ceiling,
        max(o.value) filter (where s.metric = 'pool_borrowed')       as pool_borrowed,
        max(o.value) filter (where s.metric = 'liquidation_ratio')   as liquidation_ratio,
        max(o.value) filter (where s.metric = 'liquidation_penalty') as liquidation_penalty
    from loop.observations o
    join loop.series s using (series_id)
    where s.entity_type = 'vault'
    group by o.ts, s.market_id, s.entity_id
),
valued as (
    select
        p.*,
        p.collateral_balance * p.spot_price as cv,
        case
            when p.collateral_balance * p.spot_price > 0
            then p.total_debt / (p.collateral_balance * p.spot_price)
        end as ltv_n
    from pivot p
)
select
    ts,
    market_id,
    vault_id,
    collateral_balance::float8                    as collateral_balance,
    spot_price::float8                            as spot_price,
    cv::float8                                    as collateral_value,
    total_debt::float8                            as total_debt,
    debt_ceiling::float8                          as debt_ceiling,
    pool_borrowed::float8                         as pool_borrowed,
    ltv_n::float8                                 as ltv,
    liquidation_ratio::float8                     as liquidation_ratio,
    liquidation_penalty::float8                   as liquidation_penalty,
    case when liquidation_ratio > 0 then (1 / liquidation_ratio)::float8 end as max_ltv,
    -- share of borrowing capacity in use; >= 1 means liquidatable at the vault's oracle
    (ltv_n * liquidation_ratio)::float8           as capacity_used,
    -- collateral price fall that would make the aggregate position liquidatable
    case
        when ltv_n > 0 and liquidation_ratio > 0
        then greatest(0, 1 - ltv_n * liquidation_ratio)::float8
    end                                           as drop_to_liquidation
from valued;

-- Recreate so the new columns flow through (v.* is expanded at creation time).
create or replace view loop.vault_daily as
select distinct on (market_id, vault_id, date_trunc('day', ts))
    date_trunc('day', ts) as day,
    v.*
from loop.vault_hourly v
order by market_id, vault_id, date_trunc('day', ts), ts desc;

-- ---------------------------------------------------------------------------- yield

-- Realized lender yield, annualized from lpX share-price growth over trailing windows
-- (includes any losses), next to the quoted rates. pass_through is the share of
-- borrower interest that reaches lenders: supply_apr / (borrow_apr x utilization).
create or replace view loop.market_yield_daily as
select
    d.market_id,
    d.day,
    d.supply_apr,
    d.borrow_apr,
    d.utilization,
    case when w7.lp_price > 0 and d.lp_price > 0
         then (power(d.lp_price / w7.lp_price, 365.0 / 7) - 1)::float8 end   as realized_apy_7d,
    case when w30.lp_price > 0 and d.lp_price > 0
         then (power(d.lp_price / w30.lp_price, 365.0 / 30) - 1)::float8 end as realized_apy_30d,
    case when w90.lp_price > 0 and d.lp_price > 0
         then (power(d.lp_price / w90.lp_price, 365.0 / 90) - 1)::float8 end as realized_apy_90d,
    case when d.borrow_apr * d.utilization > 0
         then (d.supply_apr / (d.borrow_apr * d.utilization))::float8 end     as pass_through
from loop.market_daily d
left join loop.market_daily w7
    on w7.market_id = d.market_id and w7.day = d.day - interval '7 days'
left join loop.market_daily w30
    on w30.market_id = d.market_id and w30.day = d.day - interval '30 days'
left join loop.market_daily w90
    on w90.market_id = d.market_id and w90.day = d.day - interval '90 days';

-- ---------------------------------------------------------------------------- flows

-- Day-over-day TVL change split exactly into interest accrued to existing shares and
-- net deposits (shares minted minus burned, at today's price):
--   tvl_t - tvl_{t-1} = supply_{t-1} (p_t - p_{t-1}) + (supply_t - supply_{t-1}) p_t
create or replace view loop.market_flows_daily as
select
    d.market_id,
    d.day,
    (d.tvl - p.tvl)::float8                              as tvl_change,
    (p.lp_supply * (d.lp_price - p.lp_price))::float8    as interest,
    ((d.lp_supply - p.lp_supply) * d.lp_price)::float8   as net_flow,
    (d.total_borrowed - p.total_borrowed)::float8        as borrow_change
from loop.market_daily d
join loop.market_daily p
    on p.market_id = d.market_id and p.day = d.day - interval '1 day';

-- ---------------------------------------------------------------------------- concentration

create or replace view loop.vault_share_daily as
select
    v.market_id,
    v.vault_id,
    v.day,
    v.total_debt,
    v.collateral_value,
    (v.total_debt / nullif(sum(v.total_debt) over w, 0))::float8             as debt_share,
    (v.collateral_value / nullif(sum(v.collateral_value) over w, 0))::float8 as collateral_share
from loop.vault_daily v
window w as (partition by v.market_id, v.day);

-- Herfindahl-Hirschman index of debt across vaults: 1 = one vault holds all debt.
create or replace view loop.market_concentration_daily as
select
    market_id,
    day,
    sum(debt_share * debt_share)::float8           as debt_hhi,
    max(debt_share)::float8                        as top_vault_share,
    count(*) filter (where total_debt > 0)         as borrowing_vaults
from loop.vault_share_daily
group by market_id, day;

-- ---------------------------------------------------------------------------- oracles

create or replace view loop.oracle_daily as
select
    market_id,
    vault_id,
    day,
    spot_price,
    lag(spot_price) over w                                        as prev_spot_price,
    case when lag(spot_price) over w > 0
         then (spot_price / lag(spot_price) over w - 1)::float8 end as spot_change
from loop.vault_daily
window w as (partition by market_id, vault_id order by day);

-- ---------------------------------------------------------------------------- data quality

create or replace view loop.coverage_daily as
select
    chain_id,
    date_trunc('day', ts)                                   as day,
    count(*)                                                as snapshots,
    sum(failed_count)                                       as failed_calls,
    max(extract(epoch from ts - block_timestamp))::float8   as max_block_lag_seconds
from loop.snapshots
group by chain_id, date_trunc('day', ts);

create or replace view loop.series_health as
select
    se.series_id,
    se.market_id,
    se.entity_type,
    se.entity_id,
    se.metric,
    (select count(*) from loop.observations o where o.series_id = se.series_id)   as observations,
    (select count(*) from loop.snapshots sn where se.series_id = any(sn.failed_series)) as reverted,
    (select max(o.ts) from loop.observations o where o.series_id = se.series_id)  as last_observed
from loop.series se;

grant select on all tables in schema loop to loop_reader;
