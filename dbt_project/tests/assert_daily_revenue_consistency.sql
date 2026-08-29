-- Singular test: daily revenue in fct_daily_revenue must exactly match
-- the sum of completed order amounts in stg_orders.

with order_sums as (
    select
        order_date,
        count(*) as expected_order_rows,
        sum(amount_usd) as expected_revenue
    from {{ ref('stg_orders') }}
    where status = 'completed'
    group by 1
)
select
    m.order_date,
    m.completed_order_rows,
    s.expected_order_rows,
    m.daily_revenue,
    s.expected_revenue
from {{ ref('fct_daily_revenue') }} m
join order_sums s on m.order_date = s.order_date
where m.completed_order_rows != s.expected_order_rows
   or abs(m.daily_revenue - s.expected_revenue) > 0.001
