from odoo import models, fields, api

class AccountReport(models.Model):
    _inherit = 'account.report'

    l10n_ve_ta_multicurrency_allow_multicurrency = fields.Boolean(
        string="Allow Multicurrency View", 
        default=False,
        help="EN: If active, it will allow selecting a different currency using the top filter. | ES: Si se activa, permitirá seleccionar una moneda distinta usando el filtro superior."
    )

    def get_options(self, previous_options):
        """
        EN: Inject multicurrency options (available currencies) into the report controller.
        ES: Inyecta las opciones multidivisa (monedas disponibles) en el controlador del reporte.
        """
        options = super().get_options(previous_options)
        
        company = self.env.company
        base_currency = company.currency_id

        # Locate remaining currencies (excluding the base to avoid duplicating options)
        currencies = self.env['res.currency'].search([
            ('active', '=', True),
            ('id', '!=', base_currency.id)
        ])
        
        # Inject default currency name for the frontend
        options['multicurrency_base_currency_name'] = base_currency.name
        
        options['available_multicurrency_currencies'] = [
            {'id': c.id, 'name': c.name, 'symbol': c.symbol} for c in currencies
        ]
        
        if previous_options and 'multicurrency_currency_id' in previous_options:
            options['multicurrency_currency_id'] = previous_options['multicurrency_currency_id']
        else:
            options['multicurrency_currency_id'] = False

        return options

    def _get_lines(self, options, all_column_groups_expression_totals=None, warnings=None, **kwargs):
        """
        EN: Intercept report lines to apply on-the-fly currency conversion if a multicurrency filter is active.
        ES: Intercepta las líneas del reporte para aplicar conversión de moneda al vuelo si el filtro multidivisa está activo.
        """
        lines = super()._get_lines(options, all_column_groups_expression_totals=all_column_groups_expression_totals, warnings=warnings, **kwargs)

        target_currency_id = options.get('multicurrency_currency_id')
        if not target_currency_id:
            return lines

        target_currency = self.env['res.currency'].browse(target_currency_id)
        if not target_currency.exists():
            return lines

        # Locate base currency (Company Currency)
        company = self.env.company
        base_currency = company.currency_id

        # If no conversion needed, return intact
        if base_currency.id == target_currency.id:
            return lines

        date_to_str = options.get('date', {}).get('date_to')
        date_to = fields.Date.from_string(date_to_str) if date_to_str else fields.Date.context_today(self)

        # Extract the RAW rate (without native rounding) same as in account_move
        raw_rate = self.env['res.currency']._get_conversion_rate(
            base_currency, target_currency, company, date_to
        )

        # Iterate report lines and CLONE dictionaries.
        # It is CRITICAL to make copies (.copy()) because Odoo caches the original dicts.
        # Mutating them in-place would cause the cached report to multiply incorrectly.
        new_lines = []
        for line in lines:
            new_line = line.copy()
            if 'columns' in line:
                new_cols = []
                for col in line['columns']:
                    new_col = col.copy()
                    val = new_col.get('no_format')
                    if val is not None and isinstance(val, (int, float)):
                        converted_value = val * raw_rate
                        new_col['no_format'] = converted_value
                        
                        # Format for visual display
                        new_col['name'] = f"{target_currency.symbol} " + "{:,.4f}".format(converted_value).replace(',', 'X').replace('.', ',').replace('X', '.')
                    new_cols.append(new_col)
                new_line['columns'] = new_cols
            new_lines.append(new_line)

        return new_lines
