import base64
import json

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class TafelFiscalDocument(models.Model):
    _name = 'tafel.fiscal.document'
    _description = 'Documento Fiscal Transmitido'
    _order = 'transmission_date desc'
    _rec_name = 'move_name'

    tafel_config_id = fields.Many2one(
        'tafel.config',
        required=True,
        ondelete='cascade',
    )
    company_id = fields.Many2one(
        related='tafel_config_id.company_id',
        store=True,
    )
    provider_config_id = fields.Many2one(
        'tafel.provider.config',
        string='Proveedor',
        ondelete='restrict',
    )
    move_id = fields.Many2one(
        'account.move',
        string='Factura',
        ondelete='set null',
    )
    move_name = fields.Char(string='Nro. Factura', readonly=True)
    partner_name = fields.Char(string='Cliente', readonly=True)
    amount_total = fields.Monetary(
        string='Monto',
        currency_field='currency_id',
        readonly=True,
    )
    currency_id = fields.Many2one('res.currency', string='Moneda', readonly=True)
    transmission_date = fields.Datetime(string='Fecha', readonly=True)
    status = fields.Selection([
        ('pending', 'Pendiente'),
        ('success', 'Emitido'),
        ('error', 'Error'),
    ], string='Estatus', default='pending', required=True, readonly=True)
    status_message = fields.Text(string='Mensaje', readonly=True)
    fiscal_id = fields.Char(string='ID Fiscal', readonly=True)
    document_number = fields.Char(string='Nro de Control', readonly=True)
    pdf_url = fields.Char(string='URL Documento', readonly=True)
    disabled = fields.Boolean(
        string='Deshabilitado',
        default=False,
        help='Si está marcado, el cron no intentará transmitir esta transacción.',
    )
    fiscal_data_json = fields.Text(string='Datos del Documento Fiscal', readonly=True)
    payload_json = fields.Text(
        string='Payload Enviado',
        readonly=True,
        groups='tafel.group_tafel_manager',
    )
    response_json = fields.Text(
        string='Respuesta API Completa',
        readonly=True,
        groups='base.group_system',
    )

    attempt_ids = fields.One2many(
        'tafel.fiscal.document.attempt',
        'fiscal_document_id',
        string='Historial de Intentos',
    )
    attempt_count = fields.Integer(
        string='Intentos',
        compute='_compute_attempt_count',
        store=True,
    )

    @api.depends('attempt_ids')
    def _compute_attempt_count(self):
        for rec in self:
            rec.attempt_count = len(rec.attempt_ids)

    # -------------------------------------------------------------------------
    # Internal
    # -------------------------------------------------------------------------

    def _record_attempt(self, status, message, response_json):
        self.env['tafel.fiscal.document.attempt'].create({
            'fiscal_document_id': self.id,
            'status': status,
            'status_message': message,
            'response_json': response_json or '',
        })

    # -------------------------------------------------------------------------
    # Actions
    # -------------------------------------------------------------------------

    def action_disable(self):
        self.ensure_one()
        self.write({'disabled': True})

    def action_enable(self):
        self.ensure_one()
        self.write({'disabled': False})

    def action_retry(self):
        self.ensure_one()
        if not self.move_id:
            raise UserError(_('No se puede reenviar: la factura original ya no existe.'))
        tafel_config = self.tafel_config_id
        if not tafel_config or not tafel_config.provider_config_id:
            raise UserError(_('No hay configuración activa de Facturación Electrónica.'))
        journal_config = self.env['tafel.journal.config'].search([
            ('provider_config_id', '=', tafel_config.provider_config_id.id),
            ('journal_id', '=', self.move_id.journal_id.id),
            ('active', '=', True),
        ], limit=1)
        if not journal_config:
            raise UserError(
                _('No hay un correlativo activo configurado para el diario de esta factura.')
            )
        tafel_config._tafel_transmit(self.move_id, journal_config)

    def action_dry_run(self):
        self.ensure_one()
        if not self.move_id:
            raise UserError(_('No se puede simular: la factura original ya no existe.'))
        tafel_config = self.tafel_config_id
        if not tafel_config or not tafel_config.provider_config_id:
            raise UserError(_('No hay configuración activa de Facturación Electrónica.'))
        journal_config = self.env['tafel.journal.config'].search([
            ('provider_config_id', '=', tafel_config.provider_config_id.id),
            ('journal_id', '=', self.move_id.journal_id.id),
            ('active', '=', True),
        ], limit=1)
        if not journal_config:
            raise UserError(
                _('No hay un correlativo activo configurado para el diario de esta factura.')
            )
        import json as _json
        payload = tafel_config._tafel_build_payload(self.move_id, journal_config)
        self.write({'payload_json': _json.dumps(payload, ensure_ascii=False, indent=2)})
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Simulación completada'),
                'message': _('El payload fue generado y guardado. Revisa la sección "Payload Enviado".'),
                'type': 'success',
                'sticky': False,
            },
        }

    def action_download_pdf(self):
        self.ensure_one()
        if not self.pdf_url:
            raise UserError(_('No hay URL de PDF disponible para este documento.'))
        return {
            'type': 'ir.actions.act_url',
            'url': self.pdf_url,
            'target': 'new',
        }

    def action_download_payload(self):
        self.ensure_one()
        if not self.payload_json:
            raise UserError(_('No hay payload disponible para este documento.'))
        attachment = self.env['ir.attachment'].create({
            'name': f'payload_{self.move_name or self.id}.json',
            'type': 'binary',
            'datas': base64.b64encode(self.payload_json.encode('utf-8')).decode(),
            'res_model': self._name,
            'res_id': self.id,
            'mimetype': 'application/json',
        })
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'new',
        }
