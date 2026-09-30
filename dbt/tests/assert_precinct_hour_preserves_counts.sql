with location_totals as (
    select sum(pedestriancount) as total
    from {{ ref('int_location_hour') }} as lh
    inner join {{ ref('int_sensor_block_map') }} as map
        on lh.location_id = map.location_id
),

precinct_totals as (
    select sum(pedestriancount) as total
    from {{ ref('mart_precinct_hour') }}
)

select location_totals.total, precinct_totals.total
from location_totals
cross join precinct_totals
where location_totals.total != precinct_totals.total
