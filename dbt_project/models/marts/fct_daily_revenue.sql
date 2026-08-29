-- Hardened daily revenue mart model.
-- Uses distinct active customer_ids to prevent revenue inflation in case
-- the upstream customer dimension has duplicate/overlapping active records (SCD Type 2 drift).

with completed_orders as (
    select *
    from {{ ref('stg_orders') }}
    where status = 'completed'
),
active_customers as (
    select distinct customer_id
    from {{ ref('stg_customers') }}
    where is_active = true
)
select
    o.order_date,
    count(*) as completed_order_rows,
    sum(o.amount_usd) as daily_revenue
from completed_orders o
left join active_customers c
    on o.customer_id = c.customer_id
group by 1
order by 1
