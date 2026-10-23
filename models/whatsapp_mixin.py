import re

from odoo import models
from odoo.exceptions import UserError

# Country calling code used when a phone number is stored in local form
# (e.g. "069 123 4567" -> "355691234567"). Change this for another country.
DEFAULT_COUNTRY_CODE = '355'


class SolvitaskWhatsappMixin(models.AbstractModel):
    """Adds a 'message on WhatsApp' button to any model with a `phone` field.

    An AbstractModel has no table of its own: it only carries behaviour that
    other models pick up through _inherit.
    """
    _name = 'solvitask.whatsapp.mixin'
    _description = 'WhatsApp link helper'

    def _whatsapp_number(self):
        """Return the phone in the digits-only form wa.me expects."""
        self.ensure_one()
        digits = re.sub(r'\D', '', self.phone or '')
        if not digits:
            return False
        # Strip the national trunk prefix ("069..." -> "69...") and add the
        # country code, unless the number already carries one.
        if digits.startswith('00'):
            return digits[2:]
        if digits.startswith(DEFAULT_COUNTRY_CODE):
            return digits
        return DEFAULT_COUNTRY_CODE + digits.lstrip('0')

    def action_open_whatsapp(self):
        self.ensure_one()
        number = self._whatsapp_number()
        if not number:
            raise UserError("No phone number on this record.")
        return {
            'type': 'ir.actions.act_url',
            'url': 'https://wa.me/%s' % number,
            'target': 'new',
        }
