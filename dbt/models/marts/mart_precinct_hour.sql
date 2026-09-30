select
    map.clue_small_area as precinct,
    lh.sensing_date,
    lh.hourday,
    min(lh.observed_at) as observed_at,
    sum(lh.pedestriancount) as pedestriancount,
    count(distinct lh.location_id) as sensor_count,
    max(lh.temperature_2m) as temperature_2m,
    max(lh.precipitation) as precipitation,
    max(lh.rain) as rain,
    max(lh.wind_speed_10m) as wind_speed_10m,
    max(lh.cloud_cover) as cloud_cover,
    max(lh.holiday_name) as holiday_name,
    bool_or(lh.is_public_holiday) as is_public_holiday,
    max(lh.school_term) as school_term,
    bool_or(lh.is_school_term) as is_school_term,
    max(lh.event_count) as event_count,
    max(lh.event_names) as event_names,
    bool_or(lh.is_event_day) as is_event_day
from {{ ref('int_location_hour') }} as lh
inner join {{ ref('int_sensor_block_map') }} as map
    on lh.location_id = map.location_id
group by map.clue_small_area, lh.sensing_date, lh.hourday
