import json
from odoo import fields, models, api


class WHubNoticeSyncLog(models.Model):
    """
    Log de Sincronización de Avisos de Cobro (Payment Notices).
    Registra cada intento de importación, permitiendo re-procesar fallos
    tras corregir homologaciones.
    """
    _name = 'whub.notice.sync.log'
    _description = 'Log de Sincronización de Avisos WispHub'
    _order = 'sync_date desc, id desc'
    _rec_name = 'whub_invoice_id'

    whub_invoice_id = fields.Char(string='ID Aviso WispHub', index=True)
    company_id = fields.Many2one('res.company', string='Compañía', default=lambda self: self.env.company, index=True)
    sync_date = fields.Datetime(string='Fecha de Sincronización', default=fields.Datetime.now)

    state = fields.Selection([
        ('success', 'Exitoso'),
        ('warning_skip', 'Advertencia (Omitido)'),
        ('error_mapping', 'Error de Mapeo'),
        ('error_connection', 'Error de Conexión'),
        ('error_other', 'Otro Error'),
    ], string='Estado', required=True, default='success', index=True)

    sale_order_id = fields.Many2one('sale.order', string='Orden de Venta Generada')
    invoice_id = fields.Many2one('account.move', string='Factura Generada')
    partner_id = fields.Many2one('res.partner', string='Cliente')
    customer_name_wh = fields.Char(string='Nombre Cliente WH')

    error_message = fields.Text(string='Detalle del Error')
    missing_entity = fields.Char(string='Entidad Faltante')
    raw_json = fields.Text(string='Información Técnica')

    can_reprocess = fields.Boolean(string='Puede Re-procesar', compute='_compute_can_reprocess', store=True)

    @api.depends('state')
    def _compute_can_reprocess(self):
        for rec in self:
            rec.can_reprocess = rec.state in ('error_mapping', 'error_other')

    def action_reprocess(self):
        """Re-procesa un aviso que falló."""
        self.ensure_one()
        if not self.raw_json: return False
        try:
            notice_data = json.loads(self.raw_json)
        except: return False

        sync_engine = self.env['whub.notice.sync.engine']
        result = sync_engine._process_single_notice(notice_data, self.company_id)

        if result.get('success'):
            self.write({
                'state': 'success',
                'sale_order_id': result.get('sale_order_id'),
                'invoice_id': result.get('invoice_id'),
                'partner_id': result.get('partner_id'),
                'error_message': False,
                'missing_entity': False,
            })
        else:
            self.write({
                'state': result.get('state', 'error_other'),
                'error_message': result.get('error_message'),
                'missing_entity': result.get('missing_entity'),
            })
        return True

    def action_open_homologation(self):
        return self.env['res.config.settings'].action_open_homologation_wizard()

    def action_view_sale_order(self):
        self.ensure_one()
        if not self.sale_order_id: return
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'res_id': self.sale_order_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_view_invoice(self):
        self.ensure_one()
        if not self.invoice_id: return
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': self.invoice_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_open_date_wizard(self):
        """Abre el wizard para consultar avisos por fechas."""
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'whub.notice.sync.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {},
        }
