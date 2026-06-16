# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from datetime import datetime


class SimplitFiscalISLRSequenceWizard(models.TransientModel):
    _name = 'simplitfiscal.islr.sequence.wizard'
    _description = 'Wizard para Configurar Correlativo de Retenciones ISLR'

    config_id = fields.Many2one(
        comodel_name='simplitfiscal.config',
        string='Configuración',
        required=True,
        ondelete='cascade',
    )

    current_sequence = fields.Char(
        string='Correlativo Actual',
        compute='_compute_current_sequence',
        help='Formato: AAAA + 6 dígitos secuenciales (10 dígitos)',
    )

    sequence_number = fields.Integer(
        string='Número Secuencial',
        required=True,
        default=1,
        help='Últimos 6 dígitos del correlativo (consecutivo)',
    )

    @api.depends('sequence_number')
    def _compute_current_sequence(self):
        """
        Calcula el correlativo en formato AAAA + 6 dígitos.
        Ejemplo: 2026000001
        """
        for wizard in self:
            year = datetime.now().strftime('%Y')
            sequential = str(wizard.sequence_number).zfill(6)
            wizard.current_sequence = f"{year}{sequential}"

    @api.constrains('sequence_number')
    def _check_sequence_number(self):
        """
        Valida que el número secuencial sea positivo.
        """
        for wizard in self:
            if wizard.sequence_number < 1:
                raise ValidationError(
                    _('El número secuencial debe ser mayor o igual a 1.')
                )

    def action_reset_sequence(self):
        """
        Resetea el correlativo a 1 (valor inicial).
        """
        self.ensure_one()
        self.sequence_number = 1

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Correlativo ISLR Reseteado'),
                'message': _('El correlativo se ha reseteado a: %s') % self.current_sequence,
                'type': 'success',
                'sticky': False,
            }
        }

    def action_save_sequence(self):
        """
        Guarda el número secuencial ISLR en la configuración.
        """
        self.ensure_one()

        self.config_id.islr_withholding_sequence_number = self.sequence_number
        self.config_id.islr_withholding_sequence_display = self.current_sequence

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Correlativo ISLR Guardado'),
                'message': _('El correlativo actual es: %s') % self.current_sequence,
                'type': 'success',
                'sticky': False,
            }
        }
