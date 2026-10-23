from odoo import fields, models, api
from odoo.exceptions import ValidationError


class SolvitaskCustomer(models.Model):
    _name = 'solvitask.customer'
    _description = 'Customer'
    _inherit = ['solvitask.whatsapp.mixin']

    name = fields.Char(string='Name', required=True)
    surname = fields.Char(string='Surname', required=True)
    phone = fields.Char(string='Phone', required=True)
    email = fields.Char(string='Email')
    address = fields.Char(string='Address', required=True)
    birthday = fields.Date(string='Birthday', groups='solvitask.group_solvitask_manager,solvitask.group_solvitask_customer')

    user_id = fields.Many2one(
        comodel_name='res.users',
        string='Related User',
        ondelete='set null',
        groups='solvitask.group_solvitask_manager',
        help='Internal login belonging to this customer.',
        readonly=True)

    job_ids = fields.One2many(
        comodel_name='solvitask.job',
        inverse_name='customer_id',
        string='Jobs'
    )
    request_ids = fields.One2many(
        comodel_name="solvitask.requests",
        inverse_name="customer_id",
        string="Requests"
    )

    _sql_constraints = [('unique_user', 'unique(user_id)', 'A user can have only one customer profile.')]

    @api.model_create_multi
    def create(self, vals_list):
        self.check_access_rights('create')
        user_model = self.env['res.users'].sudo()
        for vals in vals_list:
            email = vals.get('email')

            if not email:
                raise ValidationError("Email field is required")

            existing_user = user_model.search(
                [('login', '=', email)],
                limit=1
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
                    (6, 0, [self.env.ref('base.group_user').id, self.env.ref('solvitask.group_solvitask_customer').id]),
                ],
            })
            vals['user_id'] = user.id

        customers = super().create(vals_list)

        return customers
