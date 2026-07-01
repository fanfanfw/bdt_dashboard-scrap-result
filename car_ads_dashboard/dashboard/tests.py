import json
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock, patch

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from django.contrib.auth.models import Group, User
from django.core.paginator import Paginator
from django.test import SimpleTestCase, TestCase, TransactionTestCase, override_settings
from django.urls import reverse

from .consumers import CarsStandardJobConsumer

from .models import CarsStandardMaintenanceJob
from .services import cars_standard_maintenance as service


class CarsStandardServiceValidationTests(TestCase):
    def test_validate_target_table_allows_only_known_tables(self):
        self.assertIs(service.validate_target_table('cars_unified'), service.ALLOWED_TARGET_TABLES['cars_unified'])
        self.assertIs(service.validate_target_table('carsome'), service.ALLOWED_TARGET_TABLES['carsome'])
        self.assertIs(service.validate_target_table('cars_unified_ind'), service.ALLOWED_TARGET_TABLES['cars_unified_ind'])
        self.assertIs(service.validate_target_table('cars_unified_jp'), service.ALLOWED_TARGET_TABLES['cars_unified_jp'])

        blocked_names = [
            'cars_standard',
            'cars_unified; DROP TABLE cars_standard;',
            'cars_unified WHERE 1=1',
            'public.cars_unified',
            'cars-unified',
            '',
        ]
        for table_name in blocked_names:
            with self.subTest(table_name=table_name):
                with self.assertRaises(ValueError):
                    service.validate_target_table(table_name)

    @patch('dashboard.services.cars_standard_maintenance.discover_sources')
    def test_validate_sources_uses_discovered_allowlist_and_aliases(self, discover_sources):
        discover_sources.return_value = ['carlistmy', 'mudahmy', 'carsomeid']

        self.assertEqual(service.validate_sources('cars_unified', [' CarListMY ', 'mudahmy']), ['carlistmy', 'mudahmy'])
        self.assertEqual(service.validate_sources('cars_unified_ind', ['carsome']), ['carsomeid'])
        self.assertEqual(service.validate_sources('cars_unified_jp', ['carsomeid']), ['carsomeid'])

        with self.assertRaises(ValueError):
            service.validate_sources('cars_unified', ['unknown'])
        with self.assertRaises(ValueError):
            service.validate_sources('cars_unified', [])

    def test_dynamic_sql_helpers_reject_unallowed_tables_before_quoting(self):
        with self.assertRaises(ValueError):
            service._insert_missing_cte('cars_unified; DROP TABLE cars_standard;')
        with self.assertRaises(ValueError):
            service._source_select_sql('cars_unified; DROP TABLE cars_standard;')
        with self.assertRaises(ValueError):
            service.get_table_columns('cars_unified; DROP TABLE cars_standard;')

    def test_alias_changes_are_limited_to_alias_target_fields(self):
        self.assertEqual(
            service.parse_alias_changes({'variant_raw': ' SDRIVE 20I ', 'brand_raw': None, 'model_raw': ''}),
            {'variant_raw': 'SDRIVE 20I'},
        )
        self.assertEqual(service.parse_alias_changes({'variant_raw': 'A' * 150}), {'variant_raw': 'A' * 100})
        with self.assertRaises(ValueError):
            service.parse_alias_changes({'variant_norm': 'unsafe normalized edit'})

    def test_candidate_matching_normalizes_values_and_nullish_values(self):
        candidate = {
            'brand_norm': 'BMW',
            'brand_raw': None,
            'brand_raw2': None,
            'model_group_norm': 'NO MODEL GROUP',
            'model_group_raw': None,
            'model_norm': 'X1',
            'model_raw': 'X 1',
            'model_raw2': None,
            'variant_norm': 'S DRIVE 20I',
            'variant_raw': 'SDRIVE 20I',
            'variant_raw2': None,
            'variant_raw3': None,
            'variant_raw4': None,
        }

        self.assertTrue(service.candidate_matches(candidate, 'brand', ' bmw '))
        self.assertTrue(service.candidate_matches(candidate, 'model', 'x 1'))
        self.assertTrue(service.candidate_matches(candidate, 'variant', 'sdrive 20i'))
        self.assertFalse(service.candidate_matches(candidate, 'variant', 'N/A'))
        self.assertIsNone(service.normalize_match_value(' - '))
        self.assertEqual(service.normalize_match_value(' x   1 '), 'X   1')

    def test_find_matches_uses_raw_aliases_and_ignores_missing_model_group(self):
        cursor = Mock()
        cursor.description = [('id',), ('brand_norm',), ('brand_raw',), ('brand_raw2',), ('model_group_norm',), ('model_group_raw',), ('model_norm',), ('model_raw',), ('model_raw2',), ('variant_norm',), ('variant_raw',), ('variant_raw2',), ('variant_raw3',), ('variant_raw4',)]
        cursor.fetchall.return_value = [(
            7,
            None,
            None,
            ' Toyota ',
            'SUV',
            None,
            None,
            None,
            'Corolla Cross',
            None,
            None,
            None,
            None,
            'Hybrid',
        )]

        matches = service._find_cars_standard_matches(
            cursor,
            set(service.STANDARD_DISPLAY_COLUMNS),
            'toyota',
            'NO MODEL GROUP',
            ' corolla cross ',
            ' hybrid ',
        )

        self.assertEqual([match['id'] for match in matches], [7])

    def test_ambiguous_matches_are_classified_without_single_update_target(self):
        cursor = Mock()
        cursor.description = [('id',), ('brand_norm',), ('brand_raw',), ('brand_raw2',), ('model_group_norm',), ('model_group_raw',), ('model_norm',), ('model_raw',), ('model_raw2',), ('variant_norm',), ('variant_raw',), ('variant_raw2',), ('variant_raw3',), ('variant_raw4',)]
        cursor.fetchall.return_value = [
            (7, 'TOYOTA', None, None, 'NO MODEL GROUP', None, 'COROLLA', None, None, 'HYBRID', None, None, None, None),
            (8, 'TOYOTA', None, None, 'NO MODEL GROUP', None, 'COROLLA', None, None, 'HYBRID', None, None, None, None),
        ]

        status, matches = service._classify_fill_record(
            cursor,
            set(service.STANDARD_DISPLAY_COLUMNS),
            {'brand': 'toyota', 'model_group': None, 'model': 'corolla', 'variant': 'hybrid'},
        )

        self.assertEqual(status, 'ambiguous')
        self.assertEqual([match['id'] for match in matches], [7, 8])

    @patch('dashboard.services.cars_standard_maintenance._classify_fill_record')
    @patch('dashboard.services.cars_standard_maintenance._fetch_dicts')
    @patch('dashboard.services.cars_standard_maintenance.connection.cursor')
    @patch('dashboard.services.cars_standard_maintenance._count_source_null_rows')
    @patch('dashboard.services.cars_standard_maintenance.get_table_columns')
    @patch('dashboard.services.cars_standard_maintenance.ensure_fill_schema')
    @patch('dashboard.services.cars_standard_maintenance.validate_sources')
    def test_analyze_null_rows_reuses_classification_and_reports_candidates(self, validate_sources, ensure_schema, get_columns, count_rows, cursor, fetch_dicts, classify):
        validate_sources.return_value = ['carlistmy']
        get_columns.return_value = set(service.STANDARD_DISPLAY_COLUMNS)
        count_rows.return_value = 3
        cursor.return_value.__enter__.return_value.execute = Mock()
        fetch_dicts.return_value = [
            {'id': 1, 'source': 'carlistmy', 'brand': 'Toyota', 'model_group': None, 'model': 'Corolla', 'variant': 'Hybrid'},
            {'id': 2, 'source': 'carlistmy', 'brand': 'Honda', 'model_group': None, 'model': 'City', 'variant': 'V'},
            {'id': 3, 'source': 'carlistmy', 'brand': 'BMW', 'model_group': None, 'model': 'X1', 'variant': 'sDrive'},
        ]
        classify.side_effect = [
            ('matched', [{'id': 10}]),
            ('unmatched', []),
            ('ambiguous', [{'id': 20}, {'id': 21}]),
        ]

        result = service.analyze_null_rows('cars_unified', 'carlistmy', 50)

        ensure_schema.assert_called_once_with('cars_unified')
        self.assertEqual(result['total_null_rows'], 3)
        self.assertEqual(result['estimated_matched'], 1)
        self.assertEqual(result['estimated_unmatched'], 1)
        self.assertEqual(result['estimated_ambiguous'], 1)
        self.assertEqual(result['distinct_unmatched_standards_count'], 1)
        self.assertEqual(result['distinct_normalized_candidates'][0]['brand_norm'], 'HONDA')
        self.assertEqual(result['sample_ambiguous_records'][0]['candidate_ids'], [20, 21])


