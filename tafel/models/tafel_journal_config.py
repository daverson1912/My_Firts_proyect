from odoo import api, fields, models
from odoo.exceptions import ValidationError


class TafelJournalConfig(models.Model):
    _name = 'tafel.journal.config'
    _description = 'Correlativo — Configuración de Transmisión'
    _rec_name = 'journal_id'

    provider_config_id = fields.Many2one(
        'tafel.provider.config',
        required=True,
        ondelete='cascade',
    )
    company_id = fields.Many2one(
        related='provider_config_id.company_id',
        store=True,
    )
    active = fields.Boolean(default=True)
    journal_id = fields.Many2one(
        'account.journal',
        string='Correlativo (Diario)',
        required=True,
        domain="[('type', '=', 'sale'), ('company_id', '=', company_id)]",
        ondelete='restrict',
    )
    start_move_id = fields.Many2one(
        'account.move',
        string='Transmitir desde',
        domain="[('journal_id', '=', journal_id), "
               " ('move_type', 'in', ['out_invoice', 'out_refund']), "
               " ('state', '=', 'posted')]",
        help='Factura a partir de la cual se comenzará a transmitir (inclusive). '
             'Si queda vacío se transmiten todas.',
        ondelete='set null',
    )
    serie_enabled = fields.Boolean(string='Serie HKA activa')
    serie_code = fields.Char(string='Código de Serie')

    _sql_constraints = [
        ('journal_provider_uniq', 'unique(journal_id, provider_config_id)',
         'Este diario ya está configurado para el proveedor.'),
    ]

    @api.constrains('serie_enabled', 'serie_code')
    def _check_serie_code(self):
        for rec in self:
            if rec.serie_enabled and not rec.serie_code:
                raise ValidationError(
                    'Debe indicar el Código de Serie cuando la Serie HKA está activa.'
                )
