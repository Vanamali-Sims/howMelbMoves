select
    sensing_date,
    hourday
from {{ ref('stg_weather_hourly') }}
group by sensing_date, hourday
having count(*) > 1
