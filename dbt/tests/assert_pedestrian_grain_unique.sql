select
    location_id,
    sensing_date,
    hourday
from {{ ref('stg_pedestrian_counts') }}
group by location_id, sensing_date, hourday
having count(*) > 1
