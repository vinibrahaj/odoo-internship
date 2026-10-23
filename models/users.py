from odoo import api, models
from odoo.exceptions import ValidationError


class ResUsers(models.Model):
    _inherit = 'res.users'

    @api.constrains('groups_id')
    def _check_solvitask_roles(self):
        roles = [self.env.ref('solvitask.group_solvitask_' + role, raise_if_not_found=False)
                 for role in ('customer', 'plumber', 'manager')]
        internal = self.env.ref('base.group_user')
        for user in self:
            assigned = [role for role in roles if role and role in user.groups_id]
            if len(assigned) > 1:
                raise ValidationError('Select exactly one SolviTask role per user.')
            if assigned and internal not in user.groups_id:
                raise ValidationError('SolviTask users must be Internal Users.')
            if assigned and assigned[0] != roles[2]:
                # Restrict MVP accounts to internal base and their SolviTask role.
                # Other application roles may grant access to confidential models.
                allowed = internal | assigned[0]
                implied = allowed
                while True:
                    expanded = implied | implied.mapped('implied_ids')
                    if expanded == implied:
                        break
                    implied = expanded
                extra = user.groups_id - implied
                # Technical feature groups are harmless only when inherited above.
                if extra:
                    raise ValidationError('Customer/plumber MVP logins may only have their SolviTask role and its implied groups. Remove other access groups.')
