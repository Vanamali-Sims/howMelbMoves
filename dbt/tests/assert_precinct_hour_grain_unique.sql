select
    precinct,
    sensing_date,
    hourday
from {{ ref('mart_precinct_hour') }}
group by precinct, sensing_date, hourday
having count(*) > 1
