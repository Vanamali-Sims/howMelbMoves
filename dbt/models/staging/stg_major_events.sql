select
    event_id,
    event_name,
    venue,
    cast(start_date as date) as start_date,
    cast(end_date as date) as end_date,
    notes,
    year,
    ingested_at_utc
from {{ source('raw', 'major_events') }}
