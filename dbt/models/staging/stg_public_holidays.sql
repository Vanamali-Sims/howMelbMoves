select
    cast(timezone('Australia/Melbourne', date) as date) as holiday_date,
    name as holiday_name,
    ingested_at_utc
from {{ source('raw', 'vic_public_holidays') }}
