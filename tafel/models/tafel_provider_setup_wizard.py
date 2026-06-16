import json
import logging

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .res_config_settings import TAFEL_API_URL
from .tafel_field_map import DEFAULT_FIELD_MAPS

_logger = logging.getLogger(__name__)


class TafelProviderSetupWizard(models.TransientModel):
    _name = 'tafel.provider.setup.wizard'
    _description = 'Configurar Proveedor de Facturación'

    tafel_config_id = fields.Many2one('tafel.config', required=True)
    provider_option_ids = fields.One2many(
        'tafel.provider.option',
        'wizard_id',
        string='Proveedores Disponibles',
    )
    selected_provider_option_id = fields.Many2one(
        'tafel.provider.option',
        string='Proveedor de Facturación',
        domain="[('wizard_id', '=', id)]",
    )
    credential_usuario = fields.Char(string='Usuario')
    credential_clave = fields.Char(string='Clave / Contraseña')
    credential_is_qa = fields.Boolean(
        string='Ambiente QA / Pruebas',
        default=True,
        help='Active si está usando credenciales del ambiente de pruebas (QA).',
    )

    # -------------------------------------------------------------------------
    # Helper (called from tafel.config.action_configure_provider)
    # -------------------------------------------------------------------------

    def _fetch_providers(self, country_code):
        base = TAFEL_API_URL
        try:
            response = requests.get(
                base.rstrip('/') + '/api/providers',
                params={'country': country_code},
                timeout=15,
            )
        except requests.exceptions.ConnectionError:
            raise UserError(
                _('No se pudo conectar con el servidor de Tafel (%s). '
                  'Verifique la URL de la API en Ajustes.') % base
            )
        except requests.exceptions.Timeout:
            raise UserError(_('El servidor de Tafel no respondió a tiempo (15 s).'))
        except requests.exceptions.RequestException as exc:
            raise UserError(_('Error al contactar el servidor de Tafel: %s') % str(exc))

        try:
            body = response.json()
        except ValueError:
            raise UserError(
                _('El servidor de Tafel devolvió una respuesta inesperada (HTTP %d):\n%s')
                % (response.status_code, response.text[:300])
            )

        if body.get('error') == 0:
            return body.get('data', [])

        raise UserError(
            _('La API de Tafel reportó un error al obtener proveedores (HTTP %d): %s')
            % (response.status_code, body.get('message') or _('Error desconocido.'))
        )

    # -------------------------------------------------------------------------
    # Action
    # -------------------------------------------------------------------------

    def action_save(self):
        self.ensure_one()
        if not self.selected_provider_option_id:
            raise UserError(_('Seleccione un proveedor de la lista.'))
        if not self.credential_usuario or not self.credential_clave:
            raise UserError(_('El usuario y la clave del proveedor son requeridos.'))

        config = self.tafel_config_id
        option = self.selected_provider_option_id

        try:
            response = config._api_request(
                'POST', '/api/tenant-providers',
                json={
                    'providerId': option.provider_id_api,
                    'credentials': {
                        'usuario': self.credential_usuario,
                        'clave': self.credential_clave,
                        'isQa': self.credential_is_qa,
                    },
                },
            )
        except UserError:
            raise
        except Exception as exc:
            _logger.exception('Error linking provider: %s', exc)
            raise UserError(
                _('Error inesperado al vincular el proveedor: %s') % str(exc)
            )

        try:
            body = response.json()
        except ValueError:
            raise UserError(
                _('El servidor devolvió una respuesta inesperada al vincular el proveedor.')
            )

        if response.status_code not in (200, 201) or body.get('error') != 0:
            raise UserError(
                _('No se pudo vincular el proveedor: %s')
                % body.get('message', _('Error desconocido.'))
            )

        tenant_provider_id = body.get('data', {}).get('id')

        provider = self.env['tafel.provider.config'].create({
            'tafel_config_id': config.id,
            'provider_id_api': option.provider_id_api,
            'provider_name': option.name,
            'tenant_provider_id': tenant_provider_id,
            'credential_usuario': self.credential_usuario,
            'credential_clave': self.credential_clave,
            'credential_is_qa': self.credential_is_qa,
            'config_schema_json': option.config_schema_json,
            'payment_methods_json': option.payment_methods_json,
        })

        try:
            payment_methods = json.loads(option.payment_methods_json or '[]')
        except (ValueError, TypeError):
            payment_methods = []

        for pm in payment_methods:
            code = pm.get('code') or pm.get('id') or ''
            name = pm.get('name') or pm.get('description') or code
            if not code:
                continue
            self.env['tafel.provider.payment.method'].create({
                'provider_config_id': provider.id,
                'code': code,
                'name': name,
                'description': pm.get('description', ''),
            })

        for fm in DEFAULT_FIELD_MAPS:
            self.env['tafel.field.map'].create({
                'provider_config_id': provider.id,
                **fm,
            })

        action = self.env.ref('tafel.action_tafel_config').read()[0]
        action['res_id'] = config.id
        return action
