from odoo import models, fields, api

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    l10n_ve_ta_multicurrency_fiscal_id = fields.Many2one(
        'res.currency',
        compute='_compute_l10n_ve_ta_multicurrency_fiscal_id',
        string="Fiscal Currency"
    )
    
    l10n_ve_ta_multicurrency_list_price_fiscal = fields.Monetary(
        string='Total Ref.',
        compute='_compute_l10n_ve_ta_multicurrency_list_price_fiscal',
        currency_field='l10n_ve_ta_multicurrency_fiscal_id',
        store=False,
    )

    def _l10n_ve_ta_multicurrency_get_ref_currency(self, product_currency):
        """
        Lógica Bimonetaria Estricta Dinámica:
        El badge siempre debe mostrar la moneda OPUESTA a la moneda base de la compañía.
        """
        company_currency = self.env.company.currency_id
        if not company_currency:
            return False

        # Buscar fiscal: por flag (company_dependent) o dinámicamente
        fiscal = self.env['res.currency'].search([('l10n_ve_ta_multicurrency_is_fiscal', '=', True)], limit=1)
        if not fiscal:
            fiscal = self.env['res.currency'].search([
                ('id', '!=', company_currency.id),
                ('active', '=', True)
            ], order='name asc', limit=1)

        if not fiscal:
            return False

        # Siempre la moneda opuesta a la de la compañía
        if product_currency == company_currency:
            return fiscal
        else:
            return company_currency

    def _l10n_ve_ta_multicurrency_get_source_currency(self, product_currency):
        """
        Para la conversión de precios, si el producto está en una variante vieja de Bolívar
        (VEF, VEB), usamos la fiscal actual (VES) como fuente de tasa.
        """
        company_currency = self.env.company.currency_id
        fiscal = self.env['res.currency'].search([('l10n_ve_ta_multicurrency_is_fiscal', '=', True)], limit=1)
        if not fiscal:
            fiscal = self.env['res.currency'].search([
                ('id', '!=', company_currency.id),
                ('active', '=', True)
            ], order='name asc', limit=1) if company_currency else None
        if fiscal and product_currency != fiscal:
            if product_currency.name and fiscal.name and product_currency.name[:2] == fiscal.name[:2]:
                return fiscal
        return product_currency

    @api.depends_context('company', 'product_catalog_order_id', 'product_catalog_order_model')
    def _compute_l10n_ve_ta_multicurrency_fiscal_id(self):
        """
        EN: Compute the reference currency (always the opposite of the product's currency).
        ES: Calcula la moneda de referencia (siempre la opuesta a la del producto).
        """
        for product in self:
            ref = self._l10n_ve_ta_multicurrency_get_ref_currency(product.currency_id or self.env.company.currency_id)
            product.l10n_ve_ta_multicurrency_fiscal_id = ref.id if ref else False

    @api.depends('list_price', 'currency_id')
    @api.depends_context('company')
    def _compute_l10n_ve_ta_multicurrency_list_price_fiscal(self):
        """
        EN: Compute the product sales price in the reference currency.
        ES: Calcula el precio de venta del producto en la moneda de referencia.
        """
        for product in self:
            target_curr = product.l10n_ve_ta_multicurrency_fiscal_id
            if not target_curr or not product.currency_id:
                product.l10n_ve_ta_multicurrency_list_price_fiscal = 0.0
                continue
            
            source = self._l10n_ve_ta_multicurrency_get_source_currency(product.currency_id)
            rate = self.env['res.currency']._get_conversion_rate(
                source, target_curr, self.env.company, fields.Date.context_today(self)
            )
            product.l10n_ve_ta_multicurrency_list_price_fiscal = product.list_price * rate


class ProductProduct(models.Model):
    _inherit = 'product.product'

    l10n_ve_ta_multicurrency_fiscal_id = fields.Many2one(
        'res.currency',
        compute='_compute_l10n_ve_ta_multicurrency_fiscal_id',
        string="Fiscal Currency"
    )
    
    l10n_ve_ta_multicurrency_list_price_fiscal = fields.Monetary(
        string='Total Ref.',
        compute='_compute_l10n_ve_ta_multicurrency_list_price_fiscal',
        currency_field='l10n_ve_ta_multicurrency_fiscal_id',
        store=False,
    )

    @api.depends_context('company', 'product_catalog_order_id', 'product_catalog_order_model')
    def _compute_l10n_ve_ta_multicurrency_fiscal_id(self):
        """
        Calcula la moneda de referencia para variantes.
        """
        for product in self:
            ref = self.env['product.template']._l10n_ve_ta_multicurrency_get_ref_currency(
                product.currency_id or self.env.company.currency_id
            )
            product.l10n_ve_ta_multicurrency_fiscal_id = ref.id if ref else False

    @api.depends('lst_price', 'currency_id')
    @api.depends_context('company', 'product_catalog_order_id', 'product_catalog_order_model')
    def _compute_l10n_ve_ta_multicurrency_list_price_fiscal(self):
        """
        EN: Compute the variant price in the reference currency.
        ES: Calcula el precio de la variante en la moneda de referencia.
        """
        for product in self:
            target_curr = product.l10n_ve_ta_multicurrency_fiscal_id
            if not target_curr or not product.currency_id:
                product.l10n_ve_ta_multicurrency_list_price_fiscal = 0.0
                continue
            
            base_price = product.lst_price
            date = fields.Date.context_today(self)
            
            order_model = self.env.context.get('product_catalog_order_model')
            order_id = self.env.context.get('product_catalog_order_id')
            
            if order_model and order_id:
                try:
                    order = self.env[order_model].browse(order_id)
                    if order.exists() and hasattr(order, '_get_product_price_and_data'):
                        price_data = order._get_product_price_and_data(product)
                        base_price = price_data.get('price', base_price)
                        date = getattr(order, 'invoice_date', getattr(order, 'date_order', getattr(order, 'date', date))) or date
                except Exception:
                    pass

            source = self.env['product.template']._l10n_ve_ta_multicurrency_get_source_currency(product.currency_id)
            rate = self.env['res.currency']._get_conversion_rate(
                source, target_curr, self.env.company, date
            )
            product.l10n_ve_ta_multicurrency_list_price_fiscal = base_price * rate
