# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError

class AccountWhIslrCustomerUnifier(models.TransientModel):
    _name = 'account.wh.islr.customer.unifier'
    _description = 'Cargar Comprobante de Retención ISLR (Venta)'

    partner_id = fields.Many2one(
        'res.partner', 
        string='Cliente', 
        readonly=True
    )
    
    number = fields.Char(
        string='Número de Comprobante', 
        required=True,
        help='Número de comprobante entregado por el cliente.'
    )

    date = fields.Date(
        string='Fecha del Comprobante', 
        required=True, 
        default=fields.Date.today
    )

    wh_islr_ids = fields.Many2many(
        'account.wh.islr', 
        string='Retenciones a Procesar'
    )

    def action_confirm(self):
        self.ensure_one()
        if not self.wh_islr_ids:
            return {'type': 'ir.actions.act_window_close'}
            
        # Asignar número, fecha y publicar
        self.wh_islr_ids.write({
            'name': self.number,
            'date': self.date,
            'state': 'posted'
        })
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Proceso Exitoso'),
                'message': _('Se han cargado %s retenciones de ISLR con el número %s') % (len(self.wh_islr_ids), self.number),
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            }
        }
