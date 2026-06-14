import json
import re
import secrets
import time

from django.core.paginator import Paginator
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.db import DatabaseError, connection, transaction
from django.db.models import Count, Q

from ..models import CarsStandard, CarsStandardAuditLog, CarsStandardMaintenanceJob, CarsUnified, CarsUnifiedInd, Carsome


ALLOWED_TARGET_TABLES = {
    'cars_unified': {
        'model': CarsUnified,
        'source_column': 'source',
        'id_column': 'id',
        'required_columns': ['id', 'source', 'cars_standard_id', 'brand', 'model', 'variant'],
    },
    'carsome': {
        'model': Carsome,
        'source_column': 'source',
        'id_column': 'id',
        'required_columns': ['id', 'source', 'cars_standard_id', 'brand', 'model', 'variant'],
    },
    'cars_unified_ind': {
        'model': CarsUnifiedInd,
        'source_column': 'source',
        'id_column': 'id',
        'required_columns': ['id', 'source', 'cars_standard_id', 'brand', 'model', 'variant'],
    },
}

STANDARD_DISPLAY_COLUMNS = [
    'id',
    'brand_norm',
    'brand_raw',
    'brand_raw2',
    'model_group_norm',
    'model_group_raw',
    'model_norm',
    'model_raw',
    'model_raw2',
    'variant_norm',
    'variant_raw',
    'variant_raw2',
    'variant_raw3',
    'variant_raw4',
]

STANDARD_SEARCH_COLUMNS = [
    'brand_norm',
    'brand_raw',
    'brand_raw2',
    'model_group_norm',
    'model_group_raw',
    'model_norm',
    'model_raw',
    'model_raw2',
    'variant_norm',
    'variant_raw',
    'variant_raw2',
    'variant_raw3',
    'variant_raw4',
]

STANDARD_EDIT_COLUMNS = [
    'brand_norm',
    'brand_raw',
    'brand_raw2',
    'model_group_norm',
    'model_group_raw',
    'model_norm',
    'model_raw',
    'model_raw2',
    'variant_norm',
    'variant_raw',
    'variant_raw2',
    'variant_raw3',
    'variant_raw4',
]

NORMALIZED_FIELDS = {'brand_norm', 'model_group_norm', 'model_norm', 'variant_norm'}

ALIAS_FIELD_GROUPS = {
    'brand': {
        'source_fields': ['brand_norm', 'brand_raw', 'brand_raw2'],
        'target_fields': ['brand_raw', 'brand_raw2'],
    },
    'model_group': {
        'source_fields': ['model_group_norm', 'model_group_raw'],
        'target_fields': ['model_group_raw'],
    },
    'model': {
        'source_fields': ['model_norm', 'model_raw', 'model_raw2'],
        'target_fields': ['model_raw', 'model_raw2'],
    },
    'variant': {
        'source_fields': ['variant_norm', 'variant_raw', 'variant_raw2', 'variant_raw3', 'variant_raw4'],
        'target_fields': ['variant_raw', 'variant_raw2', 'variant_raw3', 'variant_raw4'],
    },
}

MERGE_PREVIEW_TOKEN_MAX_AGE = 15 * 60
MERGE_PREVIEW_TOKEN_SALT = 'dashboard.cars_standard.merge_preview'
INSERT_MISSING_PREVIEW_TOKEN_MAX_AGE = 15 * 60
INSERT_MISSING_PREVIEW_TOKEN_SALT = 'dashboard.cars_standard.insert_missing_preview'
FILL_PREVIEW_TOKEN_MAX_AGE = 15 * 60
FILL_PREVIEW_TOKEN_SALT = 'dashboard.cars_standard.fill_preview'
MODEL_GROUP_DEFAULT = 'NO MODEL GROUP'
NULLISH_VALUES = ('', '-', 'N/A', 'NA', 'NULL', 'NONE')
FILL_BATCH_SIZE_MIN = 1
FILL_BATCH_SIZE_MAX = 10000
SOURCE_ALIASES_BY_TABLE = {
    'cars_unified_ind': {
        'carsome': 'carsomeid',
    },
}
SAMPLE_LIMIT = 20


def validate_target_table(table_name):
    if table_name not in ALLOWED_TARGET_TABLES:
        raise ValueError('Unsupported target table')
    return ALLOWED_TARGET_TABLES[table_name]


def get_table_columns(table_name):
    validate_target_table(table_name) if table_name != CarsStandard._meta.db_table else None
    with connection.cursor() as cursor:
        description = connection.introspection.get_table_description(cursor, table_name)
    return {column.name for column in description}


def get_available_cars_standard_columns():
    try:
        table_columns = get_table_columns(CarsStandard._meta.db_table)
    except DatabaseError:
        table_columns = {field.column for field in CarsStandard._meta.fields}
    return [column for column in STANDARD_DISPLAY_COLUMNS if column in table_columns]


def discover_sources(table_name):
    config = validate_target_table(table_name)
    model = config['model']
    source_column = config['source_column']
    return list(
        model.objects.exclude(**{f'{source_column}__isnull': True})
        .exclude(**{source_column: ''})
        .values_list(source_column, flat=True)
        .distinct()
        .order_by(source_column)
    )


def validate_sources(table_name, sources):
    validate_target_table(table_name)
    cleaned_sources = []
    available_sources = discover_sources(table_name)
    available_by_lower = {str(source).lower(): source for source in available_sources}
    source_aliases = SOURCE_ALIASES_BY_TABLE.get(table_name, {})
    for source in sources or []:
        value = str(source).strip().lower()
        if not value:
            continue
        if value not in available_by_lower:
            value = source_aliases.get(value, value)
        if value not in available_by_lower:
            raise ValueError(f'Unsupported source for {table_name}: {source}')
        cleaned_sources.append(available_by_lower[value])
    cleaned_sources = sorted(set(cleaned_sources))
    if not cleaned_sources:
        raise ValueError('At least one source is required.')
    return cleaned_sources


