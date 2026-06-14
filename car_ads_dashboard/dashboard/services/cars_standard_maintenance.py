from django.core.paginator import Paginator
from django.db import DatabaseError, connection
from django.db.models import Count, Q

from ..models import CarsStandard, CarsUnified, CarsUnifiedInd, Carsome


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


def get_admin_overview():
    return {
        'cars_standard_total': get_cars_standard_total_count(),
        'null_count_summary': get_null_count_summary(),
    }
