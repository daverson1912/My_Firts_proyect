from odoo import fields, models


class TafelFiscalDocumentAttempt(models.Model):
    _name = 'tafel.fiscal.document.attempt'
    _description = 'Historial de Intentos de Transmisión'
    _order = 'attempt_date desc'
    _rec_name = 'attempt_date'

    fiscal_document_id = fields.Many2one(
        'tafel.fiscal.document',
        required=True,
        ondelete='cascade',
    )
    attempt_date = fields.Datetime(
        string='Fecha',
        default=fields.Datetime.now,
        readonly=True,
    )
    status = fields.Selection([
        ('success', 'Emitido'),
        ('error', 'Error'),
    ], string='Resultado', required=True, readonly=True)
    status_message = fields.Text(string='Mensaje', readonly=True)
    response_json = fields.Text(string='Respuesta API', readonly=True)
