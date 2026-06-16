# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from datetime import datetime


class SimplitFiscalSequenceWizard(models.TransientModel):
    _name = 'simplitfiscal.sequence.wizard'
    _description = 'Wizard para Configurar Correlativo de Retenciones'
    
    config_id = fields.Many2one(
        comodel_name='simplitfiscal.config',
        string='Configuración',
        required=True,
        ondelete='cascade',
    )
    
    current_sequence = fields.Char(
        string='Correlativo Actual (Formato Legal)',
        compute='_compute_current_sequence',
        help='Formato: AAAAMMSSSSSSSS (14 dígitos)',
    )
    
    sequence_number = fields.Integer(
        string='Número Secuencial',
        required=True,
        default=1,
        help='Últimos 8 dígitos del correlativo (consecutivo)',
    )
    
    @api.depends('sequence_number')
    def _compute_current_sequence(self):
        """
        Calcula el correlativo en formato legal AAAAMMSSSSSSSS.
        """
        for wizard in self:
            now = datetime.now()
            year = now.strftime('%Y')
            month = now.strftime('%m')
            sequential = str(wizard.sequence_number).zfill(8)
            
            wizard.current_sequence = f"{year}{month}{sequential}"
    
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
        
        # Actualizar mensaje informativo
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Correlativo Reseteado'),
                'message': _('El correlativo se ha reseteado a: %s') % self.current_sequence,
                'type': 'success',
                'sticky': False,
            }
        }
    
    def action_save_sequence(self):
        """
        Guarda el número secuencial en la configuración.
        """
        self.ensure_one()
        
        self.config_id.withholding_sequence_number = self.sequence_number
        self.config_id.withholding_sequence_display = self.current_sequence
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Correlativo Guardado'),
                'message': _('El correlativo actual es: %s') % self.current_sequence,
                'type': 'success',
                'sticky': False,
            }
        }
