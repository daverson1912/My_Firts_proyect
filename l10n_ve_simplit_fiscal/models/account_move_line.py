# -*- coding: utf-8 -*-

from odoo import api, fields, models
import logging

_logger = logging.getLogger(__name__)


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    l10n_ve_islr_amount_line = fields.Monetary(
        string='Retención ISLR Línea',
        help='Monto de retención ISLR para esta línea de factura.',
    )

    l10n_ve_islr_subject_amount = fields.Monetary(
        string='Monto Sujeto ISLR',
        help='Monto sobre el cual se aplica la retención de ISLR.',
    )

    l10n_ve_islr_subject_percentage = fields.Float(
        string='% Base Sujeta ISLR',
        help='Porcentaje aplicado a la base imponible para obtener el monto sujeto.',
    )

    l10n_ve_islr_fiscal_code = fields.Char(
        string='Código Fiscal ISLR',
        help='Código fiscal del concepto de retención.',
    )

    l10n_ve_islr_retention_percentage = fields.Float(
        string='% Retención ISLR',
        help='Porcentaje de retención aplicado.',
    )

    l10n_ve_islr_subtrahend = fields.Monetary(
        string='Sustraendo ISLR',
        help='Monto de sustraendo aplicado en la retención.',
    )

    l10n_ve_islr_subject_amount_display = fields.Char(
        string='Monto Sujeto ISLR',
        compute='_compute_l10n_ve_islr_subject_amount_display',
        help='Monto sujeto con el porcentaje aplicado entre paréntesis.',
    )

    @api.depends('l10n_ve_islr_subject_amount', 'l10n_ve_islr_subject_percentage', 'currency_id')
    def _compute_l10n_ve_islr_subject_amount_display(self):
        for line in self:
            if not line.l10n_ve_islr_fiscal_code:
                line.l10n_ve_islr_subject_amount_display = ""
                continue
            
            amount = line.l10n_ve_islr_subject_amount
            symbol = line.currency_id.symbol or ''
            
            percentage = line.l10n_ve_islr_subject_percentage
            formatted_amount = "{:,.2f}".format(amount).replace(",", "X").replace(".", ",").replace("X", ".")
            line.l10n_ve_islr_subject_amount_display = f"{formatted_amount} {symbol} ({int(percentage) if percentage % 1 == 0 else percentage}%)"

    l10n_ve_islr_base_retention_amount = fields.Monetary(
        string='Cálculo Base Retención ISLR',
        help='Monto base de retención (sin sustraendo) devuelto por el API.',
    )

    l10n_ve_islr_retention_calculation_display = fields.Char(
        string='Calc. Imp. Ret',
        compute='_compute_l10n_ve_islr_retention_calculation_display',
        help='Monto de cálculo base con el porcentaje de retención entre paréntesis.',
    )

    @api.depends('l10n_ve_islr_base_retention_amount', 'l10n_ve_islr_retention_percentage', 'currency_id')
    def _compute_l10n_ve_islr_retention_calculation_display(self):
        for line in self:
            if not line.l10n_ve_islr_fiscal_code:
                line.l10n_ve_islr_retention_calculation_display = ""
                continue
            
            amount = line.l10n_ve_islr_base_retention_amount
            symbol = line.currency_id.symbol or ''
            
            percentage = line.l10n_ve_islr_retention_percentage
            formatted_amount = "{:,.2f}".format(amount).replace(",", "X").replace(".", ",").replace("X", ".")
            line.l10n_ve_islr_retention_calculation_display = f"{formatted_amount} {symbol} ({int(percentage) if percentage % 1 == 0 else percentage}%)"

    def _should_apply_fiscal_replacement(self):
        """
        Determina si se debe aplicar el reemplazo de impuestos fiscales.
        
        Returns:
            bool: True si se cumplen todas las condiciones
        """
        # Solo procesar si hay un move_id asociado
        if not self.move_id:
            _logger.debug("[FISCAL] No hay move_id asociado, saltando reemplazo")
            return False
        
        # Solo procesar facturas de compra o venta
        if self.move_id.move_type not in ('in_invoice', 'out_invoice'):
            _logger.debug(f"[FISCAL] Tipo de factura {self.move_id.move_type} no es procesable para reemplazo")
            return False
        
        # Verificar que la empresa sea venezolana
        company = self.move_id.company_id or self.env.company
        if not company.country_id:
            _logger.warning(f"[FISCAL] La empresa {company.name} no tiene país configurado")
            return False
        
        if company.country_id.code != 'VE':
            _logger.warning(f"[FISCAL] La empresa {company.name} no es de Venezuela (país: {company.country_id.name}). El módulo fiscal solo funciona con empresas venezolanas.")
            return False
        
        # Obtener configuración de Simplit Fiscal
        config = self.env['simplitfiscal.config'].search([
            ('company_id', '=', company.id)
        ], limit=1)
        
        if not config:
            _logger.warning(f"[FISCAL] No se encontró configuración de Simplit Fiscal para la empresa {company.name}")
            return False
        
        # Lógica diferenciada por tipo de factura
        if self.move_id.move_type == 'in_invoice':
            # COMPRAS: Nosotros retenemos al proveedor
            if not config.is_withholding_agent:
                _logger.warning(f"[FISCAL] La empresa {company.name} no está marcada como Agente de Retención")
                return False
                
            if not self.move_id.partner_id:
                return False
                
            retention_type = self.move_id.partner_id.l10n_ve_supplier_retention_type
            if not retention_type:
                _logger.info(f"[FISCAL] El proveedor {self.move_id.partner_id.name} no tiene tipo de retención configurado")
                return False
        else:
            # VENTAS: El cliente nos retiene a nosotros
            # Primero: Nosotros debemos ser sujetos de retención (Agentes en Venezuela)
            if not config.is_withholding_agent:
                _logger.info(f"[FISCAL] Nuestra empresa no es Agente de Retención, no aplica retención de IVA en ventas")
                return False
                
            # Segundo: El cliente debe ser Agente de Retención
            if not self.move_id.partner_id or not self.move_id.partner_id.l10n_ve_customer_iva_agent:
                _logger.info(f"[FISCAL] El cliente {self.move_id.partner_id.name} no es Agente de Retención")
                return False
                
            # Tercero: Debe haber un porcentaje definido en la configuración global
            if not config.default_retention_type:
                _logger.warning(f"[FISCAL] No se ha definido el Porcentaje de Retención por Defecto en la configuración fiscal")
                return False

        return True
    
    def _apply_fiscal_tax_replacement(self, from_onchange=False):
        """
        Aplica el reemplazo de impuestos estándar por grupos combo.
        Este método es llamado tanto por onchange como por create/write.
        
        Args:
            from_onchange: True si se llama desde onchange, False desde create/write
        """
        self.ensure_one()
        
        # Evitar bucle infinito si ya estamos en un reemplazo fiscal
        if self.env.context.get('skip_fiscal_replacement'):
            return
        
        if not self._should_apply_fiscal_replacement():
            return
        
        # Determinar el porcentaje de retención
        if self.move_id.move_type == 'in_invoice':
            retention_type = self.move_id.partner_id.l10n_ve_supplier_retention_type
        else:
            # Para ventas usamos la configuración global de la empresa
            company = self.move_id.company_id or self.env.company
            config = self.env['simplitfiscal.config'].search([('company_id', '=', company.id)], limit=1)
            retention_type = config.default_retention_type
        
        # Procesar cada impuesto en la línea
        new_taxes = []
        should_replace = False
        
        for tax in self.tax_ids:
            # NO tocar retenciones ni grupos combo ya aplicados
            # Solo reemplazar IVA base (16% o 8%)
            if hasattr(tax, 'is_simplit_tax') and tax.is_simplit_tax:
                # Si es una retención (negativo) o grupo combo, mantener
                if tax.amount < 0 or tax.amount_type == 'group':
                    new_taxes.append(tax.id)
                    continue
                
                # Si es IVA base 16% o 8%, SÍ reemplazar por grupo combo
                # (Continúa a la detección abajo)
            
            # Detectar IVA 16% (estándar o SP)
            if tax.amount == 16.0 and tax.type_tax_use in ('sale', 'purchase', 'none'):
                should_replace = True
                
                # Definir el tipo técnico que buscamos y el uso
                use = 'purchase' if self.move_id.move_type == 'in_invoice' else 'sale'
                prefix = 'purchase_' if use == 'purchase' else 'sale_'
                target_simplit_type = f"{prefix}group_iva_ret_75" if retention_type == '75' else f"{prefix}group_iva_ret_100"
                
                # Búsqueda robusta por tipo técnico y compañía
                combo_tax = self.env['account.tax'].search([
                    ('company_id', '=', self.move_id.company_id.id),
                    ('simplit_tax_type', '=', target_simplit_type),
                    ('type_tax_use', '=', use)
                ], limit=1)
                
                if combo_tax:
                    new_taxes.append(combo_tax.id)
                    _logger.info(f"[FISCAL] Reemplazado {tax.name} por {combo_tax.name} (Tipo: {target_simplit_type})")
                else:
                    # Falback: Si no se encuentra el combo (ej: migración), mantener el original
                    new_taxes.append(tax.id)
                    _logger.warning(f"[FISCAL] No se encontró grupo combo tipo '{target_simplit_type}' para compañía {self.move_id.company_id.name}")
            
            # Detectar IVA 8% reducido (estándar o SP)
            elif tax.amount == 8.0 and tax.type_tax_use in ('sale', 'purchase', 'none'):
                should_replace = True
                
                use = 'purchase' if self.move_id.move_type == 'in_invoice' else 'sale'
                prefix = 'purchase_' if use == 'purchase' else 'sale_'
                target_simplit_type = f"{prefix}group_ivar_ret_75" if retention_type == '75' else f"{prefix}group_ivar_ret_100"
                
                combo_tax = self.env['account.tax'].search([
                    ('company_id', '=', self.move_id.company_id.id),
                    ('simplit_tax_type', '=', target_simplit_type),
                    ('type_tax_use', '=', use)
                ], limit=1)

                if combo_tax:
                    new_taxes.append(combo_tax.id)
                    _logger.info(f"[FISCAL] Reemplazado {tax.name} por {combo_tax.name} (Tipo: {target_simplit_type})")
                else:
                    new_taxes.append(tax.id)
                    _logger.warning(f"[FISCAL] No se encontró grupo combo tipo '{target_simplit_type}' para compañía {self.move_id.company_id.name}")
            
            else:
                # Otros impuestos se mantienen sin cambios
                new_taxes.append(tax.id)
        
        # Aplicar el reemplazo si hubo cambios
        if should_replace and new_taxes:
            if from_onchange:
                # En onchange, usar asignación directa (registro no está en BD)
                self.tax_ids = [(6, 0, new_taxes)]
            else:
                # En create/write, usar write() con contexto para evitar bucle
                self.with_context(skip_fiscal_replacement=True).write({
                    'tax_ids': [(6, 0, new_taxes)]
                })
            _logger.info(f"[FISCAL] Impuestos reemplazados exitosamente")
    
    @api.onchange('product_id', 'tax_ids')
    def _onchange_product_id_l10n_ve_fiscal(self):
        """
        Reemplaza automáticamente los impuestos estándar por grupos combo
        cuando se trata de una factura de compra y el proveedor tiene
        configurado un tipo de retención.
        
        Este método se ejecuta cuando el usuario selecciona un producto o un impuesto manualmente.
        """
        self._apply_fiscal_tax_replacement(from_onchange=True)
    
    @api.model_create_multi
    def create(self, vals_list):
        """
        Override del create para aplicar el reemplazo de impuestos
        cuando las líneas se crean programáticamente (ej: desde órdenes de compra).
        """
        lines = super().create(vals_list)
        
        # Aplicar reemplazo de impuestos a cada línea creada
        for line in lines:
            if line.display_type not in ('line_section', 'line_note'):
                try:
                    line._apply_fiscal_tax_replacement()
                except Exception as e:
                    _logger.error(f"[FISCAL] Error al aplicar reemplazo de impuestos en create: {e}")
        
        return lines
    
    def write(self, vals):
        """
        Override del write para aplicar el reemplazo de impuestos
        cuando se modifican las líneas.
        """
        result = super().write(vals)
        
        # NO aplicar si venimos de nuestro propio reemplazo
        if self.env.context.get('skip_fiscal_replacement'):
            return result
        
        # Si se modificó el producto o los impuestos, aplicar reemplazo
        if 'product_id' in vals or 'tax_ids' in vals:
            for line in self:
                if line.display_type not in ('line_section', 'line_note'):
                    try:
                        line._apply_fiscal_tax_replacement()
                    except Exception as e:
                        _logger.error(f"[FISCAL] Error al aplicar reemplazo de impuestos en write: {e}")
        
        return result
