from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.contrib.auth.models import Group, User
from django.core.paginator import Paginator
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from .models import CarsStandardMaintenanceJob
from .services import cars_standard_maintenance as service


class CarsStandardServiceValidationTests(SimpleTestCase):
    def test_validate_target_table_allows_only_known_tables(self):
        self.assertIs(service.validate_target_table('cars_unified'), service.ALLOWED_TARGET_TABLES['cars_unified'])
        self.assertIs(service.validate_target_table('carsome'), service.ALLOWED_TARGET_TABLES['carsome'])
        self.assertIs(service.validate_target_table('cars_unified_ind'), service.ALLOWED_TARGET_TABLES['cars_unified_ind'])

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
        reference_counts.return_value = {'cars_unified': 3, 'carsome': 1, 'cars_unified_ind': 0}
        fk_rules.return_value = {'cars_unified': 'SET NULL', 'carsome': 'NO ACTION', 'cars_unified_ind': 'UNKNOWN'}

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
            {'cars_unified': 2, 'carsome': 1, 'cars_unified_ind': 0},
            {'cars_unified': 0, 'carsome': 0, 'cars_unified_ind': 0},
            {'cars_unified': 5, 'carsome': 1, 'cars_unified_ind': 0},
        ]
        fk_rules.return_value = {'cars_unified': 'SET NULL', 'carsome': 'NO ACTION', 'cars_unified_ind': 'SET NULL'}
        manual_null.return_value = {'carsome': 1}
        null_counts.return_value = {'cars_unified': 10, 'carsome': 4, 'cars_unified_ind': 0}

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
            ('post', reverse('admin_cars_standard_update', kwargs={'username': self.regular_user.username}), {}),
            ('post', reverse('admin_cars_standard_merge_preview', kwargs={'username': self.regular_user.username}), {}),
            ('post', reverse('admin_cars_standard_merge_execute', kwargs={'username': self.regular_user.username}), {}),
            ('post', reverse('admin_cars_standard_insert_missing_preview', kwargs={'username': self.regular_user.username}), {}),
            ('post', reverse('admin_cars_standard_insert_missing_execute', kwargs={'username': self.regular_user.username}), {}),
            ('post', reverse('admin_cars_standard_fill_preview', kwargs={'username': self.regular_user.username}), {}),
            ('post', reverse('admin_cars_standard_fill_execute', kwargs={'username': self.regular_user.username}), {}),
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
