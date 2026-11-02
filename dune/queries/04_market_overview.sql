-- Loop: latest state, all-time peak and drawdown per market (counter/table widgets).
-- Parameters: {{namespace}} (text)
with obs as (
    select *
    from (
        select o.*, row_number() over (partition by series_id, ts order by ingested_at desc) as rn
        from dune.{{namespace}}.loop_observations as o
    )
    where rn = 1 and entity_type = 'pool'
),
tvl as (
    select market_id, ts, value as tvl
    from obs
    where metric = 'expected_liquidity'
),
latest as (
    select market_id, max(ts) as ts from tvl group by 1
),
peak as (
    select market_id, max_by(ts, tvl) as peak_ts, max(tvl) as peak_tvl from tvl group by 1
)
select
    m.market_id,
    m.name,
    m.chain,
    m.underlying_symbol,
    l.ts                                                   as as_of,
    t.tvl                                                  as tvl,
    max(o.value) filter (where o.metric = 'total_borrowed') as borrowed,
    max(o.value) filter (where o.metric = 'supply_rate')    as supply_apr,
    max(o.value) filter (where o.metric = 'borrow_rate')    as borrow_apr,
    p.peak_tvl,
    p.peak_ts,
    1 - t.tvl / nullif(p.peak_tvl, 0)                      as drawdown_from_peak
from dune.{{namespace}}.loop_markets as m
join latest as l on l.market_id = m.market_id
join tvl as t on t.market_id = l.market_id and t.ts = l.ts
join peak as p on p.market_id = m.market_id
join obs as o on o.market_id = l.market_id and o.ts = l.ts
group by 1, 2, 3, 4, 5, 6, 10, 11
order by m.market_id
