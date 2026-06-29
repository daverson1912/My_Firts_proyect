import json
import os
import requests
from odoo import fields, models, api
from odoo.exceptions import UserError
from odoo.modules import get_module_resource
import logging

_logger = logging.getLogger(__name__)


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    whub_api_key = fields.Char(string='WHub API Key', help="Token de WispHub")
    whub_middleware_url = fields.Char(related='company_id.whub_middleware_url', readonly=False, string='URL del Middleware')
    whub_allowed_notice_statuses = fields.Char(related='company_id.whub_allowed_notice_statuses', readonly=False, string='Estados de Avisos Permitidos')
    whub_customers_page_size = fields.Integer(related='company_id.whub_customers_page_size', readonly=False, string='Tamaño de Página Clientes')
    whub_customers_max_pages = fields.Integer(related='company_id.whub_customers_max_pages', readonly=False, string='Páginas Máximas Clientes')

    whub_sync_date = fields.Datetime(related='company_id.whub_sync_date', readonly=True)
    
    # Nuevas fechas individuales
    whub_sync_cat = fields.Datetime(related='company_id.whub_sync_cat', readonly=True)
    whub_sync_prod = fields.Datetime(related='company_id.whub_sync_prod', readonly=True)
    whub_sync_plan = fields.Datetime(related='company_id.whub_sync_plan', readonly=True)
    whub_sync_cust = fields.Datetime(related='company_id.whub_sync_cust', readonly=True)

    # Pasos de configuración / Configuration steps
    whub_step_1_ok = fields.Boolean(string="Paso 1 Completado", compute='_compute_whub_steps')
    whub_step_2_ok = fields.Boolean(string="Paso 2 Completado", compute='_compute_whub_steps')

    @api.depends('company_id.whub_api_key', 'company_id.whub_sync_date')
    def _compute_whub_steps(self):
        for rec in self:
            step1 = bool(rec.company_id.whub_api_key)
            step2 = step1 and bool(rec.company_id.whub_sync_date)
            rec.whub_step_1_ok = step1
            rec.whub_step_2_ok = step2

    def _get_whub_config(self):
        """Lee la URL del middleware desde globalConfig.json si existe."""
        config_path = get_module_resource('whub_integration', 'globalConfig.json')
        if config_path and os.path.exists(config_path):
            with open(config_path, 'r') as f:
                return json.load(f)
        return {}

    def get_values(self):
        res = super(ResConfigSettings, self).get_values()
        # Si la compañía no tiene configurada la URL del Middleware, usar el valor por defecto del JSON
        middleware_url = self.env.company.whub_middleware_url
        if not middleware_url:
            config = self._get_whub_config()
            middleware_url = config.get('middleware_url', '')
            if middleware_url:
                self.env.company.sudo().write({'whub_middleware_url': middleware_url})

        res.update(
            whub_api_key=self.env.company.whub_api_key,
            whub_middleware_url=middleware_url,
        )
        return res

    def set_values(self):
        super(ResConfigSettings, self).set_values()
        self.env.company.whub_api_key = self.whub_api_key

    def test_connection(self):
        """Realiza un ping al middleware para validar la API Key (Punto 81 del Plan)."""
        url = (self.env.company.whub_middleware_url or '').strip().rstrip('/')
        
        if not url:
            raise UserError("No se ha configurado la URL del Middleware en globalConfig.json.")

        if not self.whub_api_key:
            raise UserError("Debe ingresar una API Key antes de probar la conexión.")

        try:
            _logger.info(f"Probando conexión WHub en: {url}")
            headers = {'Content-Type': 'application/json'}
            payload = {"auth": {"api_key": self.whub_api_key}, "filters": {}}
            response = requests.post(f"{url}/api/v1/wisphub/articles", json=payload, headers=headers, timeout=5)

            try:
                data = response.json()
            except Exception:
                data = {}

            if response.status_code in (200, 201):
                if data.get('error', 0) == 0:
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': 'Conexión Exitosa',
                            'message': '¡Perfecto! La conexión con WispHub es correcta.',
                            'type': 'success',
                            'sticky': False,
                        }
                    }
                else:
                    raise UserError("La API Key es incorrecta. Por favor, verifíquela en su panel de WispHub.")

            elif response.status_code in (401, 403):
                raise UserError("Credenciales inválidas: La API Key no es correcta o no tiene permisos suficientes.")

            else:
                msg = data.get('message') or "Error de comunicación con el Middleware."
                raise UserError(f"No se pudo establecer conexión (HTTP {response.status_code}): {msg}")
        except UserError:
            raise
        except requests.exceptions.RequestException as re:
            _logger.warning(f"Error de red en test_connection WispHub: {re}")
            raise UserError("No se pudo establecer conexión con WispHub. Verifique su red.")
        except Exception as e:
            _logger.error(f"Error inesperado en test_connection WispHub: {e}")
            raise UserError(f"Ocurrió un error inesperado al intentar conectar con WispHub: {str(e)}")

    def action_open_homologation_wizard(self):
        # Buscar el asistente persistente único para la compañía activa
        existing_wizard = self.env['whub.homologation.wizard'].search([
            ('company_id', '=', self.env.company.id)
        ], limit=1)
        if not existing_wizard:
            existing_wizard = self.env['whub.homologation.wizard'].create({
                'company_id': self.env.company.id
            })

        return {
            'name': 'Homologación WispHub',
            'type': 'ir.actions.act_window',
            'res_model': 'whub.homologation.wizard',
            'res_id': existing_wizard.id,
            'view_mode': 'form',
            'target': 'current',
        }


    def action_sync_payment_notices(self):
        """Abre el mini wizard para elegir el punto de partida y sincronizar avisos de cobro."""
        return {
            'type': 'ir.actions.act_window',
            'name': 'Sincronizar Avisos de Cobro',
            'res_model': 'whub.notice.sync.wizard',
            'view_mode': 'form',
            'target': 'new',
        }

    def action_open_sync_log(self):
        """Abre la vista del Log de Sincronización de Avisos."""
        return self.env.ref('whub_integration.action_whub_notice_sync_log').read()[0]

    def action_open_api_config(self):
        return {
            'name': 'Configurar Credenciales WispHub',
            'type': 'ir.actions.act_window',
            'res_model': 'whub.config.wizard',
            'view_mode': 'form',
            'target': 'new',
        }