class CarsStandardMergeServiceTests(SimpleTestCase):
    def make_standard(self, row_id, **values):
        defaults = {
            'brand_norm': 'BMW',
            'brand_raw': None,
            'brand_raw2': None,
            'model_group_norm': 'NO MODEL GROUP',
            'model_group_raw': None,
            'model_norm': 'X1',
            'model_raw': None,
            'model_raw2': None,
            'variant_norm': 'S DRIVE 20I',
            'variant_raw': None,
            'variant_raw2': None,
            'variant_raw3': None,
            'variant_raw4': None,
        }
        defaults.update(values)
        return SimpleNamespace(id=row_id, **defaults)

    @patch('dashboard.services.cars_standard_maintenance.get_fk_delete_rules')
    @patch('dashboard.services.cars_standard_maintenance.get_reference_counts')
    @patch('dashboard.services.cars_standard_maintenance.CarsStandard.objects.get')
    def test_merge_preview_suggests_aliases_and_reports_fallback_tables(self, objects_get, reference_counts, fk_rules):
        source = self.make_standard(2, variant_norm='SDRIVE 20I')
        target = self.make_standard(1, variant_norm='S DRIVE 20I')
        objects_get.side_effect = [source, target]
        reference_counts.return_value = {'cars_unified': 3, 'carsome': 1, 'cars_unified_ind': 0, 'cars_unified_jp': 0}
        fk_rules.return_value = {'cars_unified': 'SET NULL', 'carsome': 'NO ACTION', 'cars_unified_ind': 'UNKNOWN', 'cars_unified_jp': 'SET NULL'}

        preview = service.get_merge_preview(2, 1)

        self.assertEqual(preview['source_id'], 2)
        self.assertEqual(preview['target_id'], 1)
        self.assertEqual(preview['alias_changes'], {'variant_raw': 'SDRIVE 20I'})
        self.assertEqual(preview['manual_null_fallback_tables'], ['carsome', 'cars_unified_ind'])
        self.assertEqual(preview['affected_references']['cars_unified'], 3)

    @patch('dashboard.services.cars_standard_maintenance.CarsStandardAuditLog.objects.create')
    @patch('dashboard.services.cars_standard_maintenance.get_null_reference_counts')
    @patch('dashboard.services.cars_standard_maintenance.manually_null_references')
    @patch('dashboard.services.cars_standard_maintenance.get_fk_delete_rules')
    @patch('dashboard.services.cars_standard_maintenance.get_reference_counts')
    @patch('dashboard.services.cars_standard_maintenance.validate_merge_preview_token')
    @patch('dashboard.services.cars_standard_maintenance.transaction.atomic')
    @patch('dashboard.services.cars_standard_maintenance.CarsStandard.objects')
    def test_execute_merge_updates_aliases_deletes_source_and_audits(self, objects, atomic, validate_token, reference_counts, fk_rules, manual_null, null_counts, audit_create):
        source = self.make_standard(2, variant_norm='SDRIVE 20I')
        source.delete = Mock()
        target = self.make_standard(1, variant_norm='S DRIVE 20I')
        target.save = Mock()
        queryset = objects.select_for_update.return_value.filter.return_value.order_by
        queryset.return_value = [target, source]
        atomic.return_value = nullcontext()
        reference_counts.side_effect = [
            {'cars_unified': 2, 'carsome': 1, 'cars_unified_ind': 0, 'cars_unified_jp': 0},
            {'cars_unified': 0, 'carsome': 0, 'cars_unified_ind': 0, 'cars_unified_jp': 0},
            {'cars_unified': 5, 'carsome': 1, 'cars_unified_ind': 0, 'cars_unified_jp': 0},
        ]
        fk_rules.return_value = {'cars_unified': 'SET NULL', 'carsome': 'NO ACTION', 'cars_unified_ind': 'SET NULL', 'cars_unified_jp': 'SET NULL'}
        manual_null.return_value = {'carsome': 1}
        null_counts.return_value = {'cars_unified': 10, 'carsome': 4, 'cars_unified_ind': 0, 'cars_unified_jp': 0}

        result = service.execute_merge(2, 1, {'variant_raw': 'SDRIVE 20I'}, SimpleNamespace(id=99), 'token')

        validate_token.assert_called_once_with('token', 2, 1, {'variant_raw': 'SDRIVE 20I'}, 99)
        target.save.assert_called_once_with(update_fields=['variant_raw'])
        source.delete.assert_called_once_with()
        manual_null.assert_called_once_with(2, ['carsome'])
        audit_create.assert_called_once()
        self.assertEqual(result['updated_aliases'], {'variant_raw': 'SDRIVE 20I'})
        self.assertEqual(result['manual_null_fallback'], {'carsome': 1})

    def test_execute_merge_rejects_same_source_and_target(self):
        with self.assertRaises(ValueError):
            service.execute_merge(1, 1, {}, SimpleNamespace(id=99), 'token')


