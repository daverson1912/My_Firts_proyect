import logging
from datetime import datetime

import requests
from dateutil.relativedelta import relativedelta

from odoo import _, fields, models
from odoo.exceptions import UserError

from .res_config_settings import TAFEL_API_URL

_logger = logging.getLogger(__name__)

_REGISTER_ENDPOINT = '/api/auth/register'
_TIMEOUT = 15


class TafelSetupWizard(models.TransientModel):
    _name = 'tafel.setup.wizard'
    _description = 'Registro de Facturación Electrónica'

    company_name = fields.Char(
        string='Nombre de la Empresa',
        required=True,
        default=lambda self: self.env.company.name,
    )
    email = fields.Char(
        string='Correo Electrónico',
        required=True,
        default=lambda self: self.env.company.email,
    )
    password = fields.Char(string='Contraseña', required=True)
    password_confirm = fields.Char(string='Confirmar Contraseña', required=True)
    tax_id = fields.Char(
        string='RIF / ID Fiscal',
        required=True,
        default=lambda self: self.env.company.vat,
    )
    country_code = fields.Selection(
        [('VE', 'Venezuela')],
        string='País',
        required=True,
        default='VE',
    )

    # -------------------------------------------------------------------------
    # HTTP helpers
    # -------------------------------------------------------------------------

    def _get_api_base_url(self):
        return TAFEL_API_URL.rstrip('/')

    def _call_register_api(self, payload):
        url = self._get_api_base_url() + _REGISTER_ENDPOINT
        try:
            response = requests.post(
                url,
                json=payload,
                timeout=_TIMEOUT,
                headers={'Content-Type': 'application/json'},
            )
        except requests.exceptions.ConnectionError:
            raise UserError(
                _('No se pudo conectar con el servidor de Tafel. '
                  'Verifique la URL de la API en Ajustes y que el servidor esté disponible.')
            )
        except requests.exceptions.Timeout:
            raise UserError(
                _('El servidor de Tafel no respondió a tiempo (límite: %d s). '
                  'Intente de nuevo más tarde.') % _TIMEOUT
            )
        except requests.exceptions.RequestException as exc:
            _logger.exception('Tafel API unexpected request error: %s', exc)
            raise UserError(
                _('Error inesperado al contactar el servidor de Tafel: %s') % str(exc)
            )

        try:
            body = response.json()
        except ValueError:
            _logger.error(
                'Tafel API returned non-JSON response (HTTP %s): %s',
                response.status_code,
                response.text[:500],
            )
            raise UserError(
                _('El servidor de Tafel devolvió una respuesta inesperada (HTTP %d).')
                % response.status_code
            )

        if response.status_code == 201 and body.get('error') == 0:
            return body.get('data', {})

        error_code = body.get('error', -99)
        api_message = body.get('message', '')

        if response.status_code == 409 or error_code == -7:
            raise UserError(
                _('Este correo electrónico ya está registrado en Tafel. '
                  'Utilice otra dirección o contacte el soporte.')
            )
        if response.status_code == 400:
            raise UserError(
                _('Los datos enviados no son válidos. Verifique los campos e intente de nuevo.\n'
                  'Detalle: %s') % api_message
            )

        _logger.error(
            'Tafel API error (HTTP %s, code %s): %s',
            response.status_code,
            error_code,
            api_message,
        )
        raise UserError(
            _('El servidor de Tafel reportó un error (código %s): %s')
            % (error_code, api_message or _('Error desconocido.'))
        )

    def _create_api_key_for_config(self, config):
        expires_at = (
            datetime.utcnow() + relativedelta(years=3)
        ).strftime('%Y-%m-%dT%H:%M:%SZ')

        try:
            response = config._api_request(
                'POST', '/api/api-keys',
                json={'name': 'Odoo', 'expiresAt': expires_at},
            )
            body = response.json()
            if response.status_code == 201 and body.get('error') == 0:
                data = body.get('data', {})
                config.sudo().write({
                    'api_key_id': data.get('id'),
                    'api_key_raw': data.get('rawKey'),
                })
            else:
                _logger.warning(
                    'API key creation failed (HTTP %s): %s',
                    response.status_code,
                    body.get('message', ''),
                )
        except UserError as exc:
            _logger.warning('API key creation blocked: %s', exc)
        except Exception as exc:
            _logger.warning('API key creation unexpected error: %s', exc)

    # -------------------------------------------------------------------------
    # Public action
    # -------------------------------------------------------------------------

    def action_register(self):
        self.ensure_one()

        if self.password != self.password_confirm:
            raise UserError(_('Las contraseñas no coinciden.'))

        payload = {
            'name': self.company_name,
            'email': self.email,
            'password': self.password,
            'taxId': self.tax_id,
            'countryCode': self.country_code,
        }

        data = self._call_register_api(payload)

        tenant = data.get('tenant', {})
        config = self.env['tafel.config'].create({
            'company_id': self.env.company.id,
            'company_name': self.company_name,
            'email': self.email,
            'password': self.password,
            'tax_id': self.tax_id,
            'country_code': self.country_code,
            'tenant_id': tenant.get('id'),
            'plan': tenant.get('plan'),
            'access_token': data.get('accessToken'),
            'refresh_token': data.get('refreshToken'),
            'registration_date': fields.Datetime.now(),
        })

        self._create_api_key_for_config(config)

        action = self.env.ref('tafel.action_tafel_config').read()[0]
        action['res_id'] = config.id
        return action
