from odoo.tests import TransactionCase, tagged
from odoo.exceptions import AccessError, ValidationError


@tagged('post_install', '-at_install')
class TestSolvitaskSecurity(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.manager = cls.env['res.users'].create({
            'name': 'Manager', 'login': 'mvp_manager',
            'groups_id': [(6, 0, [cls.env.ref('base.group_user').id,
                                  cls.env.ref('solvitask.group_solvitask_manager').id])],
        })
        cls.customers = cls.env['solvitask.customer']
        cls.plumbers = cls.env['solvitask.plumber']
        for index in range(3):
            cls.customers |= cls.env['solvitask.customer'].with_user(cls.manager).create({
                'name': 'Customer %s' % index, 'surname': 'Test', 'phone': '123',
                'email': 'customer%s@mvp.invalid' % index, 'address': 'Customer address',
            })
            cls.plumbers |= cls.env['solvitask.plumber'].with_user(cls.manager).create({
                'name': 'Plumber %s' % index, 'phone': '456', 'address': 'Private address',
                'email': 'plumber%s@mvp.invalid' % index, 'hourly_rate': 50,
            })
        cls.cuser = cls.customers[0].user_id
        cls.puser = cls.plumbers[0].user_id
        cls.job = cls.env['solvitask.job'].with_user(cls.manager).create({
            'customer_id': cls.customers[0].id, 'is_custom': True,
            'description': 'Shared job', 'initial_price': 100,
            'plumber_ids': [(6, 0, cls.plumbers[:2].ids)],
        })
        cls.other = cls.env['solvitask.job'].with_user(cls.manager).create({
            'customer_id': cls.customers[1].id, 'is_custom': True,
            'description': 'Unrelated job', 'initial_price': 100,
            'plumber_ids': [(6, 0, cls.plumbers[2].ids)],
        })

    def test_internal_accounts_and_minimal_groups(self):
        for user in self.customers.mapped('user_id') | self.plumbers.mapped('user_id'):
            self.assertTrue(user.has_group('base.group_user'))
            self.assertFalse(user.has_group('base.group_portal'))
            self.assertFalse(user.has_group('base.group_system'))

    def test_customer_isolation_and_rpc(self):
        jobs = self.env['solvitask.job'].with_user(self.cuser)
        self.assertEqual(jobs.search([]), self.job.with_user(self.cuser))
        with self.assertRaises(AccessError):
            self.other.with_user(self.cuser).read(['description'])
        self.assertEqual(self.env['solvitask.customer'].with_user(self.cuser).search([]).ids,
                         self.customers[:1].ids)
        with self.assertRaises(AccessError):
            jobs.create({'customer_id': self.customers[1].id, 'is_custom': True, 'description': 'Forged'})
        for vals in ({'plumber_ids': [(5, 0, 0)]}, {'initial_price': 1}, {'stage_id': 'stage_canceled'}):
            with self.assertRaises(AccessError):
                self.job.with_user(self.cuser).write(vals)

    def test_shared_plumbers_contacts_only(self):
        plumbers = self.env['solvitask.plumber'].with_user(self.puser)
        self.assertEqual(set(plumbers.search([]).ids), set(self.plumbers[:2].ids))
        self.plumbers[1].with_user(self.puser).read(['name', 'surname', 'phone', 'email'])
        for user in (self.puser, self.cuser):
            for field in ('balance', 'iban', 'address', 'payment_method', 'hourly_rate',
                          'job_ids', 'request_ids', 'slot_ids', 'service_ids', 'user_id'):
                self.assertNotIn(field, self.env['solvitask.plumber'].with_user(user).fields_get())
                with self.assertRaises(AccessError):
                    self.plumbers[1].with_user(user).read([field])
        with self.assertRaises(AccessError):
            self.plumbers[2].with_user(self.puser).read(['phone'])
        self.job.with_user(self.puser).write({'work_notes': 'Done', 'hours_worked': 2})
        with self.assertRaises(AccessError):
            self.job.with_user(self.puser).write({'customer_id': self.customers[1].id})
        # Assignment changes revoke contact access immediately.
        self.job.with_user(self.manager).write({'plumber_ids': [(6, 0, self.plumbers[:1].ids)]})
        self.assertNotIn(self.plumbers[1].id, plumbers.search([]).ids)

    def test_requests_cannot_be_forged_or_self_approved(self):
        requests = self.env['solvitask.requests'].with_user(self.cuser)
        values = {'name': 'Change', 'description': 'Please reschedule', 'job_id': self.job.id}
        for extra in ({'requester_id': self.puser.id}, {'state': 'approved'}, {'job_id': self.other.id}):
            with self.assertRaises(AccessError):
                requests.create(dict(values, **extra))
        req = requests.create(values)
        req.action_submit()
        with self.assertRaises(AccessError):
            req.action_approve()
        with self.assertRaises(AccessError):
            req.write({'state': 'approved'})
        self.assertNotIn(req.id, self.env['solvitask.requests'].with_user(self.puser).search([]).ids)
        req.with_user(self.manager).action_approve()
        self.assertEqual(req.state, 'approved')

    def test_core_directory_does_not_bypass_custom_rules(self):
        for user in (self.cuser, self.puser):
            self.assertNotIn(self.customers[1].user_id.partner_id.id,
                             self.env['res.partner'].with_user(user).search([]).ids)
            with self.assertRaises(AccessError):
                self.customers[1].user_id.with_user(user).read(['login'])
            with self.assertRaises(AccessError):
                self.job.with_user(user).action_generate_invoice()

    def test_roles_cannot_be_combined(self):
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.cuser.write({'groups_id': [(4, self.env.ref('solvitask.group_solvitask_manager').id)]})
