select
    id,
    location_id,
    cast(sensing_date as date) as sensing_date,
    hourday,
    direction_1 as direction_1_count,
    direction_2 as direction_2_count,
    pedestriancount,
    sensor_name,
    location.lon as longitude,
    location.lat as latitude,
    observed_at,
    ingested_at_utc
from {{ source('raw', 'pedestrian_hourly_counts') }}