def get_null_count_summary():
    summary = []
    for table_name, config in ALLOWED_TARGET_TABLES.items():
        model = config['model']
        source_column = config['source_column']
        try:
            total_count = model.objects.count()
            null_count = model.objects.filter(cars_standard__isnull=True).count()
            source_rows = list(
                model.objects.filter(cars_standard__isnull=True)
                .values(source_column)
                .annotate(null_count=Count('id'))
                .order_by(source_column)
            )
            sources = [
                {
                    'source': row.get(source_column) or 'Unknown',
                    'null_count': row['null_count'],
                }
                for row in source_rows
            ]
            error = ''
        except DatabaseError as exc:
            total_count = 0
            null_count = 0
            sources = []
            error = str(exc)

        summary.append(
            {
                'table': table_name,
                'total_count': total_count,
                'null_count': null_count,
                'sources': sources,
                'error': error,
            }
        )
    return summary


def get_cars_standard_total_count():
    try:
        return CarsStandard.objects.count()
    except DatabaseError:
        return 0


def search_cars_standard(query='', page=1, per_page=25):
    columns = get_available_cars_standard_columns()
    query = (query or '').strip()

    try:
        queryset = CarsStandard.objects.values(*columns).order_by('id')
        if query:
            filters = Q()
            if query.isdigit() and 'id' in columns:
                filters |= Q(id=int(query))
            for column in STANDARD_SEARCH_COLUMNS:
                if column in columns:
                    filters |= Q(**{f'{column}__icontains': query})
            queryset = queryset.filter(filters)
        paginator = Paginator(queryset, per_page)
        page_obj = paginator.get_page(page)
    except DatabaseError:
        paginator = Paginator([], per_page)
        page_obj = paginator.get_page(1)

    return {
        'page_obj': page_obj,
        'columns': columns,
        'query': query,
    }


def get_recent_maintenance_jobs(limit=10):
    return CarsStandardMaintenanceJob.objects.select_related('requested_by').order_by('-created_at')[:limit]


def serialize_maintenance_job(job):
    return {
        'id': job.id,
        'job_type': job.job_type,
        'job_type_display': job.get_job_type_display(),
        'status': job.status,
        'status_display': job.get_status_display(),
        'requested_by': job.requested_by.username if job.requested_by else '',
        'target_table': job.target_table,
        'sources': job.sources,
        'dry_run': job.dry_run,
        'parameters': job.parameters,
        'progress': job.progress,
        'result': job.result,
        'error_message': job.error_message,
        'celery_task_id': job.celery_task_id,
        'created_at': job.created_at.isoformat() if job.created_at else None,
        'started_at': job.started_at.isoformat() if job.started_at else None,
        'finished_at': job.finished_at.isoformat() if job.finished_at else None,
    }


def get_admin_overview():
    return {
        'cars_standard_total': get_cars_standard_total_count(),
        'null_count_summary': get_null_count_summary(),
        'maintenance_jobs': get_recent_maintenance_jobs(),
    }


def normalize_for_match(value):
    if value is None:
        return ''
    return re.sub(r'\s+', ' ', str(value).strip()).upper()


def serialize_cars_standard(row):
    return {column: getattr(row, column, None) for column in STANDARD_EDIT_COLUMNS if hasattr(row, column)}


def get_cars_standard_for_edit(row_id):
    return CarsStandard.objects.get(pk=row_id)


def get_normalized_preview(values):
    return {
        field: normalize_for_match(value)
        for field, value in values.items()
        if field in STANDARD_EDIT_COLUMNS and value
    }


def update_cars_standard(row_id, cleaned_data, user):
    with transaction.atomic():
        row = CarsStandard.objects.select_for_update().get(pk=row_id)
        old_values = serialize_cars_standard(row)
        updates = {}
        for field in STANDARD_EDIT_COLUMNS:
            if field in cleaned_data and hasattr(row, field):
                value = cleaned_data[field]
                if value == '':
                    value = None
                if getattr(row, field) != value:
                    updates[field] = value
        for field, value in updates.items():
            setattr(row, field, value)
        if updates:
            row.save(update_fields=list(updates.keys()))
            CarsStandardAuditLog.objects.create(
                user=user,
                action=CarsStandardAuditLog.ACTION_UPDATE,
                target_id=row.id,
                old_values={field: old_values.get(field) for field in updates},
                new_values={field: updates[field] for field in updates},
            )
        return {
            'row': row,
            'updated_fields': updates,
            'normalized_preview': get_normalized_preview(serialize_cars_standard(row)),
        }


def get_reference_counts(cars_standard_id):
    counts = {}
    for table_name, config in ALLOWED_TARGET_TABLES.items():
        model = config['model']
        counts[table_name] = model.objects.filter(cars_standard_id=cars_standard_id).count()
    return counts


def get_fk_delete_rules():
    table_names = list(ALLOWED_TARGET_TABLES.keys())
    placeholders = ', '.join(['%s'] * len(table_names))
    sql = f'''
        SELECT tc.table_name, rc.delete_rule
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
         AND tc.constraint_schema = kcu.constraint_schema
        JOIN information_schema.referential_constraints rc
          ON tc.constraint_name = rc.constraint_name
         AND tc.constraint_schema = rc.constraint_schema
        WHERE tc.constraint_type = 'FOREIGN KEY'
          AND tc.table_name IN ({placeholders})
          AND kcu.column_name = 'cars_standard_id'
    '''
    rules = {table_name: 'UNKNOWN' for table_name in table_names}
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql, table_names)
            for table_name, delete_rule in cursor.fetchall():
                rules[table_name] = delete_rule
    except DatabaseError:
        return rules
    return rules


