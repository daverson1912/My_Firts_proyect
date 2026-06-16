import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = 'account.move'

    l10n_ve_control_number = fields.Char(
        string='Nro de Control',
        help='Número de control del documento físico emitido por el proveedor fiscal.',
        copy=False,
        readonly=True,
    )
    digital_document = fields.Char(
        string='Documento Digital',
        help='URL de consulta del documento fiscal digital (HKA Venezuela).',
        copy=False,
        readonly=True,
    )

    _TAFEL_LOCKED_FIELDS = frozenset({
        'partner_id', 'currency_id', 'journal_id', 'invoice_date',
    })

    def write(self, vals):
        if any(f in vals for f in self._TAFEL_LOCKED_FIELDS):
            for move in self:
                if (move.l10n_ve_control_number
                        and move.move_type in ('out_invoice', 'out_refund')):
                    raise UserError(_(
                        'La factura "%s" tiene un Nro. de Control fiscal asignado (%s). '
                        'No se pueden modificar datos críticos (cliente, moneda, diario, fecha).',
                        move.name, move.l10n_ve_control_number,
                    ))
        return super().write(vals)

    def action_view_digital_document(self):
        self.ensure_one()
        if not self.digital_document:
            return
        return {
            'type': 'ir.actions.act_url',
            'url': self.digital_document,
            'target': 'new',
        }

    def _post(self, soft=True):
        result = super()._post(soft=soft)
        for move in self.filtered(
            lambda m: m.state == 'posted'
            and m.move_type in ('out_invoice', 'out_refund')
        ):
            try:
                move._tafel_register_pending()
            except Exception:
                _logger.exception(
                    'Tafel: error al registrar pendiente para %s', move.name
                )
        return result

    def _tafel_register_pending(self):
        self.ensure_one()
        tafel_config = self.env['tafel.config'].search(
            [('company_id', '=', self.company_id.id)], limit=1
        )
        if not tafel_config or not tafel_config.provider_config_id:
            return
        journal_config = self.env['tafel.journal.config'].search([
            ('provider_config_id', '=', tafel_config.provider_config_id.id),
            ('journal_id', '=', self.journal_id.id),
            ('active', '=', True),
        ], limit=1)
        if not journal_config:
            return
        if journal_config.start_move_id and self.id < journal_config.start_move_id.id:
            return
        existing = self.env['tafel.fiscal.document'].search([
            ('move_id', '=', self.id),
            ('tafel_config_id', '=', tafel_config.id),
        ], limit=1)
        if existing:
            return
        self.env['tafel.fiscal.document'].create({
            'tafel_config_id': tafel_config.id,
            'provider_config_id': tafel_config.provider_config_id.id,
            'move_id': self.id,
            'move_name': self.name,
            'partner_name': self.partner_id.name,
            'amount_total': self.amount_total,
            'currency_id': self.currency_id.id,
            'transmission_date': fields.Datetime.now(),
            'status': 'pending',
        })


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    tafel_price_with_tax = fields.Float(
        string='Total con IVA (sin retención)',
        compute='_compute_tafel_price_with_tax',
        store=False,
        help='price_subtotal + impuestos positivos (IVA). Excluye retenciones. Útil para campos adicionales HKA.',
    )

    @api.depends('price_subtotal', 'tax_ids')
    def _compute_tafel_price_with_tax(self):
        for line in self:
            positive_tax_rate = sum(
                c.amount
                for t in line.tax_ids
                for c in (t.children_tax_ids if t.amount_type == 'group' else t)
                if c.amount > 0
            )
            line.tafel_price_with_tax = round(
                line.price_subtotal * (1 + positive_tax_rate / 100.0), 2
            )
