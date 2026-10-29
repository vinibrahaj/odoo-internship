import base64

from odoo import fields, models, api
from odoo.exceptions import AccessError, ValidationError, UserError

from .constants import BUILDING_TYPES


STAGE_SELECTION = [
    ('stage_new', 'New Jobs'),
    ('stage_in_progress', 'In Progress'),
    ('stage_ready_invoice', 'Ready to Invoice'),
    ('stage_invoiced', 'Invoiced'),
    ('stage_paid', 'Paid & Closed'),
    ('stage_canceled', 'Canceled')
]

# Which stages a job may move to, keyed by where it is now.
# Empty set = terminal.
ALLOWED_TRANSITIONS = {
    'stage_new':            {'stage_in_progress', 'stage_canceled'},
    'stage_in_progress':    {'stage_ready_invoice', 'stage_canceled'},
    'stage_ready_invoice':  {'stage_invoiced', 'stage_canceled'},
    'stage_invoiced':       {'stage_paid', 'stage_canceled'},
    'stage_paid':           set(),
    'stage_canceled':       set(),
}

STAGE_LABELS = dict(STAGE_SELECTION)
# this is a safety check whenever we may add a new stage
assert set(ALLOWED_TRANSITIONS) == set(STAGE_LABELS), \
    "ALLOWED_TRANSITIONS is out of sync with STAGE_SELECTION"

# Single stages referenced by the action buttons and the cron.
STARTED_STAGE = 'stage_in_progress'
CANCELED_STAGE = 'stage_canceled'

# Groups used by _compute_stage_flags to show/hide buttons in the form.
STARTED_STAGES = {'stage_in_progress', 'stage_ready_invoice',
                  'stage_invoiced', 'stage_paid'}