def suggest_alias_transfers(source, target):
    suggestions = []
    for group_name, config in ALIAS_FIELD_GROUPS.items():
        target_values = {
            normalize_for_match(getattr(target, field, None))
            for field in config['source_fields']
            if normalize_for_match(getattr(target, field, None))
        }
        used_target_fields = set()
        for source_field in config['source_fields']:
            source_value = getattr(source, source_field, None)
            normalized_value = normalize_for_match(source_value)
            if not normalized_value or normalized_value in target_values:
                continue
            target_field = next(
                (
                    field for field in config['target_fields']
                    if field not in used_target_fields and not getattr(target, field, None)
                ),
                None,
            )
            if target_field:
                suggestions.append(
                    {
                        'group': group_name,
                        'source_field': source_field,
                        'target_field': target_field,
                        'value': source_value,
                        'normalized_value': normalized_value,
                    }
                )
                used_target_fields.add(target_field)
                target_values.add(normalized_value)
    return suggestions


def build_alias_changes_from_suggestions(suggestions):
    return {item['target_field']: item['value'] for item in suggestions}


def parse_alias_changes(raw_value):
    if not raw_value:
        return {}
    if isinstance(raw_value, dict):
        data = raw_value
    else:
        data = json.loads(raw_value)
    changes = {}
    allowed_fields = {field for config in ALIAS_FIELD_GROUPS.values() for field in config['target_fields']}
    for field, value in data.items():
        if field not in allowed_fields:
            raise ValueError('Unsupported alias target field')
        if value is None:
            continue
        value = str(value).strip()
        if value:
            changes[field] = value[:100]
    return changes


def serialize_alias_changes(alias_changes):
    return json.dumps(parse_alias_changes(alias_changes), sort_keys=True, separators=(',', ':'))


def quote_identifier(identifier):
    return connection.ops.quote_name(identifier)


def ensure_insert_missing_schema(table_name):
    config = validate_target_table(table_name)
    source_columns = get_table_columns(table_name)
    missing_source_columns = set(config['required_columns']) - source_columns
    if missing_source_columns:
        missing = ', '.join(sorted(missing_source_columns))
        raise RuntimeError(f'{table_name} is missing required columns: {missing}')
    standard_columns = get_table_columns(CarsStandard._meta.db_table)
    required_standard_columns = {'id', 'brand_norm', 'model_group_norm', 'model_norm', 'variant_norm'}
    missing_standard_columns = required_standard_columns - standard_columns
    if missing_standard_columns:
        missing = ', '.join(sorted(missing_standard_columns))
        raise RuntimeError(f'cars_standard is missing required columns: {missing}')


def ensure_fill_schema(table_name):
    config = validate_target_table(table_name)
    source_columns = get_table_columns(table_name)
    missing_source_columns = set(config['required_columns']) - source_columns
    if missing_source_columns:
        missing = ', '.join(sorted(missing_source_columns))
        raise RuntimeError(f'{table_name} is missing required columns: {missing}')
    standard_columns = get_table_columns(CarsStandard._meta.db_table)
    required_standard_columns = {'id', 'brand_norm', 'model_group_norm', 'model_norm', 'variant_norm'}
    missing_standard_columns = required_standard_columns - standard_columns
    if missing_standard_columns:
        missing = ', '.join(sorted(missing_standard_columns))
        raise RuntimeError(f'cars_standard is missing required columns: {missing}')


def validate_fill_batch_size(batch_size):
    try:
        batch_size = int(batch_size)
    except (TypeError, ValueError):
        raise ValueError('Batch size must be a number.')
    if batch_size < FILL_BATCH_SIZE_MIN or batch_size > FILL_BATCH_SIZE_MAX:
        raise ValueError(f'Batch size must be between {FILL_BATCH_SIZE_MIN} and {FILL_BATCH_SIZE_MAX}.')
    return batch_size


def ensure_cars_standard_id_default():
    table_name = CarsStandard._meta.db_table
    with connection.cursor() as cursor:
        cursor.execute(
            '''
            SELECT pg_get_expr(pg_attrdef.adbin, pg_attrdef.adrelid) AS column_default,
                   pg_attribute.attidentity
            FROM pg_attribute
            JOIN pg_class ON pg_class.oid = pg_attribute.attrelid
            LEFT JOIN pg_attrdef
              ON pg_attrdef.adrelid = pg_attribute.attrelid
             AND pg_attrdef.adnum = pg_attribute.attnum
            WHERE pg_class.oid = to_regclass(%s)
              AND pg_attribute.attname = 'id'
              AND NOT pg_attribute.attisdropped
            ''',
            [table_name],
        )
        row = cursor.fetchone()
    if not row:
        raise RuntimeError('cars_standard.id metadata could not be verified.')
    column_default, identity = row
    has_sequence_default = column_default and 'nextval(' in column_default.lower()
    if identity not in ('a', 'd') and not has_sequence_default:
        raise RuntimeError('cars_standard.id has no database default or identity sequence; aborting insert missing execution.')


def _insert_missing_params(sources):
    params = [MODEL_GROUP_DEFAULT, sources]
    params.extend(NULLISH_VALUES)
    params.extend(NULLISH_VALUES)
    params.extend(NULLISH_VALUES)
    return params


