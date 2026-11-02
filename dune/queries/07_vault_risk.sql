-- Loop: liquidation proximity per vault and day.
-- capacity_used = LTV x liquidation ratio (>= 1 means liquidatable at the vault's oracle);
-- drop_to_liquidation = collateral price fall that would make the aggregate liquidatable.
-- Mirrors the risk columns of loop.vault_daily. Parameters: {{namespace}} (text)
with obs as (
    select *
    from (
        select o.*, row_number() over (partition by series_id, ts order by ingested_at desc) as rn
        from dune.{{namespace}}.loop_observations as o
    )
    where rn = 1 and entity_type = 'vault'
),
eod as (
    select market_id, entity_id as vault_id, date_trunc('day', ts) as day, metric, value
    from (
        select obs.*, row_number() over (partition by series_id, date_trunc('day', ts) order by ts desc) as d
        from obs
    )
    where d = 1
),
pivot as (
    select
        market_id,
        vault_id,
        day,
        max(value) filter (where metric = 'collateral_balance') * max(value) filter (where metric = 'spot_price') as collateral_value,
        max(value) filter (where metric = 'total_debt')          as total_debt,
        max(value) filter (where metric = 'liquidation_ratio')   as liquidation_ratio
    from eod
    group by 1, 2, 3
)
select
    p.market_id,
    p.vault_id,
    v.name                                                        as vault_name,
    p.day,
    p.collateral_value,
    p.total_debt,
    p.total_debt / nullif(p.collateral_value, 0)                  as ltv,
    p.liquidation_ratio,
    p.total_debt / nullif(p.collateral_value, 0) * p.liquidation_ratio as capacity_used,
    greatest(0, 1 - p.total_debt / nullif(p.collateral_value, 0) * p.liquidation_ratio) as drop_to_liquidation
from pivot as p
left join dune.{{namespace}}.loop_vaults as v
    on v.market_id = p.market_id and v.vault_id = p.vault_id
where p.total_debt > 0
order by p.market_id, p.vault_id, p.day
