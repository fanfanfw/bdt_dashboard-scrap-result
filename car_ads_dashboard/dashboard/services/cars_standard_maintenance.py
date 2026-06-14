import json
import re
import secrets

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
