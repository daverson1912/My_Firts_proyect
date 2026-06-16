# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)


class SimplitFiscalConfig(models.Model):
    """
    Modelo de configuración centralizada para Simplit Fiscal.
    Este modelo es un singleton que almacena toda la configuración
    del módulo de gestión fiscal venezolana.
    """
    _name = 'simplitfiscal.config'
    _description = 'Configuración de Simplit Fiscal'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    # ========== CAMPOS DE INFORMACIÓN BÁSICA ==========
    
    name = fields.Char(
        string='Nombre de Configuración',
        default='Configuración Fiscal Venezuela',
        required=True,
        tracking=True,
    )
    
    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        required=True,
        default=lambda self: self.env.company,
        tracking=True,
    )
    
    active = fields.Boolean(
        string='Activa',
        default=True,
        tracking=True,
    )
    
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('configured', 'Configurada'),
        ('active', 'Activa'),
    ], string='Estado', default='draft', required=True, tracking=True)

    # ========== CONEXIÓN API ==========

    ta_api_key = fields.Char(
        string='API Key',
        readonly=True,
        help='API Key generada automáticamente al registrar la licencia. Se usa para autenticar las peticiones al API.',
        tracking=True,
    )

    ta_api_connected = fields.Boolean(
        string='API Conectada',
        compute='_compute_ta_api_connected',
        store=False,
    )

    @api.depends('ta_api_key')
    def _compute_ta_api_connected(self):
        for rec in self:
            rec.ta_api_connected = bool(rec.ta_api_key)
    
    # ========== CONFIGURACIÓN GENERAL ==========
    
    is_withholding_agent = fields.Boolean(
        string='Es Agente de Retención IVA',
        help='Indica si esta empresa es un Contribuyente Especial designado '
             'por el SENIAT como Agente de Retención de IVA en Venezuela.',
        default=False,
        tracking=True,
    )
    
    default_retention_type = fields.Selection([
        ('75', 'Retención 75%'),
        ('100', 'Retención 100%'),
    ], string='Tipo de Retención por Defecto',
       help='Porcentaje de retención que aplica su empresa como Agente de Retención. '
            'Este será el valor por defecto al configurar proveedores.',
       tracking=True,
    )

    islr_provider_type_id = fields.Many2one(
        'islr.provider.type',
        string='Tipo de Beneficiario ISLR (Compañía)',
        help='Tipo de beneficiario ISLR de su empresa. Se usa para calcular retenciones recibidas en ventas.',
        tracking=True,
    )
    
    country_id = fields.Many2one(
        'res.country',
        related='company_id.country_id',
        string='País de la Compañía',
        store=True,
        readonly=True,
    )
    
    # ========== INFORMACIÓN DE IMPUESTOS ==========
    
    taxes_generated = fields.Boolean(
        string='Impuestos Generados',
        default=False,
        readonly=True,
        help='Indica si ya se generaron los impuestos automáticamente.',
    )
    
    withholding_sequence_number = fields.Integer(
        string='Correlativo Actual de Retenciones IVA',
        default=1,
        help='Número secuencial actual para comprobantes de retención IVA (últimos 8 dígitos del formato AAAAMMSSSSSSSS).',
    )

    islr_withholding_sequence_number = fields.Integer(
        string='Correlativo Actual de Retenciones ISLR',
        default=1,
        help='Número secuencial actual para comprobantes de retención ISLR (últimos 6 dígitos del formato AAAASSSSSS).',
    )

    withholding_sequence_display = fields.Char(
        string='Correlativo Completo IVA',
        readonly=True,
        help='Número de correlativo completo de IVA en formato AAAAMMSSSSSSSS (14 dígitos).',
    )

    islr_withholding_sequence_display = fields.Char(
        string='Correlativo Completo ISLR',
        readonly=True,
        help='Número de correlativo completo de ISLR en formato ISLRAAAAMMSSSSSSSS.',
    )
    
    # --- CONFIGURACIÓN CONTABLE ISLR VENTAS ---

    l10n_ve_islr_journal_id_sale = fields.Many2one(
        'account.journal',
        string='Diario de Retención ISLR (Ventas)',
        check_company=True,
        help='Diario para asientos de retención ISLR en operaciones de venta.',
        tracking=True,
    )

    l10n_ve_islr_account_id_sale = fields.Many2one(
        'account.account',
        string='Cuenta Contable ISLR (Ventas)',
        check_company=True,
        help='Cuenta de pasivo para la retención ISLR recibida en ventas.',
        tracking=True,
    )

    # --- CONFIGURACIÓN CONTABLE ISLR COMPRAS ---

    l10n_ve_islr_journal_id_purchase = fields.Many2one(
        'account.journal',
        string='Diario de Retención ISLR (Compras)',
        check_company=True,
        help='Diario para asientos de retención ISLR en operaciones de compra.',
        tracking=True,
    )

    l10n_ve_islr_account_id_purchase = fields.Many2one(
        'account.account',
        string='Cuenta Contable ISLR (Compras)',
        check_company=True,
        help='Cuenta de pasivo para la retención ISLR efectuada en compras.',
        tracking=True,
    )

    taxes_count = fields.Integer(
        string='Cantidad de Impuestos',
        compute='_compute_taxes_count',
        store=False,
    )
    
    tax_groups_count = fields.Integer(
        string='Cantidad de Grupos de Impuestos',
        compute='_compute_taxes_count',
        store=False,
    )
    
    # ========== MÉTODOS COMPUTADOS ==========
    
    @api.depends('company_id')
    def _compute_taxes_count(self):
        """
        Calcula la cantidad de impuestos y grupos creados por este módulo.
        """
        for record in self:
            # Buscar impuestos creados por este módulo (con external_id específico)
            taxes = self.env['account.tax'].search([
                ('company_id', '=', record.company_id.id),
            ])
            
            # Filtrar solo los que tienen el prefijo de este módulo
            module_taxes = taxes.filtered(
                lambda t: self.env['ir.model.data'].search([
                    ('model', '=', 'account.tax'),
                    ('res_id', '=', t.id),
                    ('module', '=', 'l10n_ve_simplit_fiscal'),
                ], limit=1)
            )
            
            record.taxes_count = len(module_taxes.filtered(lambda t: t.type_tax_use != 'none'))
            record.tax_groups_count = len(module_taxes.filtered(lambda t: t.amount_type == 'group'))
    
    # ========== CONSTRAINTS ==========
    
    @api.constrains('company_id')
    def _check_country_venezuela(self):
        """
        Valida que la compañía sea de Venezuela.
        """
        for record in self:
            if record.company_id.country_id.code != 'VE':
                raise ValidationError(
                    _('Este módulo solo puede ser utilizado por empresas venezolanas. '
                      'El país de la compañía debe ser Venezuela.')
                )
    
    # ========== MÉTODOS DE ACCIÓN ==========
    
    def action_sync_islr_master_data(self):
        """
        Sincroniza manualmente los Maestros ISLR desde el API.
        Requiere API Key activa.
        """
        self.ensure_one()
        if not self.ta_api_key:
            raise UserError(
                _('Debe conectarse primero con TotalAplicaciones. '
                  'Vaya a la pestaña "Configuración" e ingrese su clave de licencia.')
            )
        from ..hooks import sync_islr_master_data
        sync_islr_master_data(self.env, api_key=self.ta_api_key)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Maestros Actualizados'),
                'message': _('Se han actualizado los modelos de Tipos de Proveedor y Conceptos de Retención correctamente.'),
                'type': 'success',
                'sticky': False,
            }
        }

    def action_register_api(self):
        """
        Registra la licencia con el API de TotalAplicaciones
        y obtiene el API Key para la compañía actual.
        """
        self.ensure_one()
        import requests

        from .utils import get_api_url, get_config_value
        api_host = get_api_url()
        is_dev = get_config_value('IS_DEV', False)

        # Leer licencia de Odoo Enterprise o usar valor demo en DEV
        license_key = self.env['ir.config_parameter'].sudo().get_param('database.enterprise_code', '')
        if not license_key:
            if is_dev:
                license_key = 'DEMO-RET-0001'
                _logger.info("API Register: Modo DEV activo, usando licencia demo: DEMO-RET-0001")
            else:
                raise UserError(
                    _('No se encontró una licencia de Odoo Enterprise activa. '
                      'Verifique que su instancia esté licenciada correctamente.')
                )

        if not api_host:
            raise UserError(
                _('No se ha configurado la URL del API. Verifique el archivo globalConfig.json.')
            )

        url = f"{api_host.rstrip('/')}/api/v1/licensing/register"
        payload = {
            'licenseKey': license_key.strip(),
            'description': f"{self.company_id.name} - Odoo",
            'companies': [{
                'odooId': self.company_id.id,
                'name': self.company_id.name,
                'ivaCorrelativeStart': self.withholding_sequence_display or str(self.withholding_sequence_number),
                'islrCorrelativeStart': self.islr_withholding_sequence_display or str(self.islr_withholding_sequence_number),
            }],
        }

        try:
            _logger.info(f"API Register: POST {url} con licencia {license_key}")
            response = requests.post(url, json=payload, timeout=15)
            _logger.info(f"API Response Body: {response.text}")
            
            try:
                res_data = response.json()
            except:
                res_data = {}

            # 1. Validar Status HTTP (201 es éxito para registro)
            if response.status_code not in (200, 201):
                msg = res_data.get('message') or _("Error de comunicación con el Servicio Fiscal (Status: %s).") % response.status_code
                raise UserError(msg)

            # 2. Validar campo error
            if res_data.get('error', 0) != 0:
                msg = res_data.get('message', _("Error de registro: Clave de licencia inválida o duplicada."))
                raise UserError(msg)

            # 3. Procesar Data
            data = res_data.get('data', {})
            companies = data.get('companies', [])

            # Buscar el API Key que corresponde a nuestra compañía
            api_key = None
            for comp in companies:
                if comp.get('odooId') == self.company_id.id:
                    api_key = comp.get('apiKey')
                    break

            if not api_key and companies:
                api_key = companies[0].get('apiKey')

            if api_key:
                self.ta_api_key = api_key
                _logger.info(f"API Register: API Key obtenida exitosamente para company {self.company_id.id}")
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('¡Conexión Exitosa!'),
                        'message': _('Se ha registrado correctamente con TotalAplicaciones. API Key guardada.'),
                        'type': 'success',
                        'sticky': False,
                    }
                }
            else:
                raise UserError(
                    _('El registro fue exitoso pero no se encontró un API Key para la compañía %s.') % self.company_id.name
                )

        except requests.exceptions.ConnectionError:
            raise UserError(
                _('No se pudo conectar con el servidor de TotalAplicaciones. Verifique su conexión a internet.')
            )
        except requests.exceptions.Timeout:
            raise UserError(
                _('La conexión con el servidor agotó el tiempo de espera. Intente más tarde.')
            )
        except UserError:
            raise
        except Exception as e:
            _logger.error(f"API Register: Error inesperado: {str(e)}")
            raise UserError(
                _('Error inesperado al registrar: %s') % str(e)
            )

    @api.model
    def trigger_islr_sync_on_update(self, *args, **kwargs):
        """
        Método invocado desde data XML al actualizar el módulo.
        Garantiza que la data maestra se sincronice automáticamente en cada -u.
        """
        try:
            # Revertir a import relativo y proteger la ejecución
            from ..hooks import sync_islr_master_data
            _logger.info("ISLR Sync: Triggering automatic sync on module update...")
            sync_islr_master_data(self.env)
        except Exception as e:
            # Importante: No permitir que un error de sync detenga la actualización del módulo (-u)
            _logger.warning(f"ISLR Auto-Sync failed during module update (Safe Fail): {str(e)}")

    def action_generate_taxes(self):
        """
        Genera automáticamente los tax groups, impuestos base y grupos combo para COMPRAS y VENTAS.
        """
        self.ensure_one()
        
        # Verificar que la empresa sea Agente de Retención
        if not self.is_withholding_agent:
            raise UserError(
                _('Debe activar "Es Agente de Retención IVA" antes de generar los impuestos.')
            )
        
        company = self.company_id
        IrModelData = self.env['ir.model.data']
        AccountTax = self.env['account.tax']
        AccountTaxGroup = self.env['account.tax.group']
        
        # ========== PARTE A: Crear Tax Groups (Categorías) ==========
        
        comp_suffix = f"comp_{company.id}"
        tax_groups_data = [
            {'name': 'IVA 16%', 'xml_id': 'tax_group_sp_iva_16'},
            {'name': 'IVA 8%', 'xml_id': 'tax_group_sp_ivar_8'},
            {'name': 'Retención IVA 75%', 'xml_id': 'tax_group_sp_ret_75'},
            {'name': 'Retención IVA 100%', 'xml_id': 'tax_group_sp_ret_100'},
        ]
        
        created_tax_groups = {}
        for tg_data in tax_groups_data:
            tax_group = AccountTaxGroup.search([
                ('name', '=', tg_data['name']),
                ('company_id', '=', company.id)
            ], limit=1)
            
            if not tax_group:
                tax_group = AccountTaxGroup.create({
                    'name': tg_data['name'],
                    'company_id': company.id,
                })
            
            xml_full_id = f"l10n_ve_simplit_fiscal.{tg_data['xml_id']}_{comp_suffix}"
            if not self.env.ref(xml_full_id, raise_if_not_found=False):
                IrModelData.create({
                    'name': f"{tg_data['xml_id']}_{comp_suffix}",
                    'model': 'account.tax.group',
                    'module': 'l10n_ve_simplit_fiscal',
                    'res_id': tax_group.id,
                    'noupdate': True,
                })
            created_tax_groups[tg_data['xml_id']] = tax_group
        
        # ========== PARTE B: Definir Impuestos Base (Compras y Ventas) ==========
        
        taxes_to_create = []
        for use in ['purchase', 'sale']:
            use_label = 'Compras' if use == 'purchase' else 'Ventas'
            prefix = 'purchase_' if use == 'purchase' else 'sale_'
            
            taxes_to_create += [
                {
                    'name': f'IVA 16% ({use_label})',
                    'xml_id': f'{prefix}tax_iva_16',
                    'amount': 16.0,
                    'type_tax_use': use,
                    'description': f'IVA 16% {use_label}',
                    'tax_group_id': created_tax_groups['tax_group_sp_iva_16'].id,
                    'simplit_tax_type': f'{prefix}iva_16',
                },
                {
                    'name': f'IVA 8% ({use_label})',
                    'xml_id': f'{prefix}tax_iva_8',
                    'amount': 8.0,
                    'type_tax_use': use,
                    'description': f'IVA 8% {use_label}',
                    'tax_group_id': created_tax_groups['tax_group_sp_ivar_8'].id,
                    'simplit_tax_type': f'{prefix}iva_8',
                },
                {
                    'name': f'Retención IVA 75% ({use_label})',
                    'xml_id': f'{prefix}tax_ret_75',
                    'amount': -12.0,
                    'type_tax_use': use,
                    'description': f'Retención 75% sobre IVA 16% ({use_label})',
                    'tax_group_id': created_tax_groups['tax_group_sp_ret_75'].id,
                    'is_retention': True,
                    'simplit_tax_type': f'{prefix}ret_75',
                },
                {
                    'name': f'Retención IVA 100% ({use_label})',
                    'xml_id': f'{prefix}tax_ret_100',
                    'amount': -16.0,
                    'type_tax_use': use,
                    'description': f'Retención 100% sobre IVA 16% ({use_label})',
                    'tax_group_id': created_tax_groups['tax_group_sp_ret_100'].id,
                    'is_retention': True,
                    'simplit_tax_type': f'{prefix}ret_100',
                },
                {
                    'name': f'Retención IVA 8% 75% ({use_label})',
                    'xml_id': f'{prefix}tax_ret_ivar_75',
                    'amount': -6.0,
                    'type_tax_use': use,
                    'description': f'Retención 75% sobre IVA 8% ({use_label})',
                    'tax_group_id': created_tax_groups['tax_group_sp_ret_75'].id,
                    'is_retention': True,
                    'simplit_tax_type': f'{prefix}ret_ivar_75',
                },
                {
                    'name': f'Retención IVA 8% 100% ({use_label})',
                    'xml_id': f'{prefix}tax_ret_ivar_100',
                    'amount': -8.0,
                    'type_tax_use': use,
                    'description': f'Retención 100% sobre IVA 8% ({use_label})',
                    'tax_group_id': created_tax_groups['tax_group_sp_ret_100'].id,
                    'is_retention': True,
                    'simplit_tax_type': f'{prefix}ret_ivar_100',
                },
            ]

        created_taxes = {}
        for tax_data in taxes_to_create:
            tax = AccountTax.search([
                ('company_id', '=', company.id),
                ('simplit_tax_type', '=', tax_data['simplit_tax_type'])
            ], limit=1)
            
            # Compatibilidad: Buscar antiguos sin prefijo si es purchase
            if not tax and 'purchase_' in tax_data['simplit_tax_type']:
                old_type = tax_data['simplit_tax_type'].replace('purchase_', '')
                tax = AccountTax.search([
                    ('company_id', '=', company.id),
                    ('simplit_tax_type', '=', old_type)
                ], limit=1)
            if not tax:
                tax = AccountTax.search([
                    ('company_id', '=', company.id),
                    ('type_tax_use', '=', tax_data['type_tax_use']),
                    ('name', '=', tax_data['name']),
                ], limit=1)

            vals = {
                'name': tax_data['name'],
                'amount': tax_data['amount'],
                'amount_type': 'percent',
                'type_tax_use': tax_data['type_tax_use'],
                'company_id': company.id,
                'description': tax_data['description'],
                'is_simplit_tax': True,
                'is_retention': tax_data.get('is_retention', False),
                'simplit_tax_type': tax_data['simplit_tax_type'],
                'tax_group_id': tax_data['tax_group_id'],
            }

            if not tax:
                tax = AccountTax.create(vals)
            else:
                tax.write(vals)

            xml_full_id = f"l10n_ve_simplit_fiscal.{tax_data['xml_id']}_{comp_suffix}"
            if not self.env.ref(xml_full_id, raise_if_not_found=False):
                IrModelData.create({
                    'name': f"{tax_data['xml_id']}_{comp_suffix}",
                    'model': 'account.tax',
                    'module': 'l10n_ve_simplit_fiscal',
                    'res_id': tax.id,
                    'noupdate': True,
                })
            created_taxes[tax_data['xml_id']] = tax

        # ========== PARTE C: Crear Grupos Combo (Compras y Ventas) ==========
        
        combo_groups_data = []
        for use in ['purchase', 'sale']:
            use_label = 'Compras' if use == 'purchase' else 'Ventas'
            prefix = 'purchase_' if use == 'purchase' else 'sale_'
            
            combo_groups_data += [
                {
                    'name': f'IVA 16% + Retención 75% ({use_label})',
                    'xml_id': f'{prefix}group_iva_ret_75',
                    'description': f'IVA 16% + Retención 75% ({use_label})',
                    'children': [f'{prefix}tax_iva_16', f'{prefix}tax_ret_75'],
                    'simplit_tax_type': f'{prefix}group_iva_ret_75',
                    'type_tax_use': use,
                },
                {
                    'name': f'IVA 16% + Retención 100% ({use_label})',
                    'xml_id': f'{prefix}group_iva_ret_100',
                    'description': f'IVA 16% + Retención 100% ({use_label})',
                    'children': [f'{prefix}tax_iva_16', f'{prefix}tax_ret_100'],
                    'simplit_tax_type': f'{prefix}group_iva_ret_100',
                    'type_tax_use': use,
                },
                {
                    'name': f'IVA 8% + Retención 75% ({use_label})',
                    'xml_id': f'{prefix}group_ivar_ret_75',
                    'description': f'IVA 8% + Retención 75% ({use_label})',
                    'children': [f'{prefix}tax_iva_8', f'{prefix}tax_ret_ivar_75'],
                    'simplit_tax_type': f'{prefix}group_ivar_ret_75',
                    'type_tax_use': use,
                },
                {
                    'name': f'IVA 8% + Retención 100% ({use_label})',
                    'xml_id': f'{prefix}group_ivar_ret_100',
                    'description': f'IVA 8% + Retención 100% ({use_label})',
                    'children': [f'{prefix}tax_iva_8', f'{prefix}tax_ret_ivar_100'],
                    'simplit_tax_type': f'{prefix}group_ivar_ret_100',
                    'type_tax_use': use,
                },
            ]

        for g_data in combo_groups_data:
            children_ids = [created_taxes[child_xml_id].id for child_xml_id in g_data['children']]
            
            tax_group = AccountTax.search([
                ('company_id', '=', company.id),
                ('simplit_tax_type', '=', g_data['simplit_tax_type'])
            ], limit=1)

            # Compatibilidad: Buscar antiguos sin prefijo si es purchase
            if not tax_group and 'purchase_' in g_data['simplit_tax_type']:
                old_type = g_data['simplit_tax_type'].replace('purchase_', '')
                tax_group = AccountTax.search([
                    ('company_id', '=', company.id),
                    ('simplit_tax_type', '=', old_type)
                ], limit=1)
            if not tax_group:
                tax_group = AccountTax.search([
                    ('company_id', '=', company.id),
                    ('type_tax_use', '=', g_data['type_tax_use']),
                    ('name', '=', g_data['name']),
                ], limit=1)

            vals = {
                'name': g_data['name'],
                'amount_type': 'group',
                'type_tax_use': g_data['type_tax_use'],
                'company_id': company.id,
                'description': g_data['description'],
                'children_tax_ids': [(6, 0, children_ids)],
                'is_simplit_tax': True,
                'simplit_tax_type': g_data['simplit_tax_type'],
            }

            if not tax_group:
                tax_group = AccountTax.create(vals)
            else:
                tax_group.write(vals)

            xml_full_id = f"l10n_ve_simplit_fiscal.{g_data['xml_id']}_{comp_suffix}"
            if not self.env.ref(xml_full_id, raise_if_not_found=False):
                IrModelData.create({
                    'name': f"{g_data['xml_id']}_{comp_suffix}",
                    'model': 'account.tax',
                    'module': 'l10n_ve_simplit_fiscal',
                    'res_id': tax_group.id,
                    'noupdate': True,
                })

        self.write({'taxes_generated': True})

        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }

    def action_configure(self):
        """
        Cambia el estado a 'configured'.
        """
        self.ensure_one()
        self.write({'state': 'configured'})
    
    def action_activate(self):
        """
        Cambia el estado a 'active'.
        """
        self.ensure_one()
        if not self.taxes_generated:
            raise UserError(
                _('Debe generar los impuestos antes de activar la configuración.')
            )
        self.write({'state': 'active'})
    
    def action_reset_to_draft(self):
        """
        Vuelve el estado a 'draft'.
        """
        self.ensure_one()
        self.write({'state': 'draft'})
    
    def action_configure_sequence(self):
        """
        Abre el wizard para configurar el correlativo de retenciones IVA.
        """
        self.ensure_one()
        
        return {
            'name': _('Configurar Correlativo de Retenciones IVA'),
            'type': 'ir.actions.act_window',
            'res_model': 'simplitfiscal.sequence.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_config_id': self.id,
                'default_sequence_number': self.withholding_sequence_number,
            },
        }

    def action_configure_islr_sequence(self):
        """
        Abre el wizard para configurar el correlativo de retenciones ISLR.
        """
        self.ensure_one()
        
        return {
            'name': _('Configurar Correlativo de Retenciones ISLR'),
            'type': 'ir.actions.act_window',
            'res_model': 'simplitfiscal.islr.sequence.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_config_id': self.id,
                'default_sequence_number': self.islr_withholding_sequence_number,
            },
        }