def _insert_missing_cte(table_name):
    config = validate_target_table(table_name)
    nullish_placeholders = ', '.join(['%s'] * len(NULLISH_VALUES))
    quoted_table = quote_identifier(table_name)
    quoted_source_column = quote_identifier(config['source_column'])
    return f'''
        WITH source_rows AS (
            SELECT DISTINCT
                UPPER(TRIM(brand::text)) AS brand_norm,
                %s::varchar AS model_group_norm,
                UPPER(TRIM(model::text)) AS model_norm,
                UPPER(TRIM(variant::text)) AS variant_norm
            FROM {quoted_table}
            WHERE {quoted_source_column} = ANY(%s::text[])
              AND {quote_identifier('cars_standard_id')} IS NULL
              AND brand IS NOT NULL
              AND model IS NOT NULL
              AND variant IS NOT NULL
              AND UPPER(TRIM(brand::text)) NOT IN ({nullish_placeholders})
              AND UPPER(TRIM(model::text)) NOT IN ({nullish_placeholders})
              AND UPPER(TRIM(variant::text)) NOT IN ({nullish_placeholders})
        ), existing_matches AS (
            SELECT source_rows.*
            FROM source_rows
            WHERE EXISTS (
                SELECT 1
                FROM cars_standard cs
                WHERE UPPER(TRIM(cs.brand_norm::text)) = source_rows.brand_norm
                  AND UPPER(TRIM(cs.model_group_norm::text)) = source_rows.model_group_norm
                  AND UPPER(TRIM(cs.model_norm::text)) = source_rows.model_norm
                  AND UPPER(TRIM(cs.variant_norm::text)) = source_rows.variant_norm
            )
        ), new_rows AS (
            SELECT source_rows.*
            FROM source_rows
            WHERE NOT EXISTS (
                SELECT 1
                FROM cars_standard cs
                WHERE UPPER(TRIM(cs.brand_norm::text)) = source_rows.brand_norm
                  AND UPPER(TRIM(cs.model_group_norm::text)) = source_rows.model_group_norm
                  AND UPPER(TRIM(cs.model_norm::text)) = source_rows.model_norm
                  AND UPPER(TRIM(cs.variant_norm::text)) = source_rows.variant_norm
            )
        )
    '''


