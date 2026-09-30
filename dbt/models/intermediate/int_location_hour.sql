with counts as (
    select * from {{ ref('stg_pedestrian_counts') }}
),

sensors as (
    select * from {{ ref('stg_sensor_locations') }}
),

weather as (
    select * from {{ ref('stg_weather_hourly') }}
),

holidays as (
    select
        holiday_date,
        string_agg(holiday_name, ', ' order by holiday_name) as holiday_name
    from {{ ref('stg_public_holidays') }}
    group by holiday_date
),

terms_by_day as (
    select
        counts.sensing_date,
        count(distinct terms.term) as school_term_count,
        case
            when count(distinct terms.term) = 1 then min(terms.term)
        end as school_term
    from counts
    inner join {{ ref('stg_school_terms') }} as terms
        on counts.sensing_date between terms.start_date and terms.end_date
    group by counts.sensing_date
),

events_by_day as (
    select
        counts.sensing_date,
        count(distinct events.event_id) as event_count,
        string_agg(distinct events.event_name, ', ' order by events.event_name) as event_names
    from counts
    inner join {{ ref('stg_major_events') }} as events
        on counts.sensing_date between events.start_date and events.end_date
    group by counts.sensing_date
)

select
    counts.location_id,
    counts.sensing_date,
    counts.hourday,
    counts.observed_at,
    counts.pedestriancount,
    counts.direction_1_count,
    counts.direction_2_count,
    counts.sensor_name as count_sensor_name,
    sensors.sensor_description,
    sensors.sensor_name as location_sensor_name,
    sensors.direction_1_label,
    sensors.direction_2_label,
    sensors.latitude,
    sensors.longitude,
    sensors.location_type,
    sensors.status as sensor_status,
    sensors.installation_date,
    weather.temperature_2m,
    weather.precipitation,
    weather.rain,
    weather.wind_speed_10m,
    weather.cloud_cover,
    holidays.holiday_name,
    holidays.holiday_name is not null as is_public_holiday,
    terms_by_day.school_term,
    coalesce(terms_by_day.school_term_count, 0) > 0 as is_school_term,
    coalesce(events_by_day.event_count, 0) as event_count,
    events_by_day.event_names,
    events_by_day.event_names is not null as is_event_day
from counts
left join sensors
    on counts.location_id = sensors.location_id
left join weather
    on counts.sensing_date = weather.sensing_date
    and counts.hourday = weather.hourday
left join holidays
    on counts.sensing_date = holidays.holiday_date
left join terms_by_day
    on counts.sensing_date = terms_by_day.sensing_date
left join events_by_day
    on counts.sensing_date = events_by_day.sensing_date
