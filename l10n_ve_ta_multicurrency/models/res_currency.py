from odoo import models, fields, api, _, tools
from odoo.exceptions import ValidationError
import requests
from datetime import date, datetime, timedelta
import logging
import json
import os

_logger = logging.getLogger(__name__)

class ResCurrency(models.Model):
    _inherit = 'res.currency'

    l10n_ve_ta_multicurrency_is_fiscal = fields.Boolean(
        string='Fiscal Currency',
        default=False,
        company_dependent=True,
        help="EN: Only one currency can be mark as the official fiscal currency (per company). | ES: Solo una moneda puede ser marcada como la moneda fiscal oficial (por compañía)."
    )

    l10n_ve_ta_multicurrency_is_reference = fields.Boolean(
        string='Reference Currency',
        default=False,
        company_dependent=True,
        help="EN: Only one currency can be marked as the reference currency for ISLR calculations (per company). | ES: Solo una moneda puede ser marcada como la moneda de referencia para cálculos ISLR (por compañía)."
    )

    l10n_ve_ta_multicurrency_is_locked = fields.Boolean(
        string="Bloqueada",
        default=False,
        company_dependent=True,
        help="Bloqueada porque otra moneda ya fue seleccionada como Referencial (por compañía)."
    )

    l10n_ve_ta_multicurrency_operation = fields.Selection(
        [
            ('multiply', 'Multiplicar'),
            ('divide', 'Dividir'),
        ],
        string='Operación',
        company_dependent=True,
        help="Define si la tasa de esta moneda se debe multiplicar o dividir respecto a la moneda de la compañía."
    )

    def write(self, vals):
        """
        EN: Manage the lock state per company without affecting other companies.
        ES: Gestiona el estado de bloqueo por compañía sin afectar otras compañías.
        """
        if self.env.context.get('skip_currency_lock_sync'):
            return super().write(vals)

        if 'l10n_ve_ta_multicurrency_is_fiscal' in vals and not vals['l10n_ve_ta_multicurrency_is_fiscal']:
            vals['l10n_ve_ta_multicurrency_operation'] = False

        result = super().write(vals)

        if 'l10n_ve_ta_multicurrency_is_fiscal' in vals:
            # Buscar la moneda fiscal para la compañía actual
            fiscal = self.env['res.currency'].search([
                ('l10n_ve_ta_multicurrency_is_fiscal', '=', True)
            ], limit=1)

            if fiscal:
                # Bloquear las demás SOLO para esta compañía
                others = self.env['res.currency'].search([('id', '!=', fiscal.id)])
                others.with_context(skip_currency_lock_sync=True).write({
                    'l10n_ve_ta_multicurrency_is_fiscal': False,
                    'l10n_ve_ta_multicurrency_is_locked': True,
                })
                fiscal.with_context(skip_currency_lock_sync=True).write({
                    'l10n_ve_ta_multicurrency_is_locked': False
                })
            else:
                # No hay fiscal para esta compañía — desbloquear todas
                all_currencies = self.env['res.currency'].search([])
                all_currencies.with_context(skip_currency_lock_sync=True).write({
                    'l10n_ve_ta_multicurrency_is_locked': False
                })

        return result

    @api.onchange('l10n_ve_ta_multicurrency_is_fiscal')
    def _onchange_l10n_ve_ta_multicurrency_is_fiscal(self):
        if not self.l10n_ve_ta_multicurrency_is_fiscal:
            self.l10n_ve_ta_multicurrency_operation = False

    @api.model_create_multi
    def create(self, vals_list):
        """
        EN: Handle multi-creation of currencies ensuring only one wins the fiscal flag.
        ES: Maneja la creación múltiple de monedas asegurando que solo una gane el flag fiscal.
        """
        records = super(ResCurrency, self).create(vals_list)
        if any(rec.l10n_ve_ta_multicurrency_is_fiscal for rec in records):
            fiscal_records = records.filtered('l10n_ve_ta_multicurrency_is_fiscal')
            winner = fiscal_records[-1]
            self.env['res.currency'].search([
                ('l10n_ve_ta_multicurrency_is_fiscal', '=', True),
                ('id', '!=', winner.id)
            ]).write({'l10n_ve_ta_multicurrency_is_fiscal': False})
            
            if len(fiscal_records) > 1:
                (fiscal_records - winner).write({'l10n_ve_ta_multicurrency_is_fiscal': False})
                
    def _l10n_ve_ta_multicurrency_get_api_params(self):
        """
        ES: Obtiene parámetros de API ÚNICAMENTE desde globalConfig.json en la raíz del módulo.
        """
        module_path = os.path.dirname(os.path.dirname(__file__))
        json_path = os.path.join(module_path, 'globalConfig.json')
        
        if os.path.exists(json_path):
            try:
                with open(json_path, 'r') as f:
                    json_config = json.load(f)
                    base_url = json_config.get('l10n_ve_ta_multicurrency_api_url')
                    api_key = json_config.get('l10n_ve_ta_multicurrency_api_guid')
                    if base_url and api_key:
                        return base_url, api_key
            except Exception as e:
                _logger.error(f"Error cargando globalConfig.json: {str(e)}")
        
        return None, None

    def action_l10n_ve_ta_multicurrency_sync_bcv_rates(self, force_config=None):
        """
        EN: Entry point for BCV Rate synchronization from an external API.
            Validates if sync is enabled per company in the centralized configuration.
        ES: Punto de entrada para la sincronización de tasas del BCV desde un API externo.
            Valida si la sincronización está habilitada por compañía en la configuración centralizada.
        """
        if force_config:
            api_configs = force_config
        else:
            api_configs = self.env['l10n_ve_ta_multicurrency.api.config'].search([
                ('l10n_ve_ta_multicurrency_enable_sync', '=', True),
                ('active', '=', True),
            ])
            
        if not api_configs:
            return True

        # Buscar fiscal: primero por flag, luego dinámicamente
        fiscal_currency = self.search([
            ('l10n_ve_ta_multicurrency_is_fiscal', '=', True)
        ], limit=1)
        if not fiscal_currency:
            # Fallback dinámico: la primera moneda activa distinta a la de la compañía actual
            company = self.env.company
            if company and company.currency_id:
                fiscal_currency = self.search([
                    ('id', '!=', company.currency_id.id),
                    ('active', '=', True)
                ], order='name asc', limit=1)
        if not fiscal_currency:
            return {'success': False, 'message': "No se ha configurado ninguna Moneda Fiscal (Bs.)."}

            
        base_url, api_key = self._l10n_ve_ta_multicurrency_get_api_params()
        
        if not base_url or not api_key:
            message = "El servicio de sincronización no está configurado correctamente. Por favor, contacte a soporte."
            _logger.error(message)
            return {'success': False, 'message': message}


        for api_config in api_configs:
            company = api_config.company_id
            
            # Prioridad absoluta al JSON (base_url / api_key)
            # Si el JSON tiene valores, ignoramos lo que diga la BD de la compañía
            url_to_use = base_url or api_config.l10n_ve_ta_multicurrency_api_url
            key_to_use = api_key or api_config.l10n_ve_ta_multicurrency_guid

            if not url_to_use:
                _logger.error(f"No se definió una URL de API válida para la compañía {company.name}")
                continue

            url = f"{url_to_use.rstrip('/')}/api/v1/bcv/rates/latest"
            query_date = date.today().strftime('%Y-%m-%d')
            headers = {'x-api-key': key_to_use}
            params = {'date': query_date}

            success = False
            rate_val = 0.0
            message = ""

            try:
                response = requests.get(url, params=params, headers=headers, timeout=10)
                response.raise_for_status()
                result = response.json()

                if result.get('error') == 0:
                    data = result.get('data', {})
                    try:
                        rate_val = float(data.get('usd_rate', 0.0))
                    except ValueError:
                        rate_val = 0.0
                    
                    is_fallback = data.get('is_fallback', False)
                    
                    if rate_val > 0:
                        success = True
                        message = "La tasa del día se ha actualizado correctamente."
                        if is_fallback:
                            message = "Tasa actualizada usando el valor de respaldo."
                        
                        api_update_time = data.get('updated_at', '')
                        if api_update_time:
                            api_config.sudo().write({'l10n_ve_ta_multicurrency_last_api_update': api_update_time})
                        
                        # Determine target currency first to get its operation setting
                        if fiscal_currency == company.currency_id:
                            # Company is VES, we update the foreign currency
                            target_currency = self.env['res.currency'].search([
                                ('id', '!=', company.currency_id.id),
                                ('active', '=', True)
                            ], order='name asc', limit=1)
                        else:
                            # Company is USD/EUR (Reference), we update the local currency (VES)
                            target_currency = fiscal_currency
                        
                        target_currency = target_currency or fiscal_currency
                        
                        # Use the specific operation defined for the target currency
                        sync_operation = target_currency.l10n_ve_ta_multicurrency_operation or 'multiply'
                        
                        if sync_operation == 'multiply':
                            final_rate_val = rate_val
                        else:
                            # Divide: Odoo expects 1/rate
                            final_rate_val = 1.0 / rate_val if rate_val else 0.0

                        if target_currency == company.currency_id:
                            _logger.info(f"Saltando actualizacion de tasa para {target_currency.name} ya que es la moneda base de la compañia {company.name}")
                            success = True
                            message = "Sincronización omitida: La moneda de destino es la moneda base de la compañía."
                            final_rate_val = 0.0
                        
                        if final_rate_val > 0:
                            # Validate if rate already exists for today
                            existing_rate = self.env['res.currency.rate'].sudo().search([
                                ('currency_id', '=', target_currency.id),
                                ('company_id', '=', company.id),
                                ('name', '=', query_date)
                            ], limit=1)
    
                            if existing_rate:
                                existing_rate.write({'rate': final_rate_val})
                            else:
                                self.env['res.currency.rate'].sudo().create({
                                    'name': query_date,
                                    'rate': final_rate_val,
                                    'currency_id': target_currency.id,
                                    'company_id': company.id,
                                })
                        elif target_currency != company.currency_id:
                            message = "El servicio devolvió una tasa no válida para el cálculo."
                            success = False
                else:
                    message = f"El servicio de tasas reportó un inconveniente: {result.get('message', 'Sin respuesta del servidor')}"

            except Exception as e:
                message = "Ocurrió un inconveniente al conectar con el servicio de tasas. Por favor, verifique su conexión a internet o intente más tarde."
                _logger.error(f"Error técnico de sincronización: {str(e)}")

            # Log the attempt
            try:
                log_target = target_currency if 'target_currency' in locals() else fiscal_currency
                self.env['l10n_ve_ta_multicurrency.rate.sync.log'].sudo().create({
                    'currency_id': log_target.id,
                    'company_id': company.id,
                    'l10n_ve_ta_multicurrency_fetched_rate': rate_val,
                    'l10n_ve_ta_multicurrency_status': 'success' if success else 'failed',
                    'l10n_ve_ta_multicurrency_response_msg': message,
                })
                
                if success:
                    _logger.info(f"BCV Sync SUCCESS: Tasa actualizada para {company.name}. Valor: {rate_val}")
                else:
                    _logger.warning(f"BCV Sync FAILURE: Falló sincronización para {company.name}. Motivo: {message}")

            except Exception as log_e:
                _logger.error(f"BCV Sync LOG ERROR: No se pudo registrar el log: {str(log_e)}")

        return {'success': success, 'message': message, 'rate': rate_val}


