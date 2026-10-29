from odoo import models, fields, _
from odoo.exceptions import ValidationError, AccessError

from job import STARTED_STAGES, CANCELED_STAGE


class CancelJobWizard(models.TransientModel):
    _name = 'solvitask.cancel.wizard'
    _description = 'Job Cancellation Wizard'

    job_id = fields.Many2one(
        'solvitask.job',
        string='Job',
        required=True,
        readonly=True,
    )

    cancel_reason = fields.Char(
        string='Cancellation Reason',
        required=True,
    )

    cancel_details = fields.Text(
        string='Cancellation Details',
        required=True,
    )

    def action_confirm_cancel(self):
        self.ensure_one()

        if not self.env.user.has_group('solvitask.group_solvitask_manager'):
            raise AccessError(_("Only managers can confirm this cancellation."))

        if not self.cancel_reason or not self.cancel_reason.strip():
            raise ValidationError(_("Cancellation reason is required."))

        if not self.cancel_details or not self.cancel_details.strip():
            raise ValidationError(_("Cancellation details are required."))

        self.job_id.write({
            'cancel_reason': self.cancel_reason.strip(),
            'cancel_details': self.cancel_details.strip(),
            'stage_id': CANCELED_STAGE,
        })

        return {'type': 'ir.actions.act_window_close'}
