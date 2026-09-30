select
    block_id,
    clue_small_area,
    avg(latitude) as latitude,
    avg(longitude) as longitude,
    count(*) as address_count
from {{ source('raw', 'clue_establishments_address_industry') }}
where cast(census_year as varchar) = '2024'
    and latitude is not null
    and longitude is not null
group by block_id, clue_small_area