class CarsStandardBulkAddServiceTests(TestCase):
    def setUp(self):
        with service.connection.cursor() as cursor:
            cursor.execute('DROP TABLE IF EXISTS cars_unified, carsome, cars_unified_ind, cars_unified_jp, cars_standard CASCADE')
            cursor.execute('''
                CREATE TABLE cars_standard (
                    id BIGSERIAL PRIMARY KEY,
                    brand_norm varchar(100) NOT NULL,
                    brand_raw varchar(100),
                    brand_raw2 varchar(100),
                    model_group_norm varchar(100) NOT NULL,
                    model_group_raw varchar(100),
                    model_norm varchar(100) NOT NULL,
                    model_raw varchar(100),
                    model_raw2 varchar(100),
                    variant_norm varchar(100) NOT NULL,
                    variant_raw varchar(100),
                    variant_raw2 varchar(100),
                    variant_raw3 varchar(100),
                    variant_raw4 varchar(100)
                )
            ''')
            for table_name in ('cars_unified', 'carsome', 'cars_unified_ind', 'cars_unified_jp'):
                cursor.execute(f'''
                    CREATE TABLE {table_name} (
                        id BIGSERIAL PRIMARY KEY,
                        source varchar(50) NOT NULL,
                        cars_standard_id bigint,
                        brand varchar(100),
                        model_group varchar(100),
                        model varchar(100),
                        variant varchar(100)
                    )
                ''')
        self.user = User.objects.create_user(username='bulkadmin')

    def test_cars_unified_jp_is_discoverable_and_counted(self):
        with service.connection.cursor() as cursor:
            cursor.execute("INSERT INTO cars_unified_jp (source, cars_standard_id, brand, model, variant) VALUES ('auctionjp', NULL, 'Toyota', 'Aqua', 'G')")

        summary = {row['table']: row for row in service.get_null_count_summary()}

        self.assertEqual(service.discover_sources('cars_unified_jp'), ['auctionjp'])
        self.assertEqual(summary['cars_unified_jp']['null_count'], 1)
        self.assertEqual(summary['cars_unified_jp']['sources'], [{'source': 'auctionjp', 'null_count': 1}])

    def test_bulk_add_inserts_unique_missing_and_skips_existing_duplicate_sources(self):
        with service.connection.cursor() as cursor:
            cursor.execute("INSERT INTO cars_standard (brand_norm, model_group_norm, model_norm, variant_norm) VALUES ('TOYOTA', 'NO MODEL GROUP', 'COROLLA', 'HYBRID')")
            cursor.execute("INSERT INTO cars_unified (source, cars_standard_id, brand, model_group, model, variant) VALUES ('carlistmy', NULL, 'Honda', NULL, 'City', 'V'), ('carlistmy', NULL, ' honda ', '-', ' city ', ' v '), ('carlistmy', NULL, 'Toyota', NULL, 'Corolla', 'Hybrid')")

        preview = service.get_insert_missing_preview('cars_unified', ['carlistmy'])
        token = service.build_insert_missing_preview_token('cars_unified', ['carlistmy'], self.user.id)
        result = service.execute_insert_missing_cars_standard('cars_unified', ['carlistmy'], self.user, preview_token=token)

        self.assertEqual(preview['distinct_candidates'], 2)
        self.assertEqual(preview['already_exists'], 1)
        self.assertEqual(preview['rows_to_insert'], 1)
        self.assertEqual(result['inserted'], 1)
        self.assertEqual(service.CarsStandard.objects.filter(brand_norm='HONDA', model_group_norm='NO MODEL GROUP', model_norm='CITY', variant_norm='V').count(), 1)

    def test_bulk_add_uses_useful_source_model_group(self):
        with service.connection.cursor() as cursor:
            cursor.execute("INSERT INTO cars_unified (source, cars_standard_id, brand, model_group, model, variant) VALUES ('carlistmy', NULL, 'Nissan', 'SUV', 'X Trail', 'VL')")

        token = service.build_insert_missing_preview_token('cars_unified', ['carlistmy'], self.user.id)
        result = service.execute_insert_missing_cars_standard('cars_unified', ['carlistmy'], self.user, preview_token=token)

        self.assertEqual(result['inserted'], 1)
        self.assertTrue(service.CarsStandard.objects.filter(brand_norm='NISSAN', model_group_norm='SUV', model_norm='X TRAIL', variant_norm='VL').exists())

    def test_bulk_add_dry_run_does_not_insert(self):
        with service.connection.cursor() as cursor:
            cursor.execute("INSERT INTO cars_unified (source, cars_standard_id, brand, model_group, model, variant) VALUES ('carlistmy', NULL, 'Mazda', NULL, '3', 'High')")

        result = service.execute_insert_missing_cars_standard('cars_unified', ['carlistmy'], self.user, dry_run=True)

        self.assertEqual(result['status'], 'dry_run')
        self.assertEqual(result['inserted'], 0)
        self.assertFalse(service.CarsStandard.objects.filter(brand_norm='MAZDA').exists())

    def test_bulk_add_works_when_source_table_has_no_model_group(self):
        with service.connection.cursor() as cursor:
            cursor.execute('ALTER TABLE cars_unified DROP COLUMN model_group')
            cursor.execute("INSERT INTO cars_unified (source, cars_standard_id, brand, model, variant) VALUES ('carlistmy', NULL, 'Mazda', '3', 'High')")

        preview = service.get_insert_missing_preview('cars_unified', ['carlistmy'])
        token = service.build_insert_missing_preview_token('cars_unified', ['carlistmy'], self.user.id)
        result = service.execute_insert_missing_cars_standard('cars_unified', ['carlistmy'], self.user, preview_token=token)

        self.assertEqual(preview['rows_to_insert'], 1)
        self.assertEqual(result['inserted'], 1)
        self.assertTrue(service.CarsStandard.objects.filter(brand_norm='MAZDA', model_group_norm='NO MODEL GROUP', model_norm='3', variant_norm='HIGH').exists())

    def test_fill_after_bulk_add_matches_newly_inserted_standard(self):
        with service.connection.cursor() as cursor:
            cursor.execute("INSERT INTO cars_unified (source, cars_standard_id, brand, model_group, model, variant) VALUES ('carlistmy', NULL, 'Honda', NULL, 'City', 'V')")

        insert_token = service.build_insert_missing_preview_token('cars_unified', ['carlistmy'], self.user.id)
        insert_result = service.execute_insert_missing_cars_standard('cars_unified', ['carlistmy'], self.user, preview_token=insert_token)
        fill_token = service.build_fill_preview_token('cars_unified', ['carlistmy'], 500, self.user.id)
        fill_result = service.execute_fill_standard_id('cars_unified', ['carlistmy'], self.user, batch_size=500, preview_token=fill_token)

        self.assertEqual(insert_result['inserted'], 1)
        self.assertEqual(fill_result['updated'], 1)
        with service.connection.cursor() as cursor:
            cursor.execute('SELECT cars_standard_id FROM cars_unified')
            self.assertIsNotNone(cursor.fetchone()[0])

    def test_execute_fill_leaves_ambiguous_source_null(self):
        with service.connection.cursor() as cursor:
            cursor.execute("INSERT INTO cars_standard (brand_norm, model_group_norm, model_norm, variant_norm) VALUES ('TOYOTA', 'NO MODEL GROUP', 'COROLLA', 'HYBRID'), ('TOYOTA', 'NO MODEL GROUP', 'COROLLA', 'HYBRID')")
            cursor.execute("INSERT INTO cars_unified (source, cars_standard_id, brand, model_group, model, variant) VALUES ('carlistmy', NULL, 'Toyota', NULL, 'Corolla', 'Hybrid')")

        token = service.build_fill_preview_token('cars_unified', ['carlistmy'], 500, self.user.id)
        result = service.execute_fill_standard_id('cars_unified', ['carlistmy'], self.user, batch_size=500, preview_token=token)

        self.assertEqual(result['updated'], 0)
        self.assertEqual(result['ambiguous'], 1)
        with service.connection.cursor() as cursor:
            cursor.execute('SELECT cars_standard_id FROM cars_unified')
            self.assertIsNone(cursor.fetchone()[0])

    def test_ambiguous_resolver_groups_all_null_rows(self):
        with service.connection.cursor() as cursor:
            cursor.execute("INSERT INTO cars_standard (brand_norm, model_group_norm, model_norm, variant_norm) VALUES ('TOYOTA', 'NO MODEL GROUP', 'COROLLA', 'HYBRID'), ('TOYOTA', 'NO MODEL GROUP', 'COROLLA', 'HYBRID'), ('HONDA', 'NO MODEL GROUP', 'CITY', 'V'), ('HONDA', 'NO MODEL GROUP', 'CITY', 'V')")
            cursor.execute("INSERT INTO cars_unified (source, cars_standard_id, brand, model_group, model, variant) VALUES ('carlistmy', NULL, 'Toyota', NULL, 'Corolla', 'Hybrid'), ('carlistmy', NULL, 'Toyota', NULL, 'Corolla', 'Hybrid'), ('carlistmy', NULL, 'Honda', NULL, 'City', 'V')")

        result = service.get_ambiguous_resolver_groups('cars_unified', 'carlistmy', 10)

        self.assertEqual(result['total_null_rows'], 3)
        self.assertEqual(result['scanned_rows'], 3)
        self.assertEqual(result['ambiguous_count'], 3)
        self.assertEqual(result['group_count'], 2)
        self.assertEqual(len(result['groups']), 2)
        self.assertFalse(result['display_truncated'])
        self.assertEqual(result['groups'][0]['row_count'], 2)
        self.assertEqual(result['groups'][0]['source_brand'], 'Toyota')
        self.assertEqual(result['groups'][0]['sample_source_row_ids'], [1, 2])
        self.assertEqual(len(result['groups'][0]['candidates']), 2)


