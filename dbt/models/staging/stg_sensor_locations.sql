select
    location_id,
    sensor_description,
    sensor_name,
    try_cast(installation_date as date) as installation_date,
    note,
    location_type,
    status,
    direction_1 as direction_1_label,
    direction_2 as direction_2_label,
    latitude,
    longitude,
    ingested_at_utc
from {{ source('raw', 'pedestrian_sensor_locations') }}
