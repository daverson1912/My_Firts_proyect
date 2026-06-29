from datetime import datetime

from odoo import fields, models


class WHubNoticeSyncWizard(models.TransientModel):
    """
    Mini wizard para sincronizar avisos de cobro desde un punto de inicio elegido
    por el usuario. A partir de ese punto, trae todas las órdenes hasta ahora y deja
    ese punto guardado para que el cron continúe automáticamente cada 20 minutos.
    """
    _name = 'whub.notice.sync.wizard'
    _description = 'Wizard de Sincronización de Avisos de Cobro'

    date_from = fields.Date(
        string='Punto de Inicio',
        required=True,
        default=lambda self: (self.env.company.whub_sync_inv or fields.Datetime.now()).date()
    )

    def action_sync_from_date(self):
        """ Ejecuta la sincronización desde el punto de inicio elegido (00:00) hasta ahora. """
        self.ensure_one()
        date_from_dt = datetime.combine(self.date_from, datetime.min.time())
        return self.env['whub.notice.sync.engine'].action_sync_payment_notices_from(date_from_dt)
