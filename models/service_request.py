from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from .constants import BUILDING_TYPES


class SolvitaskServiceRequest(models.Model):
    _name = 'solvitask.service.request'
    _description = 'Customer Service Request'
    _order = 'create_date desc, id desc'

    name = fields.Char(string='Title', required=True)
    description = fields.Text(required=True)
    request_kind = fields.Selection(
        [('service', 'Choose a service'), ('other', 'Other')],
        string='Request for', required=True, default='service')
    service_id = fields.Many2one('solvitask.service', string='Service', ondelete='restrict')
    customer_id = fields.Many2one(
        'solvitask.customer', required=True, ondelete='restrict',
        default=lambda self: self._default_customer())
    problem_photo = fields.Image(string='Image', required=True, attachment=False)
    building_type = fields.Selection(BUILDING_TYPES, required=True)
    service_address = fields.Char(string='Job Address', required=True)
    state = fields.Selection(
        [('draft', 'Draft'), ('submitted', 'Submitted')],
        default='draft', required=True, readonly=True, copy=False)
    submitted_at = fields.Datetime(readonly=True, copy=False)
    job_id = fields.Many2one('solvitask.job', string='Created Job', readonly=True,
                             copy=False, ondelete='restrict')

    def _is_manager(self):
        return self.env.su or self.env.user.has_group('solvitask.group_solvitask_manager')

    @api.model
    def _default_customer(self):
        customer = self.env['solvitask.customer'].sudo().search(
            [('user_id', '=', self.env.uid)],
            limit=1,
        )
        return customer.with_env(self.env)

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        if 'service_address' in fields_list and not values.get('service_address'):
            customer = self._default_customer()
            if customer:
                values['service_address'] = customer.address
        return values

    @api.onchange('request_kind', 'service_id')
    def _onchange_service(self):
        if self.request_kind == 'service':
            self.name = self.service_id.name or False
            self.description = (self.service_id.description or self.service_id.name) or False
        else:
            self.service_id = False
            # A custom request starts with its own text, not stale catalog text.
            self.name = False
            self.description = False

    @api.onchange('customer_id')
    def _onchange_customer(self):
        if self.customer_id:
            self.service_address = self.customer_id.address

    def _prepare_draft_values(self, values, current=None):
        """Apply identical catalog/ownership rules for UI, imports and RPC."""
        allowed = {'name', 'description', 'request_kind', 'service_id', 'customer_id',
                   'problem_photo', 'building_type', 'service_address'}
        if set(values) - allowed:
            raise AccessError('Status and the created job are controlled by Submit.')
        values = dict(values)
        if not self._is_manager():
            customer = self._default_customer()
            if not customer or values.get('customer_id', customer.id) != customer.id:
                raise AccessError('You can only create or edit your own service requests.')
            values['customer_id'] = customer.id
        kind = values.get('request_kind', current.request_kind if current else 'service')
        service_id = values.get('service_id', current.service_id.id if current else False)
        if kind == 'service':
            service = self.env['solvitask.service'].browse(service_id).exists()
            if not service:
                raise ValidationError('Choose a service, or select Other.')
            service.check_access_rights('read')
            service.check_access_rule('read')
            # Refresh snapshot only when selection changes, not on unrelated edits.
            if current is None or {'service_id', 'request_kind', 'name', 'description'} & values.keys():
                values.update(name=service.name, description=service.description or service.name)
        elif kind == 'other':
            values['service_id'] = False
            if current and current.request_kind != 'other':
                values.setdefault('name', False)
                values.setdefault('description', False)
        else:
            raise ValidationError('Choose a service, or select Other.')
        return values

    @api.model_create_multi
    def create(self, vals_list):
        self.check_access_rights('create')
        cleaned = [self._prepare_draft_values(values) for values in vals_list]
        context = {k: v for k, v in self.env.context.items() if not k.startswith('default_')}
        return super(SolvitaskServiceRequest, self.with_context(context)).create(cleaned)

    def _lock_drafts(self):
        """Serialize submit/edit/delete so an old draft cannot overwrite a submission."""
        self.check_access_rights('write')
        self.check_access_rule('write')
        if self.ids:
            self.env.cr.execute(
                'SELECT id FROM solvitask_service_request WHERE id IN %s ORDER BY id FOR UPDATE',
                [tuple(self.ids)])
            self.invalidate_recordset()
        if any(request.state != 'draft' for request in self):
            raise UserError('Submitted service requests are locked and cannot be changed.')

    def write(self, values):
        self._lock_drafts()
        for request in self:
            prepared = self._prepare_draft_values(values, current=request)
            super(SolvitaskServiceRequest, request).write(prepared)
        return True

    def unlink(self):
        self.check_access_rights('unlink')
        self.check_access_rule('unlink')
        self._lock_drafts()
        return super().unlink()

    @api.constrains('name', 'description', 'request_kind', 'service_id',
                    'problem_photo', 'building_type', 'service_address')
    def _check_required_details(self):
        for request in self:
            if (not (request.name or '').strip() or not (request.description or '').strip()
                    or not request.problem_photo or not request.building_type
                    or not (request.service_address or '').strip()):
                raise ValidationError('Title, description, image, building type and job address are required, including for drafts.')
            if request.request_kind == 'service' and not request.service_id:
                raise ValidationError('Choose a service, or select Other.')
            if request.request_kind == 'other' and request.service_id:
                raise ValidationError('Other requests cannot reference a catalog service.')

    def action_save_draft(self):
        self.ensure_one()
        self._lock_drafts()
        self._check_required_details()
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_submit(self):
        self.ensure_one()
        self._lock_drafts()
        self._check_required_details()
        # Fixed allowlist, after ownership and state checks. Customers have no job
        # create/write ACL; only this transition provisions their job with sudo.
        job_values = {
            'intake_request_id': self.id,
            'customer_id': self.customer_id.id,
            'title': self.name,
            'description': self.description,
            'service_id': self.service_id.id,
            'is_custom': self.request_kind == 'other',
            'problem_photo': self.with_context(bin_size=False).problem_photo,
            'building_type': self.building_type,
            'service_address': self.service_address,
        }
        context = {k: v for k, v in self.env.context.items() if not k.startswith('default_')}
        job = self.env['solvitask.job'].sudo().with_context(context).create(job_values)
        # Bypass this model's immutable public write only for the fixed transition.
        super(SolvitaskServiceRequest, self).write({
            'state': 'submitted', 'submitted_at': fields.Datetime.now(), 'job_id': job.id})
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_view_job(self):
        self.ensure_one()
        self.check_access_rights('read')
        self.check_access_rule('read')
        if not self.job_id:
            raise UserError('Submit this request first to create a job.')
        self.job_id.check_access_rights('read')
        self.job_id.check_access_rule('read')
        return {'type': 'ir.actions.act_window', 'name': 'Job',
                'res_model': 'solvitask.job', 'view_mode': 'form',
                'res_id': self.job_id.id, 'target': 'current'}
