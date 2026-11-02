-- Loop: realized lender APY from lpX share-price growth vs quoted supply APR.
-- Mirrors loop.market_yield_daily (30-day window shown; change the interval for 7/90).
-- Parameters: {{namespace}} (text)
with obs as (
    select *
    from (
        select o.*, row_number() over (partition by series_id, ts order by ingested_at desc) as rn
        from dune.{{namespace}}.loop_observations as o
    )
    where rn = 1 and entity_type = 'pool'
      and metric in ('expected_liquidity', 'total_supply', 'supply_rate', 'borrow_rate', 'total_borrowed')
),
eod as (
    select market_id, date_trunc('day', ts) as day, metric, value
    from (
        select obs.*, row_number() over (partition by series_id, date_trunc('day', ts) order by ts desc) as d
        from obs
    )
    where d = 1
),
daily as (
    select
        market_id,
        day,
        max(value) filter (where metric = 'expected_liquidity') / nullif(max(value) filter (where metric = 'total_supply'), 0) as lp_price,
        max(value) filter (where metric = 'supply_rate')     as supply_apr,
        max(value) filter (where metric = 'borrow_rate')     as borrow_apr,
        max(value) filter (where metric = 'total_borrowed') / nullif(max(value) filter (where metric = 'expected_liquidity'), 0) as utilization
    from eod
    group by 1, 2
)
select
    d.market_id,
    d.day,
    d.supply_apr,
    d.borrow_apr,
    power(d.lp_price / w.lp_price, 365.0 / 30) - 1                    as realized_apy_30d,
    d.supply_apr / nullif(d.borrow_apr * d.utilization, 0)            as pass_through
from daily as d
left join daily as w on w.market_id = d.market_id and w.day = d.day - interval '30' day
order by d.market_id, d.day