class CarsStandardCrudServiceTests(TestCase):
    def setUp(self):
        with service.connection.cursor() as cursor:
            cursor.execute('DROP TABLE IF EXISTS cars_unified, carsome, cars_unified_ind, cars_unified_jp, cars_standard CASCADE')
            cursor.execute('''
                CREATE TABLE cars_standard (
                    id BIGSERIAL PRIMARY KEY,
                    brand_norm varchar(100) NOT NULL,
                    brand_raw varchar(100),
                    brand_raw2 varchar(100),
                    model_group_norm varchar(100) NOT NULL,
                    model_group_raw varchar(100),
                    model_norm varchar(100) NOT NULL,
                    model_raw varchar(100),
                    model_raw2 varchar(100),
                    variant_norm varchar(100) NOT NULL,
                    variant_raw varchar(100),
                    variant_raw2 varchar(100),
                    variant_raw3 varchar(100),
                    variant_raw4 varchar(100)
                )
            ''')
            for table_name in ('cars_unified', 'carsome', 'cars_unified_ind', 'cars_unified_jp'):
                cursor.execute(f'''
                    CREATE TABLE {table_name} (
                        id BIGSERIAL PRIMARY KEY,
                        source varchar(50) NOT NULL DEFAULT 'test',
                        cars_standard_id bigint REFERENCES cars_standard(id) ON DELETE SET NULL,
                        brand varchar(100),
                        model_group varchar(100),
                        model varchar(100),
                        variant varchar(100)
                    )
                ''')
        self.user = User.objects.create_user(username='crudadmin')

    def test_create_and_update_normalize_required_fields(self):
        row = service.create_cars_standard(
            {
                'brand_norm': ' honda ',
                'model_group_norm': '',
                'model_norm': ' city ',
                'variant_norm': ' v ',
                'brand_raw': 'Honda',
            },
            self.user,
        )

        self.assertEqual(row.brand_norm, 'HONDA')
        self.assertEqual(row.model_group_norm, 'NO MODEL GROUP')
        self.assertEqual(row.model_norm, 'CITY')
        self.assertEqual(row.variant_norm, 'V')

        result = service.update_cars_standard(row.id, {**service.serialize_cars_standard(row), 'model_norm': ' civic '}, self.user)

        self.assertEqual(result['updated_fields']['model_norm'], 'CIVIC')
        self.assertEqual(service.CarsStandard.objects.get(pk=row.id).model_norm, 'CIVIC')
        with self.assertRaises(ValueError):
            service.update_cars_standard(row.id, {**service.serialize_cars_standard(row), 'brand_norm': ' '}, self.user)

    def test_delete_hard_deletes_and_database_sets_references_null(self):
        row = service.create_cars_standard(
            {'brand_norm': 'TOYOTA', 'model_group_norm': 'NO MODEL GROUP', 'model_norm': 'COROLLA', 'variant_norm': 'G'},
            self.user,
        )
        with service.connection.cursor() as cursor:
            for table_name in ('cars_unified', 'carsome', 'cars_unified_ind', 'cars_unified_jp'):
                cursor.execute(f"INSERT INTO {table_name} (cars_standard_id, brand, model, variant) VALUES (%s, 'Toyota', 'Corolla', 'G')", [row.id])

        preview = service.get_delete_preview(row.id)
        result = service.delete_cars_standard(row.id, self.user)

        self.assertTrue(preview['all_set_null'])
        self.assertEqual(service.get_fk_delete_rules(), {'cars_unified': 'SET NULL', 'carsome': 'SET NULL', 'cars_unified_ind': 'SET NULL', 'cars_unified_jp': 'SET NULL'})
        self.assertEqual(preview['affected_references'], {'cars_unified': 1, 'carsome': 1, 'cars_unified_ind': 1, 'cars_unified_jp': 1})
        self.assertFalse(service.CarsStandard.objects.filter(pk=row.id).exists())
        self.assertEqual(result['affected_references_after'], {'cars_unified': 0, 'carsome': 0, 'cars_unified_ind': 0, 'cars_unified_jp': 0})
        with service.connection.cursor() as cursor:
            for table_name in ('cars_unified', 'carsome', 'cars_unified_ind', 'cars_unified_jp'):
                cursor.execute(f'SELECT COUNT(*) FROM {table_name} WHERE cars_standard_id IS NULL')
                self.assertEqual(cursor.fetchone()[0], 1)


