select count(*) as staged_rows
from {{ ref('stg_pedestrian_counts') }}
having staged_rows != (select count(*) from {{ ref('int_location_hour') }})
