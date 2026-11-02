-- Loop: one row per (market, hour). Amounts in the market's underlying token.
-- Mirrors loop.market_hourly in supabase/migrations/*_analytics_views.sql.
-- Parameters: {{namespace}} (text)
with obs as (
    select *
    from (
        select o.*, row_number() over (partition by series_id, ts order by ingested_at desc) as rn
        from dune.{{namespace}}.loop_observations as o
    )
    where rn = 1
),
pivot as (
    select
        ts,
        market_id,
        max(value) filter (where entity_type = 'pool' and metric = 'total_supply')        as lp_supply,
        max(value) filter (where entity_type = 'pool' and metric = 'expected_liquidity')  as expected_liquidity,
        max(value) filter (where entity_type = 'pool' and metric = 'available_liquidity') as available_liquidity,
        max(value) filter (where entity_type = 'pool' and metric = 'total_borrowed')      as total_borrowed,
        max(value) filter (where entity_type = 'pool' and metric = 'borrow_rate')         as borrow_apr,
        max(value) filter (where entity_type = 'pool' and metric = 'supply_rate')         as supply_apr,
        max(value) filter (where entity_type = 'pool' and metric = 'locked_shares')       as locked_lp,
        max(value) filter (where entity_type = 'staking' and metric = 'total_supply')     as slp_supply,
        max(value) filter (where entity_type = 'staking' and metric = 'total_assets')     as staked_lp
    from obs
    where entity_type in ('pool', 'staking')
    group by 1, 2
)
select
    ts,
    market_id,
    expected_liquidity                                                   as tvl,
    available_liquidity,
    total_borrowed,
    if(expected_liquidity > 0, total_borrowed / expected_liquidity)       as utilization,
    borrow_apr,
    supply_apr,
    lp_supply,
    if(lp_supply > 0, expected_liquidity / lp_supply)                     as lp_price,
    slp_supply,
    if(slp_supply > 0, staked_lp / slp_supply)                            as slp_price,
    staked_lp * if(lp_supply > 0, expected_liquidity / lp_supply)         as staked_tvl,
    locked_lp * if(lp_supply > 0, expected_liquidity / lp_supply)         as locked_tvl
from pivot
order by market_id, ts
