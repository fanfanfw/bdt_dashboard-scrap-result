from django.db import migrations


VIEW_NAME = "cars_dashboard_combined"
VIEW_SQL = f"""
CREATE OR REPLACE VIEW {VIEW_NAME} AS
SELECT
    cu.id,
    cu.cars_standard_id,
    cu.source,
    cu.listing_id,
    cu.listing_url,
    cu.condition,
    cu.brand,
    cu.model,
    cu.variant,
    cu.series,
    cu.type,
    cu.year,
    cu.mileage,
    cu.transmission,
    cu.seat_capacity,
    cu.engine_cc,
    cu.fuel_type,
    cu.price,
    cu.location,
    cu.information_ads,
    cu.images,
    cu.status,
    cu.version,
    cu.created_at,
    cu.last_scraped_at,
    cu.information_ads_date,
    cu.id AS original_id,
    'cars_unified'::text AS origin_table,
    NULL::text AS reg_no,
    NULL::timestamptz AS carsome_created_at
FROM cars_unified cu

UNION ALL

SELECT
    1000000000::bigint + cs.id AS id,
    cs.cars_standard_id::bigint,
    'carsome'::varchar(20) AS source,
    NULL::text AS listing_id,
    CONCAT(
        'carsome-',
        COALESCE(NULLIF(TRIM(cs.reg_no), ''), cs.id::text)
    ) AS listing_url,
    'Used'::varchar(50) AS condition,
    cs.brand,
    cs.model,
    cs.variant,
    NULL::varchar(100) AS series,
    NULL::varchar(100) AS type,
    cs.year,
    cs.mileage,
    NULL::varchar(50) AS transmission,
    NULL::varchar(10) AS seat_capacity,
    NULL::varchar(50) AS engine_cc,
    NULL::varchar(50) AS fuel_type,
    cs.price,
    NULL::varchar(255) AS location,
    NULL::text AS information_ads,
    CASE
        WHEN cs.image IS NULL OR cs.image = ''
            THEN ARRAY[]::text[]
        ELSE ARRAY[cs.image]::text[]
    END AS images,
    cs.status,
    1 AS version,
    cs.created_at AS created_at,
    cs.last_updated_at AS last_scraped_at,
    COALESCE(cs.created_at::date, CURRENT_DATE) AS information_ads_date,
    cs.id AS original_id,
    'carsome'::text AS origin_table,
    cs.reg_no::text AS reg_no,
    cs.created_at AS carsome_created_at
FROM carsome cs;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("dashboard", "0005_carsinventory_carsome"),
    ]

    operations = [
        migrations.RunSQL(
            sql=VIEW_SQL,
            reverse_sql=f"DROP VIEW IF EXISTS {VIEW_NAME};",
        ),
    ]

