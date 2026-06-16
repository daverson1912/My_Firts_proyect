# -*- coding: utf-8 -*-
from odoo import models, fields, api

class L10nVeTaMulticurrencyApiConfig(models.Model):
    _name = 'l10n_ve_ta_multicurrency.api.config'
    _description = 'Configuracion Automatica Tasa BCV'
    _rec_name = 'l10n_ve_ta_multicurrency_api_url'

    l10n_ve_ta_multicurrency_enable_sync = fields.Boolean(
        string='Sincronización Automática',
        default=False,
    )
    l10n_ve_ta_multicurrency_enable_fiscal = fields.Boolean(
        string='Integración Fiscal (Retenciones)',
        default=False,
    )
    l10n_ve_ta_multicurrency_api_url = fields.Char(
        string='URL del Middleware BCV',
    )
    l10n_ve_ta_multicurrency_guid = fields.Char(string='Client GUID')
    company_id = fields.Many2one('res.company', string='Compañía', default=lambda self: self.env.company, required=True)
    active = fields.Boolean(string='Active', default=True)

    l10n_ve_ta_multicurrency_last_rate = fields.Float(string='Tasa Actual', compute='_compute_l10n_ve_ta_multicurrency_summary', store=True)
    l10n_ve_ta_multicurrency_last_api_update = fields.Char(string='Última Actualización (Middleware)', readonly=True)
    l10n_ve_ta_multicurrency_last_sync_date = fields.Date(string='Fecha de Sincronización', compute='_compute_l10n_ve_ta_multicurrency_summary', store=True)

    @api.depends('l10n_ve_ta_multicurrency_enable_sync', 'company_id.currency_id')
    def _compute_l10n_ve_ta_multicurrency_summary(self):
        """
        Determina de forma genérica la última tasa sincronizada para mostrarla en el panel.
        """
        for config in self:
            company_currency = config.company_id.currency_id
            if not company_currency:
                config.l10n_ve_ta_multicurrency_last_rate = 0.0
                config.l10n_ve_ta_multicurrency_last_sync_date = False
                continue
            
            # Buscar la primera divisa extranjera activa
            foreign_curr = self.env['res.currency'].sudo().search([
                ('id', '!=', company_currency.id),
                ('active', '=', True)
            ], order='name asc', limit=1)
            
            if not foreign_curr:
                config.l10n_ve_ta_multicurrency_last_rate = 0.0
                config.l10n_ve_ta_multicurrency_last_sync_date = False
                continue
                
            # Buscar la última tasa de cambio registrada para la divisa extranjera
            rate_obj = self.env['res.currency.rate'].search([
                ('currency_id', '=', foreign_curr.id),
                ('company_id', '=', config.company_id.id)
            ], order='name desc', limit=1)
            
            if rate_obj and rate_obj.rate > 0:
                if rate_obj.rate < 1.0:
                    config.l10n_ve_ta_multicurrency_last_rate = 1.0 / rate_obj.rate
                else:
                    config.l10n_ve_ta_multicurrency_last_rate = rate_obj.rate
                config.l10n_ve_ta_multicurrency_last_sync_date = rate_obj.name
            else:
                config.l10n_ve_ta_multicurrency_last_rate = 0.0
                config.l10n_ve_ta_multicurrency_last_sync_date = False

    def action_sync_now(self):
        result = self.env['res.currency'].action_l10n_ve_ta_multicurrency_sync_bcv_rates(force_config=self)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': "Sincronización",
                'message': result.get('message', ''),
                'type': 'success' if result.get('success') else 'danger',
                'sticky': False,
                'next': {'type': 'ir.actions.client', 'tag': 'reload'},
            }
        }
        
class L10nVeTaMulticurrencyGuide(models.Model):
    _name = 'l10n_ve_ta_multicurrency.guide'
    _description = 'User Guide'
    _order = 'sequence, id'

    name = fields.Char(string='Title', required=True)
    sequence = fields.Integer(string='Sequence', default=10)
    content = fields.Html(string='Content')
    active = fields.Boolean(default=True)
