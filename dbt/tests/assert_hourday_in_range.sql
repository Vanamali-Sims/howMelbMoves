select
    location_id,
    sensing_date,
    hourday
from {{ ref('int_location_hour') }}
where hourday < 0 or hourday > 23
