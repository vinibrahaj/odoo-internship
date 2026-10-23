import base64
from io import BytesIO

from PIL import Image

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged

from .test_security import TestSolvitaskSecurity


@tagged('post_install', '-at_install')
class TestServiceRequest(TestSolvitaskSecurity):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        stream = BytesIO()
        Image.new('RGB', (4, 4), 'white').save(stream, format='PNG')
        cls.photo = base64.b64encode(stream.getvalue())
        cls.service = cls.env['solvitask.service'].with_user(cls.manager).create({
            'name': 'Catalog test service', 'description': 'Catalog description', 'unit_price': 75,
        })

    def _values(self, **changes):
        values = {'request_kind': 'service', 'service_id': self.service.id,
                  'building_type': 'apartment', 'problem_photo': self.photo,
                  'service_address': 'Job location'}
        values.update(changes)
        return values

    def _model(self):
        return self.env['solvitask.service.request'].with_user(self.cuser)

    def test_catalog_autofill_and_draft_does_not_create_job(self):
        count = self.env['solvitask.job'].search_count([])
        request = self._model().create(self._values(name='Forged title', description='Forged text'))
        self.assertEqual(request.name, self.service.name)
        self.assertEqual(request.description, self.service.description)
        self.assertEqual(request.customer_id.id, self.customers[0].id)
        self.assertEqual(request.state, 'draft')
        self.assertFalse(request.job_id)
        request.action_save_draft()
        self.assertEqual(self.env['solvitask.job'].search_count([]), count)
        request.write({'service_address': 'Updated address'})
        self.assertEqual(request.service_address, 'Updated address')

    def test_catalog_onchange_and_other_manual_fields(self):
        form = self._model().new({'request_kind': 'service', 'service_id': self.service.id})
        form._onchange_service()
        self.assertEqual(form.name, self.service.name)
        self.assertEqual(form.description, self.service.description)
        form.request_kind = 'other'
        form._onchange_service()
        self.assertFalse(form.service_id)
        self.assertFalse(form.name)
        self.assertFalse(form.description)
        for changes in ({'name': ''}, {'description': '   '}):
            with self.assertRaises(ValidationError), self.cr.savepoint():
                self._model().create(self._values(request_kind='other', service_id=False,
                    **dict({'name': 'Custom title', 'description': 'Custom details'}, **changes)))
        request = self._model().create(self._values(request_kind='other', service_id=False,
                                                    name='Custom title', description='Custom details'))
        request.action_submit()
        self.assertTrue(request.job_id.is_custom)
        self.assertFalse(request.job_id.service_id)
        self.assertEqual(request.job_id.title, 'Custom title')

    def test_required_fields_apply_to_drafts(self):
        for field in ('problem_photo', 'building_type', 'service_address'):
            with self.assertRaises(ValidationError), self.cr.savepoint():
                self._model().create(self._values(**{field: False}))
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self._model().create(self._values(service_address='   '))

    def test_submit_copies_details_and_locks_both_customer_surfaces(self):
        request = self._model().create(self._values())
        request.action_submit()
        job = request.job_id
        self.assertEqual(request.state, 'submitted')
        self.assertTrue(request.submitted_at)
        self.assertEqual(job.customer_id.id, self.customers[0].id)
        self.assertEqual(job.title, self.service.name)
        self.assertEqual(job.description, self.service.description)
        self.assertEqual(job.service_id.id, self.service.id)
        self.assertEqual(job.building_type, 'apartment')
        self.assertEqual(job.service_address, 'Job location')
        self.assertTrue(job.problem_photo)
        self.assertEqual(job.stage_id, 'stage_new')
        self.assertEqual(job.initial_price, 75)
        self.assertFalse(job.plumber_ids)
        self.assertEqual(self.env['solvitask.job'].sudo().browse(job.id).intake_request_id.id, request.id)
        self.assertIn(request.id, self._model().search([]).ids)
        for values in ({'description': 'Changed'}, {'state': 'draft'}, {'job_id': False}):
            with self.assertRaises(UserError):
                request.write(values)
        with self.assertRaises(UserError):
            request.unlink()
        with self.assertRaises(AccessError):
            job.write({'description': 'Bypass locked request'})
        job.with_user(self.manager).write({'priority': 'high'})
        count = self.env['solvitask.job'].sudo().search_count([('intake_request_id', '=', request.id)])
        with self.assertRaises(UserError):
            request.action_submit()
        self.assertEqual(count, 1)
        self.assertEqual(self.env['solvitask.job'].sudo().search_count([('intake_request_id', '=', request.id)]), 1)

    def test_ownership_state_and_link_cannot_be_forged(self):
        for values in ({'state': 'submitted'}, {'job_id': self.job.id},
                       {'customer_id': self.customers[1].id}):
            with self.assertRaises(AccessError):
                self._model().create(self._values(**values))
        request = self._model().create(self._values())
        with self.assertRaises(AccessError):
            request.write({'state': 'submitted'})
        for user in (self.customers[1].user_id, self.puser):
            with self.assertRaises(AccessError):
                request.with_user(user).read(['description'])
            with self.assertRaises(AccessError):
                request.with_user(user).action_submit()
        with self.assertRaises(AccessError):
            self.env['solvitask.job'].with_user(self.cuser).create({
                'customer_id': self.customers[0].id, 'is_custom': True, 'description': 'Bypass intake'})

    def test_submission_failure_keeps_draft_without_orphan_job(self):
        # An error during job creation must roll back the entire submission.
        from unittest.mock import patch
        request = self._model().create(self._values())
        count = self.env['solvitask.job'].sudo().search_count([])
        job_class = type(self.env['solvitask.job'])
        with patch.object(job_class, 'create', side_effect=ValidationError('Job creation failed')):
            with self.assertRaises(ValidationError), self.cr.savepoint():
                request.action_submit()
        request.invalidate_recordset()
        self.assertEqual(request.state, 'draft')
        self.assertFalse(request.job_id)
        self.assertEqual(self.env['solvitask.job'].sudo().search_count([]), count)
