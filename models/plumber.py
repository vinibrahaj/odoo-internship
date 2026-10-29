from odoo import fields, models, api
from odoo.exceptions import ValidationError


WEEKDAYS = [
    ('0', 'Monday'), ('1', 'Tuesday'),
    ('2', 'Wednesday'), ('3', 'Thursday'),
    ('4', 'Friday'), ('5', 'Saturday'),
    ('6', 'Sunday'),
]
PLUMBER_HOURS = [
    (f'{h:02d}:{m:02d}', f'{h:02d}:{m:02d}')
    for h in range(24) for m in (0, 30)
]


class SolvitaskPlumber(models.Model):
    _name = 'solvitask.plumber'
    _description = 'Worker / Plumber'
    _inherit = ['solvitask.whatsapp.mixin']

    # visitble to everyone
    name = fields.Char(string='Name', required=True)
    surname = fields.Char(string='Surname')
    phone = fields.Char(string='Phone', required=True)
    email = fields.Char(string='Email')
    # invisible for customers

    address = fields.Char(
        string='Address',
        required=True,
        groups='solvitask.group_solvitask_manager'
    )
    balance = fields.Float(
        string="Balance",
        readonly=True,
        groups='solvitask.group_solvitask_manager'
    )

    hourly_rate = fields.Float(
        string='Hourly Rate', digits=(12, 2), groups='solvitask.group_solvitask_manager'
    )
    payment_method = fields.Selection(
        string='Payment Method',
        selection=[('cash', 'Cash'), ('bank', 'Bank Transfer')],
        groups='solvitask.group_solvitask_manager'
    )
    iban = fields.Char(
        string="IBAN",
        size=36,
        groups='solvitask.group_solvitask_manager'
    )

    user_id = fields.Many2one(
        comodel_name='res.users',
        string='Related User',
        readonly=True,
        ondelete='restrict',
        groups='solvitask.group_solvitask_manager',
        help='Odoo user belongs to this plumber'
    )
    # Many workers <-> many services. Creates a hidden link table automatically.
    service_ids = fields.Many2many(
        comodel_name='solvitask.service',
        string='Skills / Services', groups='solvitask.group_solvitask_manager')

    job_ids = fields.Many2many(
        'solvitask.job',
        relation='solvitask_job_plumber_relation',
        column1='solvitask_plumber_id', column2='solvitask_job_id',
        string='Assigned Jobs', groups='solvitask.group_solvitask_manager'
    )
    request_ids = fields.One2many(
        comodel_name='solvitask.requests',
        inverse_name='plumber_id',
        string="Requests", groups='solvitask.group_solvitask_manager'
    )
    slot_ids = fields.One2many(
        'solvitask.plumber.slot',
        'plumber_id',
        string='Weekly Availability', groups='solvitask.group_solvitask_manager',
        default=lambda self: [
            fields.Command.create({
                'day_of_week': str(day),
                'hour_from': '08:00',
                'hour_to': '16:00',
                'day_off': day >= 5,
            })
            for day in range(7)
        ],
    )

    def is_available_at(self, dt):
        self.ensure_one()

        local = fields.Datetime.context_timestamp(self, dt)
        day = str(local.weekday())
        time = f'{local.hour:02d}:{local.minute:02d}'

        slot = self.slot_ids.filtered(
            lambda s: s.day_of_week == day
        )

        if not slot or slot.day_off:
            return False

        return slot.hour_from <= time < slot.hour_to

    _sql_constraints = [('unique_user', 'unique(user_id)', 'A user can have only one plumber profile.')]

    @api.model_create_multi
    def create(self, vals_list):
        """Create the plumber, its Odoo user account, and weekly slots."""
        self.check_access_rights('create')
        user_model = self.env['res.users'].sudo()

        for vals in vals_list:
            email = vals.get('email')

            if not email:
                raise ValidationError(
                    'An email address is required to create a plumber.'
                )
            # Prevent duplicate Odoo accounts.
            existing_user = user_model.search(
                [('login', '=', email)],
                limit=1,
            )
            if existing_user:
                raise ValidationError(
                    f'An Odoo user with the email "{email}" already exists.'
                )

            user = user_model.create({
                'name': ' '.join(
                    filter(None, [
                        vals.get('name'),
                        vals.get('surname'),
                    ])
                ),
                'login': email,
                'email': email,
                'phone': vals.get('phone'),
                'groups_id': [
                    (6, 0, [self.env.ref('base.group_user').id, self.env.ref('solvitask.group_solvitask_plumber').id]),
                ],
            })
            vals['user_id'] = user.id

        plumbers = super().create(vals_list)
        return plumbers

class SolvitaskPlumberSlot(models.Model):
    _name = 'solvitask.plumber.slot'
    _description = 'Plumber Weekly Time Slot'
    _order = 'day_of_week'

    plumber_id = fields.Many2one(
        'solvitask.plumber',
        string='Plumber',
        required=True,
        ondelete='cascade',
    )

    day_of_week = fields.Selection(
        WEEKDAYS,
        string='Day',
        required=True,
    )

    day_off = fields.Boolean(string='Day Off')

    hour_from = fields.Selection(
        PLUMBER_HOURS,
        string='From',
        required=True,
        default='08:00',
    )

    hour_to = fields.Selection(
        PLUMBER_HOURS,
        string='To',
        required=True,
        default='16:00',
    )

    _sql_constraints = [
        (
            'uniq_plumber_day',
            'unique(plumber_id, day_of_week)',
            'Each weekday can appear only once per plumber.',
        ),
    ]

    @api.constrains('day_off', 'hour_from', 'hour_to')
    def _check_hours(self):
        for slot in self:
            if not slot.day_off and slot.hour_from >= slot.hour_to:
                raise ValidationError(
                    'Start time must be before end time.'
                )


class SolvitaskPlumberLine(models.Model):
    _name = 'solvitask.plumber.line'
    _description = 'Job Plumber Labor Line'

    job_id = fields.Many2one(
        'solvitask.job',
        required=True,
        ondelete='cascade'
    )

    plumber_id = fields.Many2one(
        'solvitask.plumber',
        required=True,
        ondelete='restrict'
    )

    hours_worked = fields.Float(
        string='Hours Worked',
        related='job_id.hours_worked',
        store=True,
        readonly=True
    )

    hourly_rate = fields.Float(
        string='Hourly Rate',
        digits=(12, 2),
        required=True
    )

    subtotal = fields.Float(
        string='Subtotal',
        compute='_compute_subtotal',
        store=True
    )

    _sql_constraints = [
        (
            'unique_job_plumber',
            'unique(job_id, plumber_id)',
            'A plumber can only have one line per job.'
        )
    ]

    @api.depends('hours_worked', 'hourly_rate')
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = (
                line.hours_worked * line.hourly_rate
            )