def _fetch_dicts(cursor):
    columns = [column[0] for column in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def get_insert_missing_preview(table_name, sources):
    validate_target_table(table_name)
    sources = validate_sources(table_name, sources)
    ensure_insert_missing_schema(table_name)
    cte = _insert_missing_cte(table_name)
    params = _insert_missing_params(sources)
    with connection.cursor() as cursor:
        cursor.execute(
            cte + '''
            SELECT
                (SELECT COUNT(*) FROM source_rows) AS distinct_candidates,
                (SELECT COUNT(*) FROM existing_matches) AS already_exists,
                (SELECT COUNT(*) FROM new_rows) AS rows_to_insert
            ''',
            params,
        )
        counts = dict(zip([column[0] for column in cursor.description], cursor.fetchone()))
        cursor.execute(cte + ' SELECT * FROM source_rows ORDER BY brand_norm, model_norm, variant_norm LIMIT %s', [*params, SAMPLE_LIMIT])
        candidate_sample = _fetch_dicts(cursor)
        cursor.execute(cte + ' SELECT * FROM existing_matches ORDER BY brand_norm, model_norm, variant_norm LIMIT %s', [*params, SAMPLE_LIMIT])
        existing_sample = _fetch_dicts(cursor)
        cursor.execute(cte + ' SELECT * FROM new_rows ORDER BY brand_norm, model_norm, variant_norm LIMIT %s', [*params, SAMPLE_LIMIT])
        insert_sample = _fetch_dicts(cursor)
    return {
        'status': 'preview',
        'table_name': table_name,
        'sources': sources,
        'distinct_candidates': counts['distinct_candidates'],
        'already_exists': counts['already_exists'],
        'rows_to_insert': counts['rows_to_insert'],
        'inserted': 0,
        'candidate_sample': candidate_sample,
        'existing_sample': existing_sample,
        'insert_sample': insert_sample,
        'sample_limit': SAMPLE_LIMIT,
        'message': f"Preview found {counts['rows_to_insert']} cars_standard rows to insert.",
    }


def build_insert_missing_preview_token(table_name, sources, user_id):
    payload = {
        'table_name': table_name,
        'sources': validate_sources(table_name, sources),
        'nonce': secrets.token_urlsafe(16),
        'user_id': user_id,
    }
    signer = TimestampSigner(salt=INSERT_MISSING_PREVIEW_TOKEN_SALT)
    return signer.sign(json.dumps(payload, sort_keys=True, separators=(',', ':')))


def validate_insert_missing_preview_token(token, table_name, sources, user_id):
    signer = TimestampSigner(salt=INSERT_MISSING_PREVIEW_TOKEN_SALT)
    try:
        payload = json.loads(signer.unsign(token, max_age=INSERT_MISSING_PREVIEW_TOKEN_MAX_AGE))
    except (BadSignature, SignatureExpired, json.JSONDecodeError):
        raise ValueError('Insert execution requires a valid recent preview token.')
    expected = {
        'table_name': table_name,
        'sources': validate_sources(table_name, sources),
        'user_id': user_id,
    }
    for key, value in expected.items():
        if payload.get(key) != value:
            raise ValueError('Insert preview token does not match the requested execution.')
    if not payload.get('nonce'):
        raise ValueError('Insert preview token is missing required nonce.')
    return payload


def execute_insert_missing_cars_standard(table_name, sources, user, preview_token=None, dry_run=False):
    validate_target_table(table_name)
    sources = validate_sources(table_name, sources)
    ensure_insert_missing_schema(table_name)
    if not dry_run:
        validate_insert_missing_preview_token(preview_token, table_name, sources, user.id if user else None)
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_advisory_xact_lock(hashtext(%s))', ['cars_standard_insert_missing'])
        preview = get_insert_missing_preview(table_name, sources)
        if dry_run or preview['rows_to_insert'] == 0:
            result = {
                **preview,
                'status': 'dry_run' if dry_run else 'success',
                'message': 'Dry-run preview completed.' if dry_run else 'No new cars_standard rows to insert.',
            }
        else:
            ensure_cars_standard_id_default()
            cte = _insert_missing_cte(table_name)
            params = _insert_missing_params(sources)
            insert_sql = cte + '''
                INSERT INTO cars_standard (
                    brand_norm,
                    model_group_norm,
                    model_norm,
                    variant_norm
                )
                SELECT
                    brand_norm,
                    model_group_norm,
                    model_norm,
                    variant_norm
                FROM new_rows
                ORDER BY brand_norm, model_norm, variant_norm
                RETURNING id, brand_norm, model_group_norm, model_norm, variant_norm
            '''
            with connection.cursor() as cursor:
                cursor.execute(insert_sql, params)
                inserted_rows = _fetch_dicts(cursor)
            result = {
                **preview,
                'status': 'success',
                'inserted': len(inserted_rows),
                'first_inserted_ids': [row['id'] for row in inserted_rows[:SAMPLE_LIMIT]],
                'inserted_sample': inserted_rows[:SAMPLE_LIMIT],
                'message': f"Inserted {len(inserted_rows)} cars_standard rows.",
            }
        CarsStandardAuditLog.objects.create(
            user=user,
            action=CarsStandardAuditLog.ACTION_INSERT_MISSING,
            old_values={},
            new_values={
                'table_name': table_name,
                'sources': sources,
                'inserted': result['inserted'],
                'insert_sample': result.get('inserted_sample') or result.get('insert_sample', []),
            },
            affected_references={
                'distinct_candidates': result['distinct_candidates'],
                'already_exists': result['already_exists'],
                'rows_to_insert': result['rows_to_insert'],
            },
        )
        return result


STANDARD_MATCH_COLUMN_GROUPS = {
    'brand': ['brand_norm', 'brand_raw', 'brand_raw2'],
    'model_group': ['model_group_norm', 'model_group_raw'],
    'model': ['model_norm', 'model_raw', 'model_raw2'],
    'variant': ['variant_norm', 'variant_raw', 'variant_raw2', 'variant_raw3', 'variant_raw4'],
}

FILL_FAILED_RECORD_LIMIT = 1000
FILL_PREVIEW_ROW_CAP = 1000


def normalize_match_value(value):
    normalized = normalize_for_match(value)
    if normalized in NULLISH_VALUES:
        return None
    return normalized or None


def candidate_matches(candidate, key, target):
    target = normalize_match_value(target)
    if target is None:
        return False
    for column in STANDARD_MATCH_COLUMN_GROUPS.get(key, []):
        value = candidate.get(column)
        if normalize_match_value(value) == target:
            return True
    return False


def _standard_select_columns(standard_columns):
    columns = ['id'] + [column for columns in STANDARD_MATCH_COLUMN_GROUPS.values() for column in columns]
    select_columns = []
    for column in columns:
        if column in standard_columns:
            select_columns.append(quote_identifier(column))
        else:
            select_columns.append(f'NULL AS {quote_identifier(column)}')
    return ', '.join(select_columns)


def _find_cars_standard_matches(cursor, standard_columns, brand, model_group, model, variant):
    brand_norm = normalize_match_value(brand)
    model_group_norm = normalize_match_value(model_group)
    model_norm = normalize_match_value(model)
    variant_norm = normalize_match_value(variant)
    if brand_norm is None or model_norm is None or variant_norm is None:
        return []
    brand_lookup_columns = [
        column for column in STANDARD_MATCH_COLUMN_GROUPS['brand'] if column in standard_columns
    ]
    if not brand_lookup_columns:
        raise RuntimeError('cars_standard has no brand lookup columns.')
    brand_conditions = ' OR '.join(
        f'UPPER(TRIM({quote_identifier(column)}::text)) = %s'
        for column in brand_lookup_columns
    )
    cursor.execute(
        f'''
        SELECT {_standard_select_columns(standard_columns)}
        FROM {quote_identifier(CarsStandard._meta.db_table)}
        WHERE {brand_conditions}
        ORDER BY id
        ''',
        [brand_norm for _ in brand_lookup_columns],
    )
    brand_matches = _fetch_dicts(cursor)
    ignore_model_group = model_group_norm in {None, MODEL_GROUP_DEFAULT}
    matches = []
    for candidate in brand_matches:
        if not candidate_matches(candidate, 'brand', brand_norm):
            continue
        if not ignore_model_group and not candidate_matches(candidate, 'model_group', model_group_norm):
            continue
        if not candidate_matches(candidate, 'model', model_norm):
            continue
        if not candidate_matches(candidate, 'variant', variant_norm):
            continue
        matches.append(candidate)
    return matches


def _source_select_sql(table_name):
    config = validate_target_table(table_name)
    source_columns = get_table_columns(table_name)
    listing_url_sql = quote_identifier('listing_url') if 'listing_url' in source_columns else 'NULL AS listing_url'
    model_group_sql = quote_identifier('model_group') if 'model_group' in source_columns else 'NULL AS model_group'
    return f'''
        SELECT
            {quote_identifier(config['id_column'])} AS id,
            {quote_identifier(config['source_column'])} AS source,
            {listing_url_sql},
            {quote_identifier('brand')} AS brand,
            {model_group_sql},
            {quote_identifier('model')} AS model,
            {quote_identifier('variant')} AS variant
        FROM {quote_identifier(table_name)}
        WHERE {quote_identifier(config['source_column'])} = %s
          AND {quote_identifier('cars_standard_id')} IS NULL
        ORDER BY {quote_identifier(config['id_column'])}
    '''


def _count_source_null_rows(table_name, source):
    config = validate_target_table(table_name)
    with connection.cursor() as cursor:
        cursor.execute(
            f'''
            SELECT COUNT(*)
            FROM {quote_identifier(table_name)}
            WHERE {quote_identifier(config['source_column'])} = %s
              AND {quote_identifier('cars_standard_id')} IS NULL
            ''',
            [source],
        )
        return cursor.fetchone()[0]


def _serialize_source_record(record):
    return {
        'id': record.get('id'),
        'source': record.get('source'),
        'listing_url': record.get('listing_url'),
        'brand': record.get('brand'),
        'model_group': record.get('model_group'),
        'model': record.get('model'),
        'variant': record.get('variant'),
    }


def get_fill_standard_id_preview(table_name, sources, batch_size=500, preview_cap=FILL_PREVIEW_ROW_CAP):
    validate_target_table(table_name)
    sources = validate_sources(table_name, sources)
    batch_size = validate_fill_batch_size(batch_size)
    ensure_fill_schema(table_name)
    preview_cap = int(preview_cap)
    if preview_cap < 1:
        raise ValueError('Preview cap must be at least 1.')
    standard_columns = get_table_columns(CarsStandard._meta.db_table)
    started = time.monotonic()
    totals = {
        'null_rows': 0,
        'scanned_rows': 0,
        'matched': 0,
        'unmatched': 0,
        'ambiguous': 0,
    }
    per_source = []
    matched_sample = []
    failed_sample = []
    ambiguous_sample = []
    truncated = False
    with connection.cursor() as cursor:
        source_sql = _source_select_sql(table_name)
        for source in sources:
            source_counts = {
                'source': source,
                'null_rows': _count_source_null_rows(table_name, source),
                'scanned_rows': 0,
                'matched': 0,
                'unmatched': 0,
                'ambiguous': 0,
                'truncated': False,
            }
            totals['null_rows'] += source_counts['null_rows']
            remaining = preview_cap - totals['scanned_rows']
            if remaining <= 0:
                source_counts['truncated'] = source_counts['null_rows'] > 0
                truncated = truncated or source_counts['truncated']
                per_source.append(source_counts)
                continue
            cursor.execute(f'{source_sql} LIMIT %s', [source, remaining])
            records = _fetch_dicts(cursor)
            source_counts['scanned_rows'] = len(records)
            totals['scanned_rows'] += len(records)
            source_counts['truncated'] = source_counts['null_rows'] > len(records)
            truncated = truncated or source_counts['truncated']
            for record in records:
                matches = _find_cars_standard_matches(
                    cursor,
                    standard_columns,
                    record.get('brand'),
                    record.get('model_group'),
                    record.get('model'),
                    record.get('variant'),
                )
                source_record = _serialize_source_record(record)
                if len(matches) == 1:
                    totals['matched'] += 1
                    source_counts['matched'] += 1
                    if len(matched_sample) < SAMPLE_LIMIT:
                        matched_sample.append({
                            'source_row': source_record,
                            'cars_standard_id': matches[0]['id'],
                        })
                elif len(matches) > 1:
                    totals['ambiguous'] += 1
                    source_counts['ambiguous'] += 1
                    if len(ambiguous_sample) < SAMPLE_LIMIT:
                        ambiguous_sample.append({
                            'source_row': source_record,
                            'candidate_ids': [match['id'] for match in matches],
                        })
                else:
                    totals['unmatched'] += 1
                    source_counts['unmatched'] += 1
                    if len(failed_sample) < SAMPLE_LIMIT:
                        failed_sample.append(source_record)
            per_source.append(source_counts)
    duration = round(time.monotonic() - started, 3)
    message = f"Preview scanned {totals['scanned_rows']} of {totals['null_rows']} NULL rows and found {totals['matched']} matched, {totals['unmatched']} unmatched, and {totals['ambiguous']} ambiguous rows."
    if truncated:
        message += f' Preview was truncated at {preview_cap} rows; execution will process all currently eligible rows via Celery.'
    return {
        'status': 'preview',
        'table_name': table_name,
        'sources': sources,
        'batch_size': batch_size,
        'null_rows': totals['null_rows'],
        'scanned_rows': totals['scanned_rows'],
        'estimated_matched': totals['matched'],
        'estimated_unmatched': totals['unmatched'],
        'estimated_ambiguous': totals['ambiguous'],
        'preview_cap': preview_cap,
        'preview_truncated': truncated,
        'per_source': per_source,
        'matched_sample': matched_sample,
        'failed_sample': failed_sample,
        'ambiguous_sample': ambiguous_sample,
        'sample_limit': SAMPLE_LIMIT,
        'duration_seconds': duration,
        'message': message,
    }


def build_fill_preview_token(table_name, sources, batch_size, user_id):
    payload = {
        'table_name': table_name,
        'sources': validate_sources(table_name, sources),
        'batch_size': validate_fill_batch_size(batch_size),
        'nonce': secrets.token_urlsafe(16),
        'user_id': user_id,
    }
    signer = TimestampSigner(salt=FILL_PREVIEW_TOKEN_SALT)
    return signer.sign(json.dumps(payload, sort_keys=True, separators=(',', ':')))


def validate_fill_preview_token(token, table_name, sources, batch_size, user_id):
    signer = TimestampSigner(salt=FILL_PREVIEW_TOKEN_SALT)
    try:
        payload = json.loads(signer.unsign(token, max_age=FILL_PREVIEW_TOKEN_MAX_AGE))
    except (BadSignature, SignatureExpired, json.JSONDecodeError):
        raise ValueError('Fill execution requires a valid recent preview token.')
    expected = {
        'table_name': table_name,
        'sources': validate_sources(table_name, sources),
        'batch_size': validate_fill_batch_size(batch_size),
        'user_id': user_id,
    }
    for key, value in expected.items():
        if payload.get(key) != value:
            raise ValueError('Fill preview token does not match the requested execution.')
    if not payload.get('nonce'):
        raise ValueError('Fill preview token is missing required nonce.')
    return payload


def execute_fill_standard_id(table_name, sources, user, batch_size=500, preview_token=None, dry_run=False):
    validate_target_table(table_name)
    sources = validate_sources(table_name, sources)
    batch_size = validate_fill_batch_size(batch_size)
    ensure_fill_schema(table_name)
    if dry_run:
        result = get_fill_standard_id_preview(table_name, sources, batch_size)
        result['status'] = 'dry_run'
        result['message'] = 'Dry-run fill matching completed without updates.'
        CarsStandardAuditLog.objects.create(
            user=user,
            action=CarsStandardAuditLog.ACTION_FILL_STANDARD_ID,
            old_values={},
            new_values={
                'table_name': table_name,
                'sources': sources,
                'dry_run': True,
            },
            affected_references=result,
        )
        return result
    validate_fill_preview_token(preview_token, table_name, sources, batch_size, user.id if user else None)
    standard_columns = get_table_columns(CarsStandard._meta.db_table)
    config = validate_target_table(table_name)
    source_sql = _source_select_sql(table_name)
    update_sql = f'''
        UPDATE {quote_identifier(table_name)}
        SET {quote_identifier('cars_standard_id')} = %s
        WHERE {quote_identifier(config['id_column'])} = %s
          AND {quote_identifier('cars_standard_id')} IS NULL
    '''
    started = time.monotonic()
    total_updated = 0
    total_failed = 0
    total_ambiguous = 0
    total_seen = 0
    per_source = []
    matched_sample = []
    failed_records = []
    ambiguous_records = []
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_advisory_xact_lock(hashtext(%s))', [f'cars_standard_fill:{table_name}'])
            for source in sources:
                source_counts = {
                    'source': source,
                    'null_rows': _count_source_null_rows(table_name, source),
                    'updated': 0,
                    'failed': 0,
                    'ambiguous': 0,
                }
                cursor.execute(source_sql, [source])
                records = _fetch_dicts(cursor)
                update_batch = []
                for record in records:
                    total_seen += 1
                    matches = _find_cars_standard_matches(
                        cursor,
                        standard_columns,
                        record.get('brand'),
                        record.get('model_group'),
                        record.get('model'),
                        record.get('variant'),
                    )
                    source_record = _serialize_source_record(record)
                    if len(matches) == 1:
                        update_batch.append((matches[0]['id'], record['id']))
                        source_counts['updated'] += 1
                        total_updated += 1
                        if len(matched_sample) < SAMPLE_LIMIT:
                            matched_sample.append({
                                'source_row': source_record,
                                'cars_standard_id': matches[0]['id'],
                            })
                    elif len(matches) > 1:
                        source_counts['ambiguous'] += 1
                        total_ambiguous += 1
                        if len(ambiguous_records) < FILL_FAILED_RECORD_LIMIT:
                            ambiguous_records.append({
                                'source_row': source_record,
                                'candidate_ids': [match['id'] for match in matches],
                            })
                    else:
                        source_counts['failed'] += 1
                        total_failed += 1
                        if len(failed_records) < FILL_FAILED_RECORD_LIMIT:
                            failed_records.append(source_record)
                    if len(update_batch) >= batch_size:
                        cursor.executemany(update_sql, update_batch)
                        update_batch = []
                if update_batch:
                    cursor.executemany(update_sql, update_batch)
                per_source.append(source_counts)
    duration = round(time.monotonic() - started, 3)
    result = {
        'status': 'success',
        'table_name': table_name,
        'sources': sources,
        'batch_size': batch_size,
        'processed': total_seen,
        'updated': total_updated,
        'failed': total_failed,
        'ambiguous': total_ambiguous,
        'per_source': per_source,
        'duration_seconds': duration,
        'matched_sample': matched_sample,
        'failed_records': failed_records,
        'failed_records_truncated': total_failed > len(failed_records),
        'ambiguous_records': ambiguous_records,
        'ambiguous_records_truncated': total_ambiguous > len(ambiguous_records),
        'message': f'Updated {total_updated} rows. Failed {total_failed}. Ambiguous {total_ambiguous}.',
    }
    CarsStandardAuditLog.objects.create(
        user=user,
        action=CarsStandardAuditLog.ACTION_FILL_STANDARD_ID,
        old_values={},
        new_values={
            'table_name': table_name,
            'sources': sources,
            'updated': total_updated,
            'failed': total_failed,
            'ambiguous': total_ambiguous,
        },
        affected_references={
            'per_source': per_source,
            'duration_seconds': duration,
            'failed_records': failed_records,
            'failed_records_truncated': result['failed_records_truncated'],
            'ambiguous_records': ambiguous_records,
            'ambiguous_records_truncated': result['ambiguous_records_truncated'],
        },
    )
    return result


def build_merge_preview_token(source_id, target_id, alias_changes, user_id):
    payload = {
        'source_id': int(source_id),
        'target_id': int(target_id),
        'alias_changes': parse_alias_changes(alias_changes),
        'nonce': secrets.token_urlsafe(16),
        'user_id': user_id,
    }
    signer = TimestampSigner(salt=MERGE_PREVIEW_TOKEN_SALT)
    return signer.sign(json.dumps(payload, sort_keys=True, separators=(',', ':')))


def validate_merge_preview_token(token, source_id, target_id, alias_changes, user_id):
    signer = TimestampSigner(salt=MERGE_PREVIEW_TOKEN_SALT)
    try:
        payload = json.loads(signer.unsign(token, max_age=MERGE_PREVIEW_TOKEN_MAX_AGE))
    except (BadSignature, SignatureExpired, json.JSONDecodeError):
        raise ValueError('Merge execution requires a valid recent preview token.')
    expected = {
        'source_id': int(source_id),
        'target_id': int(target_id),
        'alias_changes': parse_alias_changes(alias_changes),
        'user_id': user_id,
    }
    for key, value in expected.items():
        if payload.get(key) != value:
            raise ValueError('Merge preview token does not match the requested merge.')
    if not payload.get('nonce'):
        raise ValueError('Merge preview token is missing required nonce.')
    return payload


def get_null_reference_counts():
    counts = {}
    for table_name, config in ALLOWED_TARGET_TABLES.items():
        model = config['model']
        counts[table_name] = model.objects.filter(cars_standard_id__isnull=True).count()
    return counts


def get_merge_preview(source_id, target_id, alias_changes=None):
    source = CarsStandard.objects.get(pk=source_id)
    target = CarsStandard.objects.get(pk=target_id)
    suggestions = suggest_alias_transfers(source, target)
    changes = alias_changes if alias_changes is not None else build_alias_changes_from_suggestions(suggestions)
    reference_counts = get_reference_counts(source_id)
    fk_delete_rules = get_fk_delete_rules()
    return {
        'source': serialize_cars_standard(source),
        'target': serialize_cars_standard(target),
        'source_id': source.id,
        'target_id': target.id,
        'suggestions': suggestions,
        'alias_changes': changes,
        'alias_change_rows': [{'field': field, 'value': value} for field, value in changes.items()],
        'affected_references': reference_counts,
        'reference_rows': [
            {'table': table, 'count': count, 'delete_rule': fk_delete_rules.get(table, 'UNKNOWN')}
            for table, count in reference_counts.items()
        ],
        'fk_delete_rules': fk_delete_rules,
        'manual_null_fallback_tables': [
            table for table, rule in fk_delete_rules.items() if rule != 'SET NULL'
        ],
    }


def manually_null_references(cars_standard_id, table_names):
    updated_counts = {}
    for table_name in table_names:
        config = validate_target_table(table_name)
        model = config['model']
        updated_counts[table_name] = model.objects.filter(cars_standard_id=cars_standard_id).update(cars_standard_id=None)
    return updated_counts


def execute_merge(source_id, target_id, alias_changes, user, preview_token):
    if source_id == target_id:
        raise ValueError('Source and target rows must be different.')
    alias_changes = parse_alias_changes(alias_changes)
    validate_merge_preview_token(preview_token, source_id, target_id, alias_changes, user.id)
    with transaction.atomic():
        rows = {
            row.id: row
            for row in CarsStandard.objects.select_for_update().filter(id__in=[source_id, target_id]).order_by('id')
        }
        if source_id not in rows or target_id not in rows:
            raise CarsStandard.DoesNotExist('Source or target row was not found.')
        source = rows[source_id]
        target = rows[target_id]
        old_source = serialize_cars_standard(source)
        old_target = serialize_cars_standard(target)
        before_counts = get_reference_counts(source_id)
        fk_delete_rules = get_fk_delete_rules()
        manual_tables = [table for table, rule in fk_delete_rules.items() if rule != 'SET NULL']
        manual_counts = manually_null_references(source_id, manual_tables) if manual_tables else {}
        update_fields = []
        for field, value in alias_changes.items():
            if getattr(target, field, None) != value:
                setattr(target, field, value)
                update_fields.append(field)
        if update_fields:
            target.save(update_fields=update_fields)
        target_after = serialize_cars_standard(target)
        source.delete()
        after_counts = get_reference_counts(source_id)
        target_after_counts = get_reference_counts(target_id)
        post_null_counts = get_null_reference_counts()
        audit_values = {
            'target_before': old_target,
            'target_after': target_after,
            'source_deleted': old_source,
            'alias_changes': {field: getattr(target, field, None) for field in update_fields},
        }
        CarsStandardAuditLog.objects.create(
            user=user,
            action=CarsStandardAuditLog.ACTION_MERGE,
            source_id=source_id,
            target_id=target_id,
            old_values={'source': old_source, 'target': old_target},
            new_values=audit_values,
            affected_references={
                'before_delete': before_counts,
                'after_delete': after_counts,
                'target_after': target_after_counts,
                'post_null_counts': post_null_counts,
                'fk_delete_rules': fk_delete_rules,
                'manual_null_fallback': manual_counts,
            },
        )
    return {
        'source_id': source_id,
        'target_id': target_id,
        'updated_aliases': alias_changes,
        'affected_references': before_counts,
        'affected_references_after': after_counts,
        'target_references_after': target_after_counts,
        'post_null_counts': post_null_counts,
        'fk_delete_rules': fk_delete_rules,
        'manual_null_fallback': manual_counts,
    }
