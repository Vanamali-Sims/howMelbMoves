select
    time as observed_at,
    cast(timezone('Australia/Melbourne', time) as date) as sensing_date,
    cast(extract('hour' from timezone('Australia/Melbourne', time)) as integer) as hourday,
    temperature_2m,
    precipitation,
    rain,
    wind_speed_10m,
    cloud_cover,
    ingested_at_utc
from {{ source('raw', 'open_meteo_archive') }}
