-- Loop: end-of-day TVL, borrows and utilization per market (chart-ready).
-- Parameters: {{namespace}} (text)
with obs as (
    select *
    from (
        select o.*, row_number() over (partition by series_id, ts order by ingested_at desc) as rn
        from dune.{{namespace}}.loop_observations as o
    )
    where rn = 1
      and entity_type = 'pool'
      and metric in ('expected_liquidity', 'total_borrowed')
),
eod as (
    -- last sample of each UTC day per series
    select *
    from (
        select
            obs.*,
            date_trunc('day', ts) as day,
            row_number() over (partition by series_id, date_trunc('day', ts) order by ts desc) as d
        from obs
    )
    where d = 1
)
select
    day,
    e.market_id,
    m.underlying_symbol,
    max(value) filter (where metric = 'expected_liquidity') as tvl,
    max(value) filter (where metric = 'total_borrowed')     as borrowed,
    max(value) filter (where metric = 'total_borrowed')
        / nullif(max(value) filter (where metric = 'expected_liquidity'), 0) as utilization
from eod as e
left join dune.{{namespace}}.loop_markets as m on m.market_id = e.market_id
group by 1, 2, 3
order by 2, 1