class CarsStandardAdminCrudEndpointTests(TestCase):
    def setUp(self):
        self.admin_group = Group.objects.create(name='Admin')
        self.admin_user = User.objects.create_user(username='endpointadmin', password='pass')
        self.admin_user.groups.add(self.admin_group)
        with service.connection.cursor() as cursor:
            cursor.execute('DROP TABLE IF EXISTS cars_unified, carsome, cars_unified_ind, cars_unified_jp, cars_standard CASCADE')
            cursor.execute('''
                CREATE TABLE cars_standard (
                    id BIGSERIAL PRIMARY KEY,
                    brand_norm varchar(100) NOT NULL,
                    brand_raw varchar(100),
                    brand_raw2 varchar(100),
                    model_group_norm varchar(100) NOT NULL,
                    model_group_raw varchar(100),
                    model_norm varchar(100) NOT NULL,
                    model_raw varchar(100),
                    model_raw2 varchar(100),
                    variant_norm varchar(100) NOT NULL,
                    variant_raw varchar(100),
                    variant_raw2 varchar(100),
                    variant_raw3 varchar(100),
                    variant_raw4 varchar(100)
                )
            ''')
            for table_name in ('cars_unified', 'carsome', 'cars_unified_ind', 'cars_unified_jp'):
                cursor.execute(f'''
                    CREATE TABLE {table_name} (
                        id BIGSERIAL PRIMARY KEY,
                        source varchar(50) NOT NULL DEFAULT 'test',
                        cars_standard_id bigint REFERENCES cars_standard(id) ON DELETE SET NULL,
                        brand varchar(100),
                        model_group varchar(100),
                        model varchar(100),
                        variant varchar(100)
                    )
                ''')
        self.client.force_login(self.admin_user)

    def test_admin_create_endpoint_normalizes_required_fields(self):
        response = self.client.post(
            reverse('admin_cars_standard_create', kwargs={'username': self.admin_user.username}),
            {'brand_norm': ' honda ', 'model_norm': ' city ', 'variant_norm': ' v ', 'brand_raw': 'Honda'},
        )

        row = service.CarsStandard.objects.get()
        self.assertEqual(response.status_code, 302)
        self.assertIn(f'edit_id={row.id}', response.url)
        self.assertEqual(row.brand_norm, 'HONDA')
        self.assertEqual(row.model_group_norm, 'NO MODEL GROUP')
        self.assertEqual(row.model_norm, 'CITY')
        self.assertEqual(row.variant_norm, 'V')

    def test_admin_update_endpoint_normalizes_and_persists_edits(self):
        row = service.create_cars_standard(
            {'brand_norm': 'TOYOTA', 'model_group_norm': 'NO MODEL GROUP', 'model_norm': 'COROLLA', 'variant_norm': 'G'},
            self.admin_user,
        )

        response = self.client.post(
            reverse('admin_cars_standard_update', kwargs={'username': self.admin_user.username}),
            {
                'cars_standard_id': row.id,
                'brand_norm': ' toyota ',
                'model_group_norm': ' sedan ',
                'model_norm': ' corolla altis ',
                'variant_norm': ' hybrid ',
                'model_raw': 'Altis',
            },
        )

        row.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertIn(f'edit_id={row.id}', response.url)
        self.assertEqual(row.model_group_norm, 'SEDAN')
        self.assertEqual(row.model_norm, 'COROLLA ALTIS')
        self.assertEqual(row.variant_norm, 'HYBRID')
        self.assertEqual(row.model_raw, 'Altis')

    def test_admin_delete_preview_and_confirmed_delete_nulls_references(self):
        row = service.create_cars_standard(
            {'brand_norm': 'MAZDA', 'model_group_norm': 'NO MODEL GROUP', 'model_norm': '3', 'variant_norm': 'HIGH'},
            self.admin_user,
        )
        with service.connection.cursor() as cursor:
            cursor.execute("INSERT INTO cars_unified (cars_standard_id, brand, model, variant) VALUES (%s, 'Mazda', '3', 'High')", [row.id])

        preview = self.client.get(reverse('admin_cars_standard', kwargs={'username': self.admin_user.username}), {'delete_id': row.id})
        blocked = self.client.post(reverse('admin_cars_standard_delete', kwargs={'username': self.admin_user.username}), {'cars_standard_id': row.id})
        deleted = self.client.post(reverse('admin_cars_standard_delete', kwargs={'username': self.admin_user.username}), {'cars_standard_id': row.id, 'confirm_set_null': 'on'})

        self.assertEqual(preview.status_code, 200)
        self.assertContains(preview, 'cars_unified')
        self.assertContains(preview, 'SET NULL')
        self.assertEqual(blocked.status_code, 302)
        self.assertEqual(deleted.status_code, 302)
        self.assertFalse(service.CarsStandard.objects.filter(pk=row.id).exists())
        with service.connection.cursor() as cursor:
            cursor.execute('SELECT COUNT(*) FROM cars_unified WHERE cars_standard_id IS NULL')
            self.assertEqual(cursor.fetchone()[0], 1)

    def test_admin_table_filters_can_be_combined(self):
        service.create_cars_standard({'brand_norm': 'HONDA', 'model_group_norm': 'NO MODEL GROUP', 'model_norm': 'CITY', 'variant_norm': 'V'}, self.admin_user)
        service.create_cars_standard({'brand_norm': 'HONDA', 'model_group_norm': 'NO MODEL GROUP', 'model_norm': 'CIVIC', 'variant_norm': 'RS'}, self.admin_user)
        service.create_cars_standard({'brand_norm': 'TOYOTA', 'model_group_norm': 'NO MODEL GROUP', 'model_norm': 'CITY', 'variant_norm': 'G'}, self.admin_user)

        response = self.client.get(
            reverse('admin_cars_standard', kwargs={'username': self.admin_user.username}),
            {'brand_norm': 'hon', 'model_norm': 'city'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'HONDA')
        self.assertContains(response, 'CITY')
        self.assertNotContains(response, 'CIVIC')
        self.assertNotContains(response, 'TOYOTA')

        city = service.CarsStandard.objects.get(brand_norm='HONDA', model_norm='CITY')
        ajax_response = self.client.get(
            reverse('admin_cars_standard', kwargs={'username': self.admin_user.username}),
            {'id': str(city.id)},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(ajax_response.status_code, 200)
        self.assertEqual(ajax_response.json()['rows'][0]['id'], city.id)

        multi_response = self.client.get(
            reverse('admin_cars_standard', kwargs={'username': self.admin_user.username}),
            {'brand_norm': 'honda,toyota', 'model_norm': 'city'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(multi_response.status_code, 200)
        brands = {row['brand_norm'] for row in multi_response.json()['rows']}
        self.assertEqual(brands, {'HONDA', 'TOYOTA'})

        multi_id_response = self.client.get(
            reverse('admin_cars_standard', kwargs={'username': self.admin_user.username}),
            {'id': f'{city.id},999999'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual([row['id'] for row in multi_id_response.json()['rows']], [city.id])

    def test_admin_page_renders_no_js_edit_delete_fallbacks(self):
        row = service.create_cars_standard(
            {'brand_norm': 'HONDA', 'model_group_norm': 'NO MODEL GROUP', 'model_norm': 'CITY', 'variant_norm': 'V'},
            self.admin_user,
        )

        response = self.client.get(reverse('admin_cars_standard', kwargs={'username': self.admin_user.username}), {'edit_id': row.id})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'Edit cars_standard #{row.id}')
        self.assertContains(response, f'?delete_id={row.id}')
        self.assertContains(response, "table.addEventListener('focusin'")

    def test_ambiguous_resolver_ajax_returns_grouped_candidates(self):
        with service.connection.cursor() as cursor:
            cursor.execute("INSERT INTO cars_standard (brand_norm, model_group_norm, model_norm, variant_norm) VALUES ('TOYOTA', 'NO MODEL GROUP', 'COROLLA', 'HYBRID'), ('TOYOTA', 'NO MODEL GROUP', 'COROLLA', 'HYBRID')")
            cursor.execute("INSERT INTO cars_unified (source, cars_standard_id, brand, model_group, model, variant) VALUES ('carlistmy', NULL, 'Toyota', NULL, 'Corolla', 'Hybrid')")

        response = self.client.post(
            reverse('admin_cars_standard_ambiguous_resolver', kwargs={'username': self.admin_user.username}),
            {'target_table': 'cars_unified', 'source': 'carlistmy', 'display_limit': 10},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        data = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data['success'])
        self.assertEqual(data['preview']['ambiguous_count'], 1)
        self.assertEqual(data['preview']['groups'][0]['candidate_ids'], [1, 2])
        self.assertEqual(len(data['preview']['groups'][0]['candidates']), 2)

    def test_admin_create_update_delete_ajax_endpoints_return_json(self):
        create_response = self.client.post(
            reverse('admin_cars_standard_create', kwargs={'username': self.admin_user.username}),
            {'brand_norm': ' honda ', 'model_norm': ' city ', 'variant_norm': ' v '},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        created = create_response.json()
        row_id = created['row']['id']

        update_response = self.client.post(
            reverse('admin_cars_standard_update', kwargs={'username': self.admin_user.username}),
            {
                'cars_standard_id': row_id,
                'brand_norm': 'honda',
                'model_group_norm': 'no model group',
                'model_norm': 'civic',
                'variant_norm': 'rs',
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        delete_response = self.client.post(
            reverse('admin_cars_standard_delete', kwargs={'username': self.admin_user.username}),
            {'cars_standard_id': row_id, 'confirm_set_null': 'on'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(create_response.status_code, 200)
        self.assertTrue(created['success'])
        self.assertEqual(created['row']['brand_norm'], 'HONDA')
        self.assertEqual(update_response.status_code, 200)
        self.assertEqual(update_response.json()['row']['model_norm'], 'CIVIC')
        self.assertEqual(delete_response.status_code, 200)
        self.assertFalse(service.CarsStandard.objects.filter(pk=row_id).exists())


class CarsStandardDryRunServiceTests(TestCase):
    @patch('dashboard.services.cars_standard_maintenance.CarsStandardAuditLog.objects.create')
    @patch('dashboard.services.cars_standard_maintenance.get_insert_missing_preview')
    @patch('dashboard.services.cars_standard_maintenance.connection.cursor')
    @patch('dashboard.services.cars_standard_maintenance.ensure_insert_missing_schema')
    @patch('dashboard.services.cars_standard_maintenance.validate_sources')
    @patch('dashboard.services.cars_standard_maintenance.validate_insert_missing_preview_token')
    def test_execute_insert_missing_dry_run_does_not_require_preview_token_or_insert(self, validate_token, validate_sources, ensure_schema, cursor, preview, audit_create):
        validate_sources.return_value = ['carlistmy']
        cursor.return_value.__enter__.return_value.execute = Mock()
        preview.return_value = {
            'status': 'preview',
            'table_name': 'cars_unified',
            'sources': ['carlistmy'],
            'distinct_candidates': 2,
            'already_exists': 1,
            'rows_to_insert': 1,
            'inserted': 0,
            'insert_sample': [],
        }

        result = service.execute_insert_missing_cars_standard('cars_unified', ['carlistmy'], SimpleNamespace(id=7), dry_run=True)

        validate_token.assert_not_called()
        ensure_schema.assert_called_once_with('cars_unified')
        self.assertEqual(result['status'], 'dry_run')
        self.assertEqual(result['inserted'], 0)
        audit_create.assert_called_once()

    @patch('dashboard.services.cars_standard_maintenance.CarsStandardAuditLog.objects.create')
    @patch('dashboard.services.cars_standard_maintenance.get_fill_standard_id_preview')
    @patch('dashboard.services.cars_standard_maintenance.ensure_fill_schema')
    @patch('dashboard.services.cars_standard_maintenance.validate_sources')
    @patch('dashboard.services.cars_standard_maintenance.validate_fill_preview_token')
    def test_execute_fill_dry_run_does_not_require_preview_token_or_update(self, validate_token, validate_sources, ensure_schema, preview, audit_create):
        validate_sources.return_value = ['carsome']
        preview.return_value = {
            'status': 'preview',
            'table_name': 'carsome',
            'sources': ['carsome'],
            'batch_size': 500,
            'null_rows': 3,
            'scanned_rows': 3,
            'estimated_matched': 2,
            'estimated_unmatched': 1,
            'estimated_ambiguous': 0,
            'per_source': [],
        }

        result = service.execute_fill_standard_id('carsome', ['carsome'], SimpleNamespace(id=7), dry_run=True)

        validate_token.assert_not_called()
        ensure_schema.assert_called_once_with('carsome')
        self.assertEqual(result['status'], 'dry_run')
        self.assertEqual(result['estimated_matched'], 2)
        audit_create.assert_called_once()


class CarsStandardAccessControlTests(TestCase):
    def setUp(self):
        self.admin_group = Group.objects.create(name='Admin')
        self.user_group = Group.objects.create(name='User')
        self.admin_user = User.objects.create_user(username='adminuser', password='pass')
        self.admin_user.groups.add(self.admin_group)
        self.regular_user = User.objects.create_user(username='regularuser', password='pass')
        self.regular_user.groups.add(self.user_group)

    def overview_context(self):
        return {
            'cars_standard_total': 0,
            'null_count_summary': [],
            'maintenance_jobs': [],
        }

    def search_context(self):
        return {
            'page_obj': Paginator([], 25).get_page(1),
            'columns': [],
            'query': '',
        }

    def test_non_admin_is_blocked_from_cars_standard_pages_and_endpoints(self):
        self.client.force_login(self.regular_user)
        endpoints = [
            ('get', reverse('admin_cars_standard', kwargs={'username': self.regular_user.username}), {}),
            ('post', reverse('admin_cars_standard_create', kwargs={'username': self.regular_user.username}), {}),
            ('post', reverse('admin_cars_standard_update', kwargs={'username': self.regular_user.username}), {}),
            ('post', reverse('admin_cars_standard_delete', kwargs={'username': self.regular_user.username}), {}),
            ('post', reverse('admin_cars_standard_merge_preview', kwargs={'username': self.regular_user.username}), {}),
            ('post', reverse('admin_cars_standard_merge_execute', kwargs={'username': self.regular_user.username}), {}),
            ('post', reverse('admin_cars_standard_null_inspector', kwargs={'username': self.regular_user.username}), {}),
            ('post', reverse('admin_cars_standard_ambiguous_resolver', kwargs={'username': self.regular_user.username}), {}),
            ('post', reverse('admin_cars_standard_insert_missing_preview', kwargs={'username': self.regular_user.username}), {}),
            ('post', reverse('admin_cars_standard_insert_missing_execute', kwargs={'username': self.regular_user.username}), {}),
            ('post', reverse('admin_cars_standard_fill_preview', kwargs={'username': self.regular_user.username}), {}),
            ('post', reverse('admin_cars_standard_fill_execute', kwargs={'username': self.regular_user.username}), {}),
            ('post', reverse('admin_cars_standard_fill_again', kwargs={'username': self.regular_user.username}), {}),
            ('post', reverse('admin_cars_standard_job_start', kwargs={'username': self.regular_user.username}), {}),
            ('get', reverse('admin_cars_standard_jobs_status', kwargs={'username': self.regular_user.username}), {}),
        ]

        for method, url, data in endpoints:
            with self.subTest(url=url):
                response = getattr(self.client, method)(url, data)
                self.assertEqual(response.status_code, 403)

    @patch('dashboard.views.search_cars_standard')
    @patch('dashboard.views.get_admin_overview')
    @patch('dashboard.views.get_pending_users_count')
    def test_admin_can_access_cars_standard_page(self, pending_count, overview, search):
        pending_count.return_value = 0
        overview.return_value = self.overview_context()
        search.return_value = self.search_context()
        self.client.force_login(self.admin_user)

        response = self.client.get(reverse('admin_cars_standard', kwargs={'username': self.admin_user.username}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Cars Standard Maintenance')
        self.assertNotContains(response, 'Merge Duplicate Rows')
        self.assertNotContains(response, 'admin_cars_standard_merge_preview')

    @patch('dashboard.forms.validate_sources')
    @patch('dashboard.views.search_cars_standard')
    @patch('dashboard.views.get_admin_overview')
    @patch('dashboard.views.get_pending_users_count')
    @patch('dashboard.views.analyze_null_rows')
    def test_null_inspector_endpoint_renders_analysis(self, analyze, pending_count, overview, search, validate_sources):
        validate_sources.return_value = ['carlistmy']
        pending_count.return_value = 0
        overview.return_value = self.overview_context()
        search.return_value = self.search_context()
        analyze.return_value = {
            'message': 'Analyzed 1 of 1 NULL rows for cars_unified/carlistmy.',
            'table_name': 'cars_unified',
            'source': 'carlistmy',
            'total_null_rows': 1,
            'scanned_rows': 1,
            'preview_truncated': False,
            'estimated_matched': 0,
            'estimated_unmatched': 1,
            'estimated_ambiguous': 0,
            'distinct_unmatched_standards_count': 1,
            'sample_unmatched_records': [],
            'sample_ambiguous_records': [],
            'distinct_normalized_candidates': [{'brand_norm': 'HONDA', 'model_group_norm': 'NO MODEL GROUP', 'model_norm': 'CITY', 'variant_norm': 'V'}],
        }
        self.client.force_login(self.admin_user)

        response = self.client.post(
            reverse('admin_cars_standard_null_inspector', kwargs={'username': self.admin_user.username}),
            {'target_table': 'cars_unified', 'source': 'carlistmy', 'preview_limit': 50},
        )

        self.assertEqual(response.status_code, 200)
        analyze.assert_called_once_with('cars_unified', 'carlistmy', 50)
        self.assertContains(response, 'NULL Inspector')
        self.assertContains(response, 'HONDA')

    @patch('dashboard.views.execute_merge')
    def test_merge_execute_requires_confirmation(self, execute_merge):
        self.client.force_login(self.admin_user)

        response = self.client.post(
            reverse('admin_cars_standard_merge_execute', kwargs={'username': self.admin_user.username}),
            {'source_id': 2, 'target_id': 1, 'alias_changes': '{}', 'preview_token': 'token'},
        )

        self.assertEqual(response.status_code, 302)
        execute_merge.assert_not_called()

    @patch('dashboard.forms.validate_sources')
    @patch('dashboard.views.CarsStandardMaintenanceJob.objects.create')
    def test_insert_execute_requires_confirmation_before_queueing_job(self, create_job, validate_sources):
        validate_sources.return_value = ['carlistmy']
        self.client.force_login(self.admin_user)

        response = self.client.post(
            reverse('admin_cars_standard_insert_missing_execute', kwargs={'username': self.admin_user.username}),
            {'target_table': 'cars_unified', 'sources': 'carlistmy', 'preview_token': 'token'},
        )

        self.assertEqual(response.status_code, 302)
        create_job.assert_not_called()

    @patch('dashboard.forms.validate_sources')
    @patch('dashboard.views.CarsStandardMaintenanceJob.objects.create')
    def test_fill_execute_requires_confirmation_before_queueing_job(self, create_job, validate_sources):
        validate_sources.return_value = ['carsome']
        self.client.force_login(self.admin_user)

        response = self.client.post(
            reverse('admin_cars_standard_fill_execute', kwargs={'username': self.admin_user.username}),
            {'target_table': 'carsome', 'sources': 'carsome', 'batch_size': 500, 'preview_token': 'token'},
        )

        self.assertEqual(response.status_code, 302)
        create_job.assert_not_called()

    def test_jobs_status_serializes_summary_samples_and_fill_again_action(self):
        self.client.force_login(self.admin_user)
        CarsStandardMaintenanceJob.objects.create(
            job_type=CarsStandardMaintenanceJob.JOB_INSERT_MISSING,
            status=CarsStandardMaintenanceJob.STATUS_SUCCESS,
            requested_by=self.admin_user,
            target_table='cars_unified',
            sources=['carlistmy'],
            dry_run=False,
            result={'inserted': 1, 'message': 'Inserted 1 rows.'},
        )
        CarsStandardMaintenanceJob.objects.create(
            job_type=CarsStandardMaintenanceJob.JOB_FILL_STANDARD_ID,
            status=CarsStandardMaintenanceJob.STATUS_FAILED,
            requested_by=self.admin_user,
            error_message='{"error":"Queue unavailable"}',
        )

        response = self.client.get(reverse('admin_cars_standard_jobs_status', kwargs={'username': self.admin_user.username}))
        jobs = json.loads(response.content)['jobs']
        job = next(job for job in jobs if job['job_type'] == CarsStandardMaintenanceJob.JOB_INSERT_MISSING)
        failed_job = next(job for job in jobs if job['job_type'] == CarsStandardMaintenanceJob.JOB_FILL_STANDARD_ID)

        self.assertEqual(job['job_type_display'], 'Bulk Add Standards')
        self.assertEqual(job['result_summary'], 'Inserted 1 rows.')
        self.assertNotIn('celery_task_id', job)
        self.assertNotIn('error_message', failed_job)
        self.assertEqual(failed_job['error_summary'], 'Queue unavailable')
        self.assertTrue(job['can_run_fill_again'])
        self.assertFalse(job['dry_run'])

    def test_job_serializer_adds_percent_and_message(self):
        job = CarsStandardMaintenanceJob.objects.create(
            job_type=CarsStandardMaintenanceJob.JOB_FILL_STANDARD_ID,
            status=CarsStandardMaintenanceJob.STATUS_RUNNING,
            requested_by=self.admin_user,
            progress={'current': 5, 'total': 10},
        )

        serialized = service.serialize_maintenance_job(job)

        self.assertEqual(serialized['progress']['percent'], 50)
        self.assertEqual(serialized['progress']['message'], '-')

    @patch('dashboard.services.cars_standard_maintenance.async_to_sync')
    @patch('dashboard.services.cars_standard_maintenance.get_channel_layer')
    def test_broadcast_job_sends_serialized_update(self, get_channel_layer, sync):
        layer = Mock()
        get_channel_layer.return_value = layer
        sender = Mock()
        sync.return_value = sender
        job = CarsStandardMaintenanceJob.objects.create(
            job_type=CarsStandardMaintenanceJob.JOB_FILL_STANDARD_ID,
            requested_by=self.admin_user,
        )

        self.assertTrue(service.broadcast_cars_standard_job(job))

        sync.assert_called_once_with(layer.group_send)
        sender.assert_called_once()
        self.assertEqual(sender.call_args.args[0], service.CARS_STANDARD_JOBS_GROUP)
        self.assertEqual(sender.call_args.args[1]['type'], 'cars_standard_job_update')
        self.assertEqual(sender.call_args.args[1]['job']['id'], job.id)

    @patch('dashboard.views.search_cars_standard')
    @patch('dashboard.views.get_admin_overview')
    @patch('dashboard.views.get_pending_users_count')
    def test_recent_operations_hides_task_id_and_shows_readable_error(self, pending_count, overview, search):
        pending_count.return_value = 0
        job = CarsStandardMaintenanceJob.objects.create(
            job_type=CarsStandardMaintenanceJob.JOB_FILL_STANDARD_ID,
            status=CarsStandardMaintenanceJob.STATUS_FAILED,
            requested_by=self.admin_user,
            target_table='cars_unified',
            sources=['carlistmy'],
            dry_run=True,
            celery_task_id='task-secret',
            error_message='{"error":"Queue unavailable"}',
            progress={'current': 5, 'total': 10, 'message': 'Processed 5 rows'},
        )
        overview.return_value = {**self.overview_context(), 'maintenance_jobs': [service.decorate_maintenance_job(job)]}
        search.return_value = self.search_context()
        self.client.force_login(self.admin_user)

        response = self.client.get(reverse('admin_cars_standard', kwargs={'username': self.admin_user.username}))

        self.assertContains(response, 'Recent Operations')
        self.assertContains(response, 'Fill IDs')
        self.assertContains(response, 'Failed')
        self.assertContains(response, 'Queue unavailable')
        self.assertContains(response, 'Processed 5 rows')
        self.assertContains(response, '/ws/cars-standard/jobs/')
        self.assertContains(response, 'progress-bar')
        self.assertNotContains(response, 'task-secret')
        self.assertNotContains(response, '{"error"')

    @patch('dashboard.tasks.execute_fill_standard_id')
    @patch('dashboard.tasks.execute_insert_missing_cars_standard')
    @patch('dashboard.tasks.insert_missing_cars_standard.apply_async')
    @patch('dashboard.forms.validate_sources')
    def test_background_job_start_queues_celery_and_returns_without_running_service(self, validate_sources, apply_async, execute_insert, execute_fill):
        validate_sources.return_value = ['carlistmy']
        apply_async.return_value = SimpleNamespace(id='task-1')
        self.client.force_login(self.admin_user)

        response = self.client.post(
            reverse('admin_cars_standard_job_start', kwargs={'username': self.admin_user.username}),
            {
                'job_type': CarsStandardMaintenanceJob.JOB_INSERT_MISSING,
                'target_table': 'cars_unified',
                'sources': 'carlistmy',
                'dry_run': 'on',
                'batch_size': 500,
            },
        )

        self.assertEqual(response.status_code, 302)
        apply_async.assert_called_once()
        execute_insert.assert_not_called()
        execute_fill.assert_not_called()
        job = CarsStandardMaintenanceJob.objects.get(job_type=CarsStandardMaintenanceJob.JOB_INSERT_MISSING)
        self.assertEqual(job.status, CarsStandardMaintenanceJob.STATUS_PENDING)
        self.assertEqual(job.celery_task_id, 'task-1')

    @patch('dashboard.tasks.execute_fill_standard_id')
    @patch('dashboard.tasks.execute_insert_missing_cars_standard')
    @patch('dashboard.tasks.insert_missing_cars_standard.apply_async')
    @patch('dashboard.views.validate_insert_missing_preview_token')
    @patch('dashboard.forms.validate_sources')
    def test_insert_execute_with_confirmed_token_queues_celery_without_running_service(self, validate_sources, validate_token, apply_async, execute_insert, execute_fill):
        validate_sources.return_value = ['carlistmy']
        apply_async.return_value = SimpleNamespace(id='task-2')
        self.client.force_login(self.admin_user)

        response = self.client.post(
            reverse('admin_cars_standard_insert_missing_execute', kwargs={'username': self.admin_user.username}),
            {
                'target_table': 'cars_unified',
                'sources': 'carlistmy',
                'preview_token': 'token',
                'confirm': 'on',
            },
        )

        self.assertEqual(response.status_code, 302)
        validate_token.assert_called_once_with('token', 'cars_unified', ['carlistmy'], self.admin_user.id)
        apply_async.assert_called_once()
        execute_insert.assert_not_called()
        execute_fill.assert_not_called()
        job = CarsStandardMaintenanceJob.objects.get(job_type=CarsStandardMaintenanceJob.JOB_INSERT_MISSING)
        self.assertFalse(job.dry_run)
        self.assertEqual(job.parameters['preview_token'], 'token')
        self.assertEqual(job.celery_task_id, 'task-2')

    @patch('dashboard.tasks.execute_fill_standard_id')
    @patch('dashboard.tasks.execute_insert_missing_cars_standard')
    @patch('dashboard.tasks.fill_standard_id.apply_async')
    @patch('dashboard.views.validate_fill_preview_token')
    @patch('dashboard.forms.validate_sources')
    def test_fill_execute_dry_run_queues_without_confirmation_or_token(self, validate_sources, validate_token, apply_async, execute_insert, execute_fill):
        validate_sources.return_value = ['carsome']
        apply_async.return_value = SimpleNamespace(id='task-dry')
        self.client.force_login(self.admin_user)

        response = self.client.post(
            reverse('admin_cars_standard_fill_execute', kwargs={'username': self.admin_user.username}),
            {
                'target_table': 'carsome',
                'sources': 'carsome',
                'batch_size': 500,
                'dry_run': 'on',
            },
        )

        self.assertEqual(response.status_code, 302)
        validate_token.assert_not_called()
        apply_async.assert_called_once()
        execute_insert.assert_not_called()
        execute_fill.assert_not_called()
        job = CarsStandardMaintenanceJob.objects.get(job_type=CarsStandardMaintenanceJob.JOB_FILL_STANDARD_ID)
        self.assertTrue(job.dry_run)
        self.assertEqual(job.parameters['preview_token'], '')
        self.assertEqual(job.celery_task_id, 'task-dry')

    @patch('dashboard.tasks.execute_fill_standard_id')
    @patch('dashboard.tasks.execute_insert_missing_cars_standard')
    @patch('dashboard.tasks.fill_standard_id.apply_async')
    @patch('dashboard.views.validate_fill_preview_token')
    @patch('dashboard.forms.validate_sources')
    def test_fill_execute_with_confirmed_token_queues_celery_without_running_service(self, validate_sources, validate_token, apply_async, execute_insert, execute_fill):
        validate_sources.return_value = ['carsome']
        apply_async.return_value = SimpleNamespace(id='task-3')
        self.client.force_login(self.admin_user)

        response = self.client.post(
            reverse('admin_cars_standard_fill_execute', kwargs={'username': self.admin_user.username}),
            {
                'target_table': 'carsome',
                'sources': 'carsome',
                'batch_size': 500,
                'preview_token': 'token',
                'confirm': 'on',
            },
        )

        self.assertEqual(response.status_code, 302)
        validate_token.assert_called_once_with('token', 'carsome', ['carsome'], 500, self.admin_user.id)
        apply_async.assert_called_once()
        execute_insert.assert_not_called()
        execute_fill.assert_not_called()
        job = CarsStandardMaintenanceJob.objects.get(job_type=CarsStandardMaintenanceJob.JOB_FILL_STANDARD_ID)
        self.assertFalse(job.dry_run)
        self.assertEqual(job.parameters['preview_token'], 'token')
        self.assertEqual(job.celery_task_id, 'task-3')

    @patch('dashboard.tasks.execute_fill_standard_id')
    @patch('dashboard.tasks.fill_standard_id.apply_async')
    @patch('dashboard.forms.validate_sources')
    def test_fill_again_defaults_to_dry_run(self, validate_sources, apply_async, execute_fill):
        validate_sources.return_value = ['carlistmy']
        apply_async.return_value = SimpleNamespace(id='task-again')
        self.client.force_login(self.admin_user)

        response = self.client.post(
            reverse('admin_cars_standard_fill_again', kwargs={'username': self.admin_user.username}),
            {'target_table': 'cars_unified', 'sources': 'carlistmy', 'batch_size': 500, 'dry_run': 'on'},
        )

        self.assertEqual(response.status_code, 302)
        apply_async.assert_called_once()
        execute_fill.assert_not_called()
        job = CarsStandardMaintenanceJob.objects.get(job_type=CarsStandardMaintenanceJob.JOB_FILL_STANDARD_ID)
        self.assertTrue(job.dry_run)
        self.assertEqual(job.target_table, 'cars_unified')
        self.assertEqual(job.sources, ['carlistmy'])
        self.assertEqual(job.parameters['preview_token'], '')

    @patch('dashboard.views.build_fill_preview_token')
    @patch('dashboard.tasks.execute_fill_standard_id')
    @patch('dashboard.tasks.fill_standard_id.apply_async')
    @patch('dashboard.forms.validate_sources')
    def test_fill_again_real_update_requires_confirmation(self, validate_sources, apply_async, execute_fill, build_token):
        validate_sources.return_value = ['carlistmy']
        apply_async.return_value = SimpleNamespace(id='task-real')
        build_token.return_value = 'fill-token'
        self.client.force_login(self.admin_user)

        response = self.client.post(
            reverse('admin_cars_standard_fill_again', kwargs={'username': self.admin_user.username}),
            {'target_table': 'cars_unified', 'sources': 'carlistmy', 'batch_size': 500},
        )

        self.assertEqual(response.status_code, 302)
        apply_async.assert_not_called()
        self.assertFalse(CarsStandardMaintenanceJob.objects.exists())

        response = self.client.post(
            reverse('admin_cars_standard_fill_again', kwargs={'username': self.admin_user.username}),
            {'target_table': 'cars_unified', 'sources': 'carlistmy', 'batch_size': 500, 'confirm': 'on'},
        )

        self.assertEqual(response.status_code, 302)
        build_token.assert_called_once_with('cars_unified', ['carlistmy'], 500, self.admin_user.id)
        apply_async.assert_called_once()
        execute_fill.assert_not_called()
        job = CarsStandardMaintenanceJob.objects.get(job_type=CarsStandardMaintenanceJob.JOB_FILL_STANDARD_ID)
        self.assertFalse(job.dry_run)
        self.assertEqual(job.parameters['preview_token'], 'fill-token')

    @patch('dashboard.tasks.insert_missing_cars_standard.apply_async')
    @patch('dashboard.forms.validate_sources')
    def test_background_job_start_denies_non_dry_run_without_queueing_job(self, validate_sources, apply_async):
        validate_sources.return_value = ['carlistmy']
        self.client.force_login(self.admin_user)

        response = self.client.post(
            reverse('admin_cars_standard_job_start', kwargs={'username': self.admin_user.username}),
            {
                'job_type': CarsStandardMaintenanceJob.JOB_INSERT_MISSING,
                'target_table': 'cars_unified',
                'sources': 'carlistmy',
                'batch_size': 500,
            },
        )

        self.assertEqual(response.status_code, 302)
        apply_async.assert_not_called()
        self.assertFalse(CarsStandardMaintenanceJob.objects.exists())


@override_settings(CHANNEL_LAYERS={'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'}})
class CarsStandardJobConsumerTests(TransactionTestCase):
    def setUp(self):
        self.admin_group = Group.objects.create(name='Admin')
        self.admin_user = User.objects.create_user(username='adminws', password='pass')
        self.admin_user.groups.add(self.admin_group)
        self.regular_user = User.objects.create_user(username='regularws', password='pass')

    def connect(self, user):
        async def runner():
            communicator = WebsocketCommunicator(CarsStandardJobConsumer.as_asgi(), '/ws/cars-standard/jobs/')
            communicator.scope['user'] = user
            connected, _ = await communicator.connect()
            message = await communicator.receive_json_from() if connected else None
            if connected:
                await communicator.disconnect()
            return connected, message
        return async_to_sync(runner)()

    def test_consumer_requires_admin_and_sends_recent_jobs(self):
        CarsStandardMaintenanceJob.objects.create(
            job_type=CarsStandardMaintenanceJob.JOB_FILL_STANDARD_ID,
            requested_by=self.admin_user,
        )

        self.assertFalse(self.connect(self.regular_user)[0])
        connected, message = self.connect(self.admin_user)

        self.assertTrue(connected)
        self.assertEqual(message['type'], 'initial')
        self.assertEqual(len(message['jobs']), 1)

    def test_consumer_sends_job_update_payload(self):
        async def runner():
            communicator = WebsocketCommunicator(CarsStandardJobConsumer.as_asgi(), '/ws/cars-standard/jobs/')
            communicator.scope['user'] = self.admin_user
            connected, _ = await communicator.connect()
            await communicator.receive_json_from()
            await communicator.receive_json_from()
            await get_channel_layer().group_send(
                service.CARS_STANDARD_JOBS_GROUP,
                {'type': 'cars_standard_job_update', 'job': {'id': 123}},
            )
            message = await communicator.receive_json_from()
            await communicator.disconnect()
            return connected, message

        connected, message = async_to_sync(runner)()

        self.assertTrue(connected)
        self.assertEqual(message, {'type': 'job_update', 'job': {'id': 123}})
