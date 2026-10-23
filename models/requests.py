from odoo import fields, models, api
from odoo.exceptions import AccessError, ValidationError, UserError


REQUEST_TRANSITIONS = {
    'draft':     {'submitted'},
    'submitted': {'approved', 'rejected'},
    'approved':  set(),
    'rejected':  set(),
}

# The only fields a manager may touch once a request is submitted.
MANAGER_FIELDS = {'state', 'manager_note', 'decision_date'}

class SolvitaskRequests(models.Model):
    _name = 'solvitask.requests'
    _description = 'Request from a customer or plumber to the manager'
    _order = 'create_date desc, id desc'

    name = fields.Char(string='Title', required=True)
    description = fields.Text(string='Description', required=True)

    requester_id = fields.Many2one(
        'res.users', string='Requested By',
        default=lambda self: self.env.user,
        required=True, readonly=True
    )
    request_type = fields.Selection(
        string='Type',
        selection=[
            ('time', 'Time / reschedule adjustment'),
            ('custom', 'Diagnose as custom job'),
            ('materials', 'Extra materials needed'),
            ('scope_price', 'Scope / price adjustment'),
            ('cancel', 'Cancellation request'),
            ('other', 'Other'),
        ],
        default='other',
        required=True,
    )

    job_id = fields.Many2one('solvitask.job', string='Job',
                             required=True, ondelete='cascade')

    # --- who raised it ---
    source = fields.Selection(
        string='From',
        selection=[('customer', 'Customer'),('plumber', 'Plumber')],
        compute='_compute_party', store=True, readonly=True
    )
    customer_id = fields.Many2one(
        comodel_name='solvitask.customer', string='Customer',
        compute='_compute_party', store=True, readonly=True)
    plumber_id = fields.Many2one(
        comodel_name='solvitask.plumber', string='Plumber',
        compute='_compute_party', store=True, readonly=True)

    # --- workflow ---
    state = fields.Selection(
        string='Status',
        selection=[
            ('draft', 'New'),
            ('submitted', 'Submitted'),
            ('approved', 'Approved'),
            ('rejected', 'Rejected'),
        ],
        default='draft',
        required=True,
    )
    manager_note = fields.Text(
        string='Manager Note',
        help='What the manager decided or changed on the job.')
    decision_date = fields.Datetime(string='Decision Date', readonly=True,
                                    copy=False)

    @api.depends('requester_id')
    def _compute_party(self):
        for req in self:
            plumber = self.env['solvitask.plumber'].sudo().search(
                [('user_id', '=', req.requester_id.id)], limit=1)
            customer = self.env['solvitask.customer'].sudo().search(
                [('user_id', '=', req.requester_id.id)], limit=1)
            req.plumber_id = plumber
            req.customer_id = customer
            req.source = ('plumber' if plumber else 'customer' if customer else False)

    def _check_job_access(self, job_id):
        job = self.env['solvitask.job'].browse(job_id).exists()
        if not job:
            raise ValidationError('Choose an existing job.')
        job.check_access_rights('read')
        job.check_access_rule('read')

    @api.model_create_multi
    def create(self, vals_list):
        self.check_access_rights('create')
        cleaned = []
        for values in vals_list:
            values = dict(values)
            if set(values) - {'name', 'description', 'request_type', 'job_id', 'requester_id', 'state'}:
                raise AccessError('Decisions and requester details cannot be supplied when creating requests.')
            if values.get('requester_id', self.env.uid) != self.env.uid:
                raise AccessError('You cannot impersonate another requester.')
            if values.get('state', 'draft') != 'draft':
                raise AccessError('New requests must start in New.')
            self._check_job_access(values.get('job_id'))
            values.update(requester_id=self.env.uid, state='draft')
            cleaned.append(values)
        # A caller must not inject protected values through default_* context keys.
        context = {k: v for k, v in self.env.context.items() if not k.startswith('default_')}
        return super(SolvitaskRequests, self.with_context(context)).create(cleaned)

    def write(self, vals):
        self.check_access_rights('write')
        self.check_access_rule('write')
        is_manager = self.env.su or self.env.user.has_group('solvitask.group_solvitask_manager')
        if 'job_id' in vals:
            self._check_job_access(vals['job_id'])
        allowed = {'name', 'description', 'request_type', 'job_id', 'state'}
        if not is_manager and (set(vals) - allowed or vals.get('state', 'submitted') not in ('draft', 'submitted')):
            raise AccessError('Only managers can record decisions.')
        if set(vals) & {'requester_id', 'source', 'customer_id', 'plumber_id'}:
            raise AccessError('The requester cannot be changed.')
        for req in self:
            new_state = vals.get('state', req.state)
            if new_state != req.state and \
                    new_state not in REQUEST_TRANSITIONS[req.state]:
                raise UserError(
                    "A request in '%s' cannot go back to '%s'."
                    % (req.state, new_state))
            if req.state != 'draft':
                if not is_manager:
                    raise UserError(
                        "Once submitted, only the manager can act on this "
                        "request.")
                forbidden = set(vals) - MANAGER_FIELDS
                if forbidden:
                    raise UserError(
                        "The title and description belong to whoever raised "
                        "the request. You can only record a decision.")
        return super().write(vals)

    def unlink(self):
        for req in self:
            if req.state != 'draft':
                raise UserError(
                    "Only a request still in New can be deleted.")
            if req.requester_id != self.env.user:
                raise UserError("You can only delete your own requests.")
        return super().unlink()

    def action_submit(self):
        self.write({'state': 'submitted'})

    def action_approve(self):
        if not (self.env.su or self.env.user.has_group('solvitask.group_solvitask_manager')):
            raise AccessError('Only managers can decide requests.')
        for req in self:
            req.state = 'approved'
            req.decision_date = fields.Datetime.now()
            req.job_id.last_request_update = req.decision_date

    def action_reject(self):
        if not (self.env.su or self.env.user.has_group('solvitask.group_solvitask_manager')):
            raise AccessError('Only managers can decide requests.')
        for req in self:
            req.state = 'rejected'
            req.decision_date = fields.Datetime.now()
