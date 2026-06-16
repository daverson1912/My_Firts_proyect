from odoo import _, api, fields, models
from odoo.exceptions import UserError


class TafelProviderConfig(models.Model):
    _name = 'tafel.provider.config'
    _description = 'Proveedor de Facturación Electrónica'
    _rec_name = 'provider_name'

    tafel_config_id = fields.Many2one(
        'tafel.config',
        required=True,
        ondelete='cascade',
    )
    company_id = fields.Many2one(
        related='tafel_config_id.company_id',
        store=True,
    )
    provider_id_api = fields.Char(string='ID del Proveedor', required=True)
    provider_name = fields.Char(string='Proveedor', readonly=True)
    tenant_provider_id = fields.Char(
        string='UUID de Vínculo',
        readonly=True,
        copy=False,
    )
    tenant_provider_id_short = fields.Char(
        string='ID de Vínculo',
        compute='_compute_tenant_provider_id_short',
    )
    credential_usuario = fields.Char(
        string='Usuario',
        groups='tafel.group_tafel_manager',
    )
    credential_clave = fields.Char(
        string='Clave',
        groups='tafel.group_tafel_manager',
    )
    credential_is_qa = fields.Boolean(
        string='Ambiente QA / Pruebas',
        default=True,
    )
    config_schema_json = fields.Text(string='Schema de Configuración')
    payment_methods_json = fields.Text(string='Catálogo de Métodos de Pago')
    payment_method_map_ids = fields.One2many(
        'tafel.payment.method.map',
        'provider_config_id',
        string='Mapeo de Métodos de Pago',
    )
    journal_config_ids = fields.One2many(
        'tafel.journal.config',
        'provider_config_id',
        string='Correlativos',
    )
    field_map_ids = fields.One2many(
        'tafel.field.map',
        'provider_config_id',
        string='Mapeo de Campos',
    )
    custom_field_ids = fields.One2many(
        'tafel.custom.field',
        'provider_config_id',
        string='Información Adicional',
    )

    def action_update_credentials(self):
        self.ensure_one()
        try:
            response = self.tafel_config_id._api_request(
                'PUT',
                f'/api/tenant-providers/{self.tenant_provider_id}',
                json={
                    'credentials': {
                        'usuario': self.credential_usuario,
                        'clave': self.credential_clave,
                        'isQa': self.credential_is_qa,
                    }
                },
            )
            body = response.json()
        except UserError:
            raise
        except Exception as exc:
            raise UserError(_('Error al actualizar las credenciales: %s') % str(exc))

        if body.get('error') != 0:
            raise UserError(
                _('No se pudo actualizar: %s') % body.get('message', _('Error desconocido.'))
            )
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': _('Credenciales actualizadas correctamente en el proveedor.'),
                'type': 'success',
                'sticky': False,
            },
        }

    @api.depends('tenant_provider_id')
    def _compute_tenant_provider_id_short(self):
        for rec in self:
            rec.tenant_provider_id_short = (
                '...' + rec.tenant_provider_id[-6:]
            ) if rec.tenant_provider_id else ''