class WHubConfigWizard(models.TransientModel):
    _name = 'whub.config.wizard'
    _description = 'Configurador de API WispHub'

    api_key = fields.Char('WHub API Key', required=True)

    @api.model
    def default_get(self, fields):
        res = super(WHubConfigWizard, self).default_get(fields)
        res['api_key'] = self.env.company.whub_api_key
        return res

    def action_test_connection(self):
        # Reutilizar lógica de test usando el nuevo campo de base de datos
        url = (self.env.company.whub_middleware_url or '').strip().rstrip('/')
        
        if not url:
            raise UserError("Error: Middleware URL no encontrada.")

        headers = {'Content-Type': 'application/json'}
        payload = {"auth": {"api_key": self.api_key}, "filters": {}}
        try:
            _logger.info(f"Validando API Key en: {url} (Wizard)")
            resp = requests.post(f"{url}/api/v1/wisphub/articles", json=payload, headers=headers, timeout=5)

            try:
                data = resp.json()
            except Exception:
                data = {}

            if resp.status_code in (200, 201) and data.get('error', 0) == 0:
                self.env.company.whub_api_key = self.api_key
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Conexión Exitosa',
                        'message': '¡Conexión validada y clave guardada correctamente!',
                        'type': 'success',
                        'sticky': False,
                        'next': {'type': 'ir.actions.act_window_close'}
                    }
                }
            else:
                msg = data.get('message') or data.get('error_desc') or 'Error de credenciales o de comunicación.'
                raise UserError(f"Fallo de validación (HTTP {resp.status_code}): {msg}")
        except UserError:
            raise
        except requests.exceptions.RequestException as re:
            _logger.warning(f"Error de red en validación WispHub (Wizard): {re}")
            raise UserError(
                "No se pudo establecer conexión con el Middleware WispHub.\n\n"
                "Por favor, verifique que la URL sea accesible y que el servicio de Middleware esté iniciado."
            )
        except Exception as e:
            _logger.error(f"Error inesperado en validación WispHub (Wizard): {e}")
            raise UserError(f"Ocurrió un error inesperado al intentar conectar: {str(e)}")
