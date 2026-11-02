-- Loop: share of each market's vault debt per vault, and the Herfindahl index (HHI).
-- Mirrors loop.vault_share_daily / loop.market_concentration_daily. Parameters: {{namespace}}
with obs as (
    select *
    from (
        select o.*, row_number() over (partition by series_id, ts order by ingested_at desc) as rn
        from dune.{{namespace}}.loop_observations as o
    )
    where rn = 1 and entity_type = 'vault' and metric = 'total_debt'
),
eod as (
    select market_id, entity_id as vault_id, date_trunc('day', ts) as day, value as total_debt
    from (
        select obs.*, row_number() over (partition by series_id, date_trunc('day', ts) order by ts desc) as d
        from obs
    )
    where d = 1
),
shares as (
    select *, total_debt / nullif(sum(total_debt) over (partition by market_id, day), 0) as debt_share
    from eod
)
select
    market_id,
    day,
    sum(debt_share * debt_share)              as debt_hhi,
    max(debt_share)                           as top_vault_share,
    count_if(total_debt > 0)                  as borrowing_vaults
from shares
group by 1, 2
order by 1, 2
