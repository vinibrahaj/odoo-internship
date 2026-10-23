from odoo import api, SUPERUSER_ID
from odoo.exceptions import ValidationError


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    roles = {key: env.ref('solvitask.group_solvitask_' + key)
             for key in ('customer', 'plumber', 'manager')}
    internal = env.ref('base.group_user')
    users = env['res.users'].with_context(active_test=False).search([
        ('groups_id', 'in', [g.id for g in roles.values()])])
    for user in users:
        assigned = [key for key, group in roles.items() if group in user.groups_id]
        if len(assigned) != 1:
            raise ValidationError('Resolve multiple SolviTask roles for user %s before upgrading.' % user.login)
        role = assigned[0]
        if role != 'manager':
            # Replace old broad/default permissions, retaining the explicit internal role.
            user.write({'groups_id': [(6, 0, (internal | roles[role]).ids)]})
    # Validate even existing users, whose groups might otherwise never be written.
    users._check_solvitask_roles()