class ResCurrencyRate(models.Model):
    _inherit = 'res.currency.rate'

    rate = fields.Float(help="Tasa de cambio: Cantidad de esta moneda que equivale a 1 unidad de la moneda base.")
    inverse_company_rate = fields.Float(help="Tasa inversa: Valor de 1 unidad de esta moneda en la moneda base.")

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        self._trigger_applied_rate_recompute(records)
        return records

    def write(self, vals):
        res = super().write(vals)
        if 'rate' in vals or 'inverse_company_rate' in vals:
            self._trigger_applied_rate_recompute(self)
        return res

    def _trigger_applied_rate_recompute(self, rates):
        companies = rates.mapped('company_id')
        if not companies:
            return
        
        # 1. Draft Invoices (account.move)
        draft_moves = self.env['account.move'].search([
            ('state', '=', 'draft'),
            ('company_id', 'in', companies.ids),
        ])
        if draft_moves:
            draft_moves.modified(['l10n_ve_ta_multicurrency_applied_rate'])

        # 2. Draft/Sent Sale Orders (sale.order)
        if 'sale.order' in self.env:
            draft_sales = self.env['sale.order'].search([
                ('state', 'in', ('draft', 'sent')),
                ('company_id', 'in', companies.ids),
            ])
            if draft_sales:
                draft_sales.modified(['l10n_ve_ta_multicurrency_applied_rate'])

        # 3. Draft/RFQ Purchase Orders (purchase.order)
        if 'purchase.order' in self.env:
            draft_purchases = self.env['purchase.order'].search([
                ('state', 'in', ('draft', 'sent', 'to approve')),
                ('company_id', 'in', companies.ids),
            ])
            if draft_purchases:
                draft_purchases.modified(['l10n_ve_ta_multicurrency_applied_rate'])

