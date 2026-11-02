-- Loop: daily TVL change split into interest accrued and net deposits, per market.
-- Mirrors loop.market_flows_daily. Exact identity:
--   tvl_t - tvl_{t-1} = supply_{t-1} (price_t - price_{t-1}) + (supply_t - supply_{t-1}) price_t
-- Parameters: {{namespace}} (text)
with obs as (
    select *
    from (
        select o.*, row_number() over (partition by series_id, ts order by ingested_at desc) as rn
        from dune.{{namespace}}.loop_observations as o
    )
    where rn = 1 and entity_type = 'pool'
      and metric in ('expected_liquidity', 'total_supply', 'total_borrowed')
),
eod as (  -- last sample of each UTC day
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
        max(value) filter (where metric = 'expected_liquidity') as tvl,
        max(value) filter (where metric = 'total_supply')       as lp_supply,
        max(value) filter (where metric = 'total_borrowed')     as borrowed
    from eod
    group by 1, 2
),
priced as (
    select *, if(lp_supply > 0, tvl / lp_supply) as lp_price from daily
)
select
    d.market_id,
    d.day,
    d.tvl - p.tvl                                 as tvl_change,
    p.lp_supply * (d.lp_price - p.lp_price)       as interest,
    (d.lp_supply - p.lp_supply) * d.lp_price      as net_flow,
    d.borrowed - p.borrowed                       as borrow_change
from priced as d
join priced as p on p.market_id = d.market_id and p.day = d.day - interval '1' day
order by d.market_id, d.day
