from odoo import fields, models, api


class WHubNoticeSyncWizard(models.TransientModel):
    """
    Wizard para consulta de avisos de cobro por rango de fechas.
    Permite sincronizar avisos de WispHub en un periodo específico.
    """
    _name = 'whub.notice.sync.wizard'
    _description = 'Wizard de Consulta de Avisos por Fechas'

    date_from = fields.Date(string='Fecha Desde', required=True, default=fields.Date.context_today)
    date_to = fields.Date(string='Fecha Hasta', required=True, default=fields.Date.context_today)
    days_back = fields.Integer(string='Días de Búsqueda de Avisos', default=lambda self: self.env.company.whub_notice_sync_days_back or 30)

    def action_sync_by_dates(self):
        """
        Ejecuta la sincronización de avisos usando el rango de fechas seleccionado.
        """
        self.ensure_one()
        sync_engine = self.env['whub.notice.sync.engine']
        
        # Validar que fecha_from no sea mayor a fecha_to
        if self.date_from > self.date_to:
            raise models.UserError('La fecha Desde no puede ser mayor a la fecha Hasta.')
        
        # Guardar los días de búsqueda atrás en la compañía
        self.env.company.sudo().write({
            'whub_notice_sync_days_back': self.days_back
        })
        
        # Llamar al método de sincronización con fechas personalizadas
        result = sync_engine.action_sync_payment_notices_by_dates(
            date_from=self.date_from,
            date_to=self.date_to
        )
        
        return result
