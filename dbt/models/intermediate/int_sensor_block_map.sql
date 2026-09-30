with sensors as (
    select
        location_id,
        latitude,
        longitude
    from {{ ref('stg_sensor_locations') }}
    where latitude is not null
        and longitude is not null
),

blocks as (
    select * from {{ ref('stg_clue_block_centroids') }}
),

ranked as (
    select
        sensors.location_id,
        blocks.block_id,
        blocks.clue_small_area,
        blocks.latitude as block_latitude,
        blocks.longitude as block_longitude,
        power(sensors.latitude - blocks.latitude, 2)
        + power(sensors.longitude - blocks.longitude, 2) as distance_sq,
        row_number() over (
            partition by sensors.location_id
            order by
                power(sensors.latitude - blocks.latitude, 2)
                + power(sensors.longitude - blocks.longitude, 2)
        ) as match_rank
    from sensors
    cross join blocks
)

select
    location_id,
    block_id,
    clue_small_area,
    block_latitude,
    block_longitude,
    distance_sq
from ranked
where match_rank = 1
