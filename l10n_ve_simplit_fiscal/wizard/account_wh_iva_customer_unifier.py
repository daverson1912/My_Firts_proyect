# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

class AccountWhIvaCustomerUnifier(models.TransientModel):
    _name = 'account.wh.iva.customer.unifier'
    _description = 'Cargar Comprobante de Retención IVA (Venta)'

    partner_id = fields.Many2one('res.partner', string='Cliente', readonly=True)
    wh_number = fields.Char(string='Número de Comprobante', required=True)
    date = fields.Date(string='Fecha del Comprobante', required=True, default=fields.Date.today)
    wh_iva_ids = fields.Many2many('account.wh.iva', string='Retenciones a Procesar')

    @api.constrains('wh_number')
    def _check_wh_number(self):
        for rec in self:
            if rec.wh_number:
                # El formato estándar es AAAAMMDDDDDDDD (14 caracteres)
                if len(rec.wh_number) != 14:
                    raise ValidationError(_("El número de comprobante de IVA debe tener exactamente 14 caracteres (formato AAAAMMDDDDDDDD)."))
                if not rec.wh_number.isdigit():
                    raise ValidationError(_("El número de comprobante de IVA debe contener solo caracteres numéricos."))

    def action_confirm(self):
        self.ensure_one()
        if not self.wh_iva_ids:
            return {'type': 'ir.actions.act_window_close'}
            
        # Asignar número, fecha y publicar
        self.wh_iva_ids.write({
            'name': self.wh_number,
            'date': self.date,
            'state': 'posted'
        })
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Proceso Exitoso'),
                'message': _('Se han cargado %s retenciones con el número %s') % (len(self.wh_iva_ids), self.wh_number),
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            }
        }
