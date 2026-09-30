select
    year,
    term,
    cast(start_date as date) as start_date,
    cast(end_date as date) as end_date,
    jurisdiction,
    source_note,
    ingested_at_utc
from {{ source('raw', 'vic_school_terms') }}
