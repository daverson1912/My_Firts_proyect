from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    l10n_ve_ta_multicurrency_enable_sync = fields.Boolean(
        string='Sincronización Automática',
        help="Activa la actualización diaria automática de las tasas de cambio desde el BCV.",
    )
    l10n_ve_ta_multicurrency_enable_fiscal = fields.Boolean(
        string='Integración Fiscal (Retenciones)',
        help="Habilita el desglose de retenciones en Bolívares y adapta los Libros de IVA.",
    )

    l10n_ve_ta_multicurrency_last_rate = fields.Float(
        string='Tasa Oficial Actual',
        readonly=True,
        help="Última tasa obtenida del Banco Central de Venezuela."
    )

    l10n_ve_ta_multicurrency_last_sync_date = fields.Date(
        string='Última Fecha',
        readonly=True,
        help="Fecha de la última sincronización realizada."
    )

    def action_l10n_ve_ta_multicurrency_sync_now(self):
        self.ensure_one()
        # Guardar valores actuales antes de sincronizar
        self.set_values()
        
        # Buscar el registro de config específico de esta compañía
        config = self.env['l10n_ve_ta_multicurrency.api.config'].search([
            ('company_id', '=', self.env.company.id),
            ('active', '=', True)
        ], limit=1)
        
        # Forzar la sincronización para esta config (aunque esté desactivada en DB todavía)
        res = self.env['res.currency'].action_l10n_ve_ta_multicurrency_sync_bcv_rates(force_config=config)
        
        if isinstance(res, dict):
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Sincronización BCV',
                    'message': res.get('message', ''),
                    'type': 'success' if res.get('success') else 'danger',
                    'sticky': False,
                    'next': {'type': 'ir.actions.client', 'tag': 'reload'},
                }
            }
        return True

    @api.onchange('l10n_ve_ta_multicurrency_enable_sync', 'l10n_ve_ta_multicurrency_enable_fiscal')
    def _onchange_l10n_ve_ta_multicurrency_settings(self):
        """ Guarda los valores inmediatamente al cambiar los checks """
        if self.l10n_ve_ta_multicurrency_enable_fiscal:
            if not self.env.registry.get('account.wh.iva'):
                self.l10n_ve_ta_multicurrency_enable_fiscal = False
                return {
                    'warning': {
                        'title': _("Módulo Fiscal Requerido"),
                        'message': _("No puede activar la Integración Fiscal porque el módulo de leyes fiscales de Venezuela (Simplit/Fiscal) no está instalado en el sistema."),
                    }
                }
        # Forzar el guardado persistente
        self.set_values()

    def set_values(self):
        # Intentar obtener la compañía del registro, o de la sesión, o de la compañía activa
        company_id = self.company_id.id or self.env.company.id or self.env.user.company_id.id
        
        _logger.info(f"L10N_VE_TA: Guardando configuración para compañía {company_id}. Sync: {self.l10n_ve_ta_multicurrency_enable_sync}, Fiscal: {self.l10n_ve_ta_multicurrency_enable_fiscal}")
        
        config = self.env['l10n_ve_ta_multicurrency.api.config'].sudo().search([
            ('company_id', '=', company_id),
            ('active', '=', True),
        ], limit=1)
        
        vals = {
            'l10n_ve_ta_multicurrency_enable_sync': self.l10n_ve_ta_multicurrency_enable_sync,
            'l10n_ve_ta_multicurrency_enable_fiscal': self.l10n_ve_ta_multicurrency_enable_fiscal,
        }
        
        if not config:
            # Obtener URL por defecto desde la nueva jerarquía (Env/Conf/Param/JSON)
            base_url, _dummy = self.env['res.currency']._l10n_ve_ta_multicurrency_get_api_params()
            vals.update({
                'company_id': company_id,
                'l10n_ve_ta_multicurrency_api_url': base_url
            })
            self.env['l10n_ve_ta_multicurrency.api.config'].sudo().create(vals)
            _logger.info(f"L10N_VE_TA: Nueva configuración creada para compañía {company_id} con URL {vals.get('l10n_ve_ta_multicurrency_api_url')}")
        else:
            config.write(vals)
            _logger.info(f"L10N_VE_TA: Configuración actualizada para compañía {company_id}")

    @api.model
    def get_values(self):
        res = super().get_values()
        company_id = self.env.company.id
        config = self.env['l10n_ve_ta_multicurrency.api.config'].sudo().search([
            ('company_id', '=', company_id),
            ('active', '=', True),
        ], limit=1)

        # Leer la tasa directamente desde res.currency.rate para máxima precisión
        last_rate = 0.0
        last_date = False

        company_currency = self.env.company.currency_id
        foreign_curr = self.env['res.currency'].sudo().search([
            ('id', '!=', company_currency.id),
            ('active', '=', True)
        ], order='name asc', limit=1)

        if foreign_curr:
            rate_obj = self.env['res.currency.rate'].search([
                ('currency_id', '=', foreign_curr.id),
                ('company_id', '=', company_id),
            ], order='name desc', limit=1)
            if rate_obj and rate_obj.rate > 0:
                if rate_obj.rate < 1.0:
                    last_rate = 1.0 / rate_obj.rate
                else:
                    last_rate = rate_obj.rate
                last_date = rate_obj.name

        res.update({
            'l10n_ve_ta_multicurrency_enable_sync': config.l10n_ve_ta_multicurrency_enable_sync if config else False,
            'l10n_ve_ta_multicurrency_enable_fiscal': config.l10n_ve_ta_multicurrency_enable_fiscal if config else False,
            'l10n_ve_ta_multicurrency_last_rate': last_rate,
            'l10n_ve_ta_multicurrency_last_sync_date': last_date,
        })
        return res