class SolvitaskJob(models.Model):
    _name = 'solvitask.job'
    _description = 'Service Request / Job'
    _order = 'priority desc, started_date desc, id desc'

    name = fields.Char(string='Reference', compute='_compute_name', store=True)
    title = fields.Char(string='Request Title')
    building_type = fields.Selection(BUILDING_TYPES, string='Building Type')
    intake_request_id = fields.Many2one(
        'solvitask.service.request', string='Customer Service Request',
        readonly=True, copy=False, ondelete='restrict', index=True,
        groups='solvitask.group_solvitask_manager,solvitask.group_solvitask_customer')
    _sql_constraints = [
        ('unique_intake_request', 'unique(intake_request_id)',
         'A submitted service request can create only one job.'),
    ]
    job_source = fields.Selection([
        ('app', 'Customer Service Request'),
        ('instagram', 'Instagram'),
        ('whatsapp', 'Whatsapp'),
        ('phone', 'Phone Call'),
        ('email', 'Email'),
        ('other', 'Other')
    ], string='Job Source', required=True)
    source_details = fields.Text(
        string='Source Details'
    )

    customer_id = fields.Many2one(
        comodel_name='solvitask.customer',
        string='Customer',
        required=True
    )
    plumber_ids = fields.Many2many(
        comodel_name='solvitask.plumber',
        relation='solvitask_job_plumber_relation',
        column1='solvitask_job_id', column2='solvitask_plumber_id',
        string='Assigned Plumber'
    )
    # this is what customers see:
    customer_plumber_ids = fields.Many2many(
        comodel_name='solvitask.plumber',
        string='Working on this job',
        compute='_compute_customer_plumber_ids',
    )
    
    service_id = fields.Many2one(
        comodel_name='solvitask.service',
        string='Service'
    )
    is_custom = fields.Boolean(string='Custom Request')
    description = fields.Text(
        string='Problem Description',
        required=True
    )
    problem_photo = fields.Image(string='Problem Photo')
    service_address = fields.Char(string='Service Address')
    
    priority = fields.Selection(
        string='Priority',
        selection=[('low', 'Low'),
                   ('normal', 'Normal'),
                   ('high', 'High'),
                   ('emergency', 'Emergency')],
        default='normal',
    )

    started_date = fields.Datetime(
        string='Started Date:',
        readonly=True
    )
    finished_date = fields.Datetime(
        string='Finished Date:',
        readonly=True
    )
    tool_ids = fields.Many2many('solvitask.tool', string='Required Tools')

    # --- work done ---
    material_line_ids = fields.One2many(
        comodel_name='solvitask.job.material',
        inverse_name='job_id',
        string='Materials Used'
    )
    work_notes = fields.Text(string='Work Notes', groups='solvitask.group_solvitask_manager')
    hours_worked = fields.Float(string='Hours Worked')

    # --- pipeline stage: this is what the kanban board drags between ---
    stage_id = fields.Selection(
        selection=STAGE_SELECTION,
        string='Stage',
        default='stage_new',
        required=True,
        group_expand='_expand_stages'
    )

    # --- requests raised against this job (by a customer or a plumber) ---
    request_ids = fields.One2many(
        comodel_name='solvitask.requests',
        inverse_name='job_id',
        string='Requests'
    )
    request_count = fields.Integer(
        string='Request Count', compute='_compute_request_count')
    last_request_update = fields.Datetime(
        string='Last Request Approved', readonly=True, copy=False,
        help='Stamped when the manager approves a request tied to this job.')


    # --- money ---
    initial_price = fields.Float(
        string='Initial Price', compute='_compute_initial_price',
        store=True, readonly=False, digits=(12, 2),
        help='Quoted starting price. Prefilled from the service, still editable.')
    labor_cost = fields.Float(string='Labor Cost',
                              compute='_compute_costs', store=True, digits=(12, 2))
    material_cost = fields.Float(string='Material Cost',
                                 compute='_compute_costs', store=True, digits=(12, 2))
    total_price = fields.Float(string='Total Price',
                               compute='_compute_costs', store=True, digits=(12, 2))


    @api.model
    def _expand_stages(self, states, domain, *args):
        return [key for key, _label in STAGE_SELECTION]

    @api.depends('request_ids')
    def _compute_request_count(self):
        for job in self:
            job.request_count = len(job.request_ids)

    @api.depends('plumber_ids', 'stage_id')
    def _compute_customer_plumber_ids(self):
        for job in self:
            job.customer_plumber_ids = job.plumber_ids

    def action_view_requests(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Requests',
            'res_model': 'solvitask.requests',
            'view_mode': 'tree,form',
            'domain': [('job_id', '=', self.id)],
            'context': {
                'default_job_id': self.id,
                'default_source': 'customer',
                'default_customer_id': self.customer_id.id,
            },
        }

    # ---- computes th name of the job ----
    @api.depends('title', 'service_id.name', 'customer_id.name')
    def _compute_name(self):
        for job in self:
            service = job.title or job.service_id.name or 'Custom'
            customer = job.customer_id.name or ''
            job.name = f'{service} - {customer}'.strip(' -')

    @api.depends('service_id')
    def _compute_initial_price(self):
        for job in self:
            job.initial_price = job.service_id.unit_price

    @api.depends('hours_worked', 'plumber_ids.hourly_rate',
                 'material_line_ids.subtotal', 'initial_price', 'is_custom')
    def _compute_costs(self):
        for job in self:
            # Listed services are charged at the catalog price, so no hourly
            # labor. Only a custom job bills time.
            if job.is_custom:
                job.labor_cost = sum(
                    plumber.hourly_rate * job.hours_worked
                    for plumber in job.plumber_ids
                )
            else:
                job.labor_cost = 0.0
            job.material_cost = sum(job.material_line_ids.mapped('subtotal'))
            job.total_price = job.initial_price + job.labor_cost + job.material_cost

    def _is_manager(self):
        return self.env.su or self.env.user.has_group('solvitask.group_solvitask_manager')

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        if not self._is_manager() and self.env.user.has_group('solvitask.group_solvitask_customer'):
            customer = self.env['solvitask.customer'].search([('user_id', '=', self.env.uid)], limit=1)
            if 'customer_id' in fields_list:
                values['customer_id'] = customer.id
        return values

    @api.model_create_multi
    def create(self, vals_list):
        self.check_access_rights('create')
        if not self._is_manager():
            raise AccessError('Create a Service Request and submit it to create a job.')
        for vals in vals_list:
            stage = vals.get('stage_id')
            if stage and stage != 'stage_new':
                raise UserError(
                    "A new job must be created in '%s'. Move it along the "
                    "pipeline afterwards." % STAGE_LABELS['stage_new'])
            vals['stage_id'] = 'stage_new'
        # A caller must not inject protected values through default_* context keys.
        context = {k: v for k, v in self.env.context.items() if not k.startswith('default_')}
        return super(SolvitaskJob, self.with_context(context)).create(vals_list)

    # stage movement logic
    def write(self, vals):
        if 'intake_request_id' in vals:
            raise AccessError('The original customer request cannot be changed.')
        if not self._is_manager():
            self.check_access_rights('write')
            self.check_access_rule('write')
            if self.env.user.has_group('solvitask.group_solvitask_customer'):
                raise AccessError('Submitted job details are locked. Submit a change request instead.')
            allowed = {'work_notes', 'hours_worked'}
            if set(vals) - allowed:
                raise AccessError('Use a change request; assignments, pricing and stages are manager controlled.')
        if 'stage_id' in vals:
            new_stage = vals['stage_id']
            for job in self:
                old_stage = job.stage_id
                if not old_stage or old_stage == new_stage:
                    continue
                if new_stage not in ALLOWED_TRANSITIONS.get(old_stage, set()):
                    raise UserError(
                        "A job in '%s' can't be moved to '%s'."
                        % (STAGE_LABELS.get(old_stage, old_stage),
                           STAGE_LABELS.get(new_stage, new_stage)))
                if new_stage == 'stage_in_progress':
                    if not job.started_date:
                        vals['started_date'] = fields.Datetime.now()

                if new_stage == 'stage_ready_invoice':
                    vals['finished_date'] = fields.Datetime.now()
        return super().write(vals)

    """ 
    ==== RULE 1 & 2 =========================================================
    - A job may not sit in a started stage without a plumber and a price.
    - Canceled jpbs are deliberately exempt -- you must be able to cancel a
    - half-filled job 
    """
    @api.constrains('stage_id', 'plumber_ids', 'total_price')
    def _check_started_requirements(self):
        for job in self:
            if job.stage_id in STARTED_STAGES:
                if not job.plumber_ids:                       # RULE 1
                    raise ValidationError(
                        "Assign a Plumber before starting this job.")
                if job.total_price <= 0:                    # RULE 2
                    raise ValidationError(
                        "Set an initial price before starting this job "
                        "(the total is currently 0).")

    @api.constrains('hours_worked')
    def _check_hours_worked(self):
        if any(job.hours_worked < 0 for job in self):
            raise ValidationError('Hours worked cannot be negative.')

    @api.onchange('is_custom')
    def _onchange_is_custom(self):
        if self.is_custom:
            self.service_id=False

    @api.constrains('is_custom', 'service_id')
    def _check_custom_or_service(self):
        for job in self:
            if job.is_custom and job.service_id:
                raise ValidationError(
                    "A custom request cannot also point to a listed service.")
            if not job.is_custom and not job.service_id:
                raise ValidationError(
                    "Choose a service, or tick 'Custom request' and describe "
                    "the problem.")

    @api.constrains('plumber_ids', 'started_date')
    def _check_plumber_availability(self):
        for job in self:
            if not job.started_date:
                continue

            unavailable = job.plumber_ids.filtered(
                lambda p: not p.is_available_at(job.started_date)
            )
            if unavailable:
                names = ", ".join(unavailable.mapped('name'))
                local = fields.Datetime.context_timestamp(
                    job, job.started_date
                )
                raise ValidationError(
                    f"Not available on {local:%A %d/%m at %H:%M}: {names}"
                )

    # --- buttons ---
    def action_mark_started(self):
        for job in self:
            vals = {'stage_id': 'stage_in_progress'}
            if not job.started_date:
                vals['started_date'] = fields.Datetime.now()
            job.write(vals)

    def action_cancel(self):
        for job in self:
            if job.stage_id in STARTED_STAGES:
                if not self.env.user.has_group('solvitask.group_solvitask_manager'):
                    raise ValidationError("This job has alredy started. Provide the reason and details to cancel it!")

                return {
                    'type': 'ir.actions.act_window',
                    'name': 'Cancel Job',
                    'res_model': 'solvitask.cancel.wizard',
                    'view_mode': 'form',
                    'target': 'new',
                    'context': {
                        'default_job_id': job.id,
                    },
                }
                    
            job.stage_id = CANCELED_STAGE

    # Generate invoice:
    def action_generate_invoice(self):
        self.ensure_one()
        if not self._is_manager():
            raise AccessError('Only managers can generate invoices.')
        self.check_access_rights('read')
        self.check_access_rule('read')
        # 1) render the QWeb report into raw PDF bytes
        pdf_content, _ = self.env['ir.actions.report']._render_qweb_pdf(
            'solvitask.report_job_invoice', self.ids)
        # 2) save those bytes as a PDF file attached to this job (kept on record)
        attachment = self.env['ir.attachment'].create({
            'name': 'Invoice - %s.pdf' % (self.name or self.id),
            'type': 'binary',
            'datas': base64.b64encode(pdf_content),   # bytes -> base64, the stored format
            'res_model': 'solvitask.job',
            'res_id': self.id,
            'mimetype': 'application/pdf',
        })
        # 3) hand that file to the browser as a download
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=true' % attachment.id,
            'target': 'new',
        }


class SolvitaskJobMaterial(models.Model):
    _name = 'solvitask.job.material'
    _description = 'Job Material Line'

    job_id = fields.Many2one('solvitask.job', string='Job',
                             required=True, ondelete='cascade')
    material_id = fields.Many2one('solvitask.material', string='Material',
                                  required=True)
    quantity = fields.Float(string='Quantity', default=1.0)
    unit_price = fields.Float(string='Unit Price',
                              compute='_compute_unit_price',
                              store=True, digits=(12, 2), readonly=False)
    @api.depends('material_id')
    def _compute_unit_price(self):
        for line in self:
            line.unit_price = line.material_id.unit_price

    subtotal = fields.Float(
        string='Subtotal',
        compute='_compute_subtotal', 
        store=True, 
        digits=(12, 2)
    )

    @api.depends('quantity', 'unit_price')  # me kete llogaritet ne cast pa u bere save
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.quantity * line.unit_price
