from odoo import fields, models


class SolvitaskService(models.Model):
    _name = 'solvitask.service'
    _description = 'Service'

    name = fields.Char(string='Service', required=True)
    # The catalog price for this kind of work. Copied onto a job as its
    # starting price (see job._compute_initial_price).
    unit_price = fields.Float(string='Unit Price', digits=(12, 2), required=True)
    plumber_count = fields.Integer(
        string='Plumbers Required', default=1, required=True,
        help='How many plumbers this kind of job normally needs.')
    description = fields.Text(string='Description')

    # The tools you'd normally bring for this kind of job.
    default_tool_ids = fields.Many2many('solvitask.tool', string='Recommended Tools')


class SolvitaskMaterial(models.Model):
    _name = 'solvitask.material'
    _description = 'Material / Part'

    name = fields.Char(string='Material', required=True)
    unit = fields.Selection(
        string='Unit',
        selection=[('unit', 'Unit'),
                   ('m', 'Meter'),
                   ('kg', 'Kg'),
                   ('l', 'Liter')],
        default='unit',
    )
    unit_price = fields.Float(string='Unit Price', digits=(12, 2))

class SolvitaskTool(models.Model):
    _name = 'solvitask.tool'
    _description = 'Tool'

    name = fields.Char(string='Tool', required=True)
    description = fields.Char(string='Description')
