from odoo import api, fields, models

DEFAULT_FIELD_MAPS = [
    # --- Emisor ---
    {
        'sequence': 10,
        'api_field_key': 'issuer.address',
        'api_field_label': 'Dirección del Emisor',
        'api_field_description': (
            'Dirección fiscal de la empresa emisora. '
            'Concatena Calle 1 y Calle 2 de la compañía en Odoo.'
        ),
        'api_field_required': False,
        'source_model': 'move',
        'odoo_expr': 'company_id.street + company_id.street2',
    },
    {
        'sequence': 20,
        'api_field_key': 'issuer.phone',
        'api_field_label': 'Teléfono del Emisor',
        'api_field_description': (
            'Número de teléfono de la empresa emisora registrado en Odoo.'
        ),
        'api_field_required': False,
        'source_model': 'move',
        'odoo_expr': 'company_id.phone',
    },
    # --- Receptor ---
    {
        'sequence': 30,
        'api_field_key': 'receiver.taxId',
        'api_field_label': 'RIF del Receptor',
        'api_field_description': (
            'Número de identificación fiscal del cliente receptor. '
            'Debe tener el formato V-XXXXXXXX o J-XXXXXXXX.'
        ),
        'api_field_required': True,
        'source_model': 'move',
        'odoo_expr': 'partner_id.vat',
    },
    {
        'sequence': 40,
        'api_field_key': 'receiver.name',
        'api_field_label': 'Nombre del Receptor',
        'api_field_description': (
            'Nombre o razón social del cliente que recibe la factura.'
        ),
        'api_field_required': True,
        'source_model': 'move',
        'odoo_expr': 'partner_id.name',
    },
    {
        'sequence': 50,
        'api_field_key': 'receiver.address',
        'api_field_label': 'Dirección del Receptor',
        'api_field_description': (
            'Dirección fiscal del cliente receptor. '
            'Concatena Calle 1 y Calle 2 del contacto en Odoo.'
        ),
        'api_field_required': False,
        'source_model': 'move',
        'odoo_expr': 'partner_id.street + partner_id.street2',
    },
    {
        'sequence': 60,
        'api_field_key': 'receiver.phone',
        'api_field_label': 'Teléfono del Receptor',
        'api_field_description': (
            'Número de teléfono del cliente receptor.'
        ),
        'api_field_required': False,
        'source_model': 'move',
        'odoo_expr': 'partner_id.phone',
    },
    {
        'sequence': 70,
        'api_field_key': 'receiver.email',
        'api_field_label': 'Email del Receptor',
        'api_field_description': (
            'Correo electrónico del cliente receptor.'
        ),
        'api_field_required': False,
        'source_model': 'move',
        'odoo_expr': 'partner_id.email',
    },
    # --- Ítems ---
    {
        'sequence': 80,
        'api_field_key': 'items[].description',
        'api_field_label': 'Descripción del Ítem',
        'api_field_description': (
            'Descripción de cada línea de la factura. '
            'Usa "name" para la descripción transaccional completa (con comentarios del usuario). '
            'El prefijo [REF] que agrega Odoo se elimina automáticamente.'
        ),
        'api_field_required': True,
        'source_model': 'line',
        'odoo_expr': 'name',
    },
    {
        'sequence': 82,
        'api_field_key': 'items[].unitPrice',
        'api_field_label': 'Precio Unitario (Línea)',
        'api_field_description': (
            'Precio unitario antes de descuento. Por defecto: price_unit (en moneda de la factura). '
            'Para multimoneda, puede apuntar a un campo calculado en la moneda deseada.'
        ),
        'api_field_required': True,
        'source_model': 'line',
        'odoo_expr': 'price_unit',
    },
    {
        'sequence': 84,
        'api_field_key': 'items[].subtotal',
        'api_field_label': 'Subtotal (Línea)',
        'api_field_description': (
            'Subtotal de la línea sin impuestos. Por defecto: price_subtotal (en moneda de la factura). '
            'Para multimoneda, apuntar al campo equivalente en la moneda deseada.'
        ),
        'api_field_required': True,
        'source_model': 'line',
        'odoo_expr': 'price_subtotal',
    },
    {
        'sequence': 86,
        'api_field_key': 'items[].taxAmount',
        'api_field_label': 'Monto de Impuesto (Línea)',
        'api_field_description': (
            'Impuesto de la línea (price_total - price_subtotal). '
            'Dejar vacío para usar el cálculo automático. '
            'Para multimoneda, apuntar al campo equivalente en la moneda deseada.'
        ),
        'api_field_required': True,
        'source_model': 'line',
        'odoo_expr': '',
    },
    {
        'sequence': 90,
        'api_field_key': 'items[].goodOrService',
        'api_field_label': 'Bien o Servicio',
        'api_field_description': (
            'Indica si la línea es un bien (1) o un servicio (2). '
            'product_id.detailed_type: consu/product → 1, service → 2.'
        ),
        'api_field_required': True,
        'source_model': 'line',
        'odoo_expr': 'product_id.detailed_type',
    },
    {
        'sequence': 100,
        'api_field_key': 'items[].unitMeasure',
        'api_field_label': 'Unidad de Medida',
        'api_field_description': (
            'Código de la unidad de medida del ítem según el estándar del proveedor '
            '(ej: NIU para unidades). '
            'product_id.uom_id.name obtiene el nombre de la unidad del producto.'
        ),
        'api_field_required': False,
        'source_model': 'line',
        'odoo_expr': '',
        'default_value': 'UND',
    },
    {
        'sequence': 102,
        'api_field_key': 'items[].ciiu',
        'api_field_label': 'Código CIIU',
        'api_field_description': (
            'Código de Clasificación Industrial Internacional Uniforme (CIIU) '
            'asociado al producto o servicio. Requerido por el SENIAT.'
        ),
        'api_field_required': False,
        'source_model': 'line',
        'odoo_expr': '',
    },
    {
        'sequence': 104,
        'api_field_key': 'items[].sku',
        'api_field_label': 'SKU / Referencia Interna',
        'api_field_description': (
            'Código del producto. '
            'product_id.default_code obtiene la referencia interna del producto.'
        ),
        'api_field_required': False,
        'source_model': 'line',
        'odoo_expr': 'product_id.default_code',
    },
    {
        'sequence': 106,
        'api_field_key': 'items[].bonusAmount',
        'api_field_label': 'Monto de Bonificación',
        'api_field_description': (
            'Monto monetario de bonificación aplicado a la línea. '
            'Dejar vacío o en 0 si no aplica.'
        ),
        'api_field_required': False,
        'source_model': 'line',
        'odoo_expr': '',
        'default_value': '0',
    },
    {
        'sequence': 107,
        'api_field_key': 'items[].bonusDescription',
        'api_field_label': 'Descripción de Bonificación',
        'api_field_description': (
            'Texto descriptivo de la bonificación aplicada (ej: Promoción aniversario). '
            'Solo se envía si hay bonificación.'
        ),
        'api_field_required': False,
        'source_model': 'line',
        'odoo_expr': '',
    },
    {
        'sequence': 108,
        'api_field_key': 'items[].surchargeAmount',
        'api_field_label': 'Monto de Recargo',
        'api_field_description': (
            'Monto monetario de recargo o cargo adicional aplicado a la línea. '
            'Dejar vacío o en 0 si no aplica.'
        ),
        'api_field_required': False,
        'source_model': 'line',
        'odoo_expr': '',
        'default_value': '0',
    },
    # --- Totales ---
    {
        'sequence': 109,
        'api_field_key': 'totals.subtotal',
        'api_field_label': 'Subtotal Bruto (Total)',
        'api_field_description': (
            'Suma bruta (precio × cantidad) antes de descuentos. '
            'Dejar vacío para calcular automáticamente desde las líneas. '
            'Para multimoneda, apuntar a un campo de account.move en la moneda deseada.'
        ),
        'api_field_required': True,
        'source_model': 'move',
        'odoo_expr': '',
    },
    {
        'sequence': 111,
        'api_field_key': 'totals.taxBase',
        'api_field_label': 'Base Imponible (Total)',
        'api_field_description': (
            'Base imponible total (sin impuestos). Por defecto: amount_untaxed. '
            'Para multimoneda: cambiar a amount_untaxed_signed u otro campo '
            'en la moneda deseada.'
        ),
        'api_field_required': True,
        'source_model': 'move',
        'odoo_expr': 'amount_untaxed',
    },
    {
        'sequence': 113,
        'api_field_key': 'totals.taxAmount',
        'api_field_label': 'Monto de Impuesto (Total)',
        'api_field_description': (
            'Monto total de IVA. Por defecto: amount_tax. '
            'Para multimoneda: cambiar al campo equivalente en la moneda deseada.'
        ),
        'api_field_required': True,
        'source_model': 'move',
        'odoo_expr': 'amount_tax',
    },
    {
        'sequence': 115,
        'api_field_key': 'totals.total',
        'api_field_label': 'Total de la Factura',
        'api_field_description': (
            'Total de la factura con impuestos. Por defecto: amount_total. '
            'Para multimoneda: cambiar al campo equivalente en la moneda deseada '
            '(ej: amount_total_signed para moneda de la empresa).'
        ),
        'api_field_required': True,
        'source_model': 'move',
        'odoo_expr': 'amount_total',
    },
    {
        'sequence': 110,
        'api_field_key': 'totals.currency',
        'api_field_label': 'Moneda',
        'api_field_description': (
            'Código ISO de la moneda de la factura (ej: VES, USD).'
        ),
        'api_field_required': True,
        'source_model': 'move',
        'odoo_expr': 'currency_id.name',
    },
    {
        'sequence': 120,
        'api_field_key': 'totals.exchangeRate',
        'api_field_label': 'Tasa de Cambio',
        'api_field_description': (
            'Tasa de cambio aplicada respecto a la moneda de referencia. '
            'En Odoo 18 el campo invoice_currency_rate de la factura contiene este valor.'
        ),
        'api_field_required': False,
        'source_model': 'move',
        'odoo_expr': 'invoice_currency_rate',
    },
    {
        'sequence': 130,
        'api_field_key': 'totals.referenceCurrency',
        'api_field_label': 'Moneda de Referencia',
        'api_field_description': (
            'Moneda de referencia para el tipo de cambio (ej: USD). '
            'Si no aplica conversión, dejar vacío.'
        ),
        'api_field_required': False,
        'source_model': 'move',
        'default_value': 'USD',
    },
    {
        'sequence': 140,
        'api_field_key': 'totals.exchangeRateOperator',
        'api_field_label': 'Operador de Tasa',
        'api_field_description': (
            'Operador matemático para aplicar la tasa de cambio. '
            'Usar / (división) o * (multiplicación) según la convención del BCV.'
        ),
        'api_field_required': False,
        'source_model': 'move',
        'default_value': '/',
    },
    # --- Documento ---
    {
        'sequence': 150,
        'api_field_key': 'notes',
        'api_field_label': 'Notas',
        'api_field_description': (
            'Observaciones o notas adicionales que acompañan la factura.'
        ),
        'api_field_required': False,
        'source_model': 'move',
        'odoo_expr': 'narration',
    },
    {
        'sequence': 155,
        'api_field_key': 'dueDate',
        'api_field_label': 'Fecha de Vencimiento',
        'api_field_description': (
            'Fecha de vencimiento del documento (DD/MM/AAAA). '
            'Se calcula automáticamente desde la fecha de vencimiento de la factura en Odoo.'
        ),
        'api_field_required': False,
        'source_model': 'move',
        'odoo_expr': '',
    },
    {
        'sequence': 160,
        'api_field_key': 'adjustmentComment',
        'api_field_label': 'Comentario de Ajuste (NC)',
        'api_field_description': (
            'Comentario sobre el ajuste aplicado en la Nota de Crédito. '
            'Por defecto toma las Notas internas de la factura (narration).'
        ),
        'api_field_required': False,
        'source_model': 'move',
        'odoo_expr': 'narration',
        'default_value': 'Nota de Crédito',
    },
    # --- Vendedor ---
    {
        'sequence': 400,
        'api_field_key': 'vendor.code',
        'api_field_label': 'Vendedor — Código',
        'api_field_description': 'Código del vendedor (máx 20 chars). Usa el ID numérico del usuario (invoice_user_id.id) para evitar superar el límite de longitud de HKA.',
        'api_field_required': False,
        'source_model': 'move',
        'odoo_expr': 'invoice_user_id.id',
    },
    {
        'sequence': 401,
        'api_field_key': 'vendor.name',
        'api_field_label': 'Vendedor — Nombre',
        'api_field_description': 'Nombre del vendedor (máx 255 chars). Dejar vacío si no aplica.',
        'api_field_required': False,
        'source_model': 'move',
        'odoo_expr': 'invoice_user_id.name',
    },
    {
        'sequence': 402,
        'api_field_key': 'vendor.cashierNumber',
        'api_field_label': 'Vendedor — Nro. de Cajero',
        'api_field_description': 'Número de cajero del vendedor (máx 20 chars). Dejar vacío si no aplica.',
        'api_field_required': False,
        'source_model': 'move',
        'odoo_expr': '',
    },
]


class TafelFieldMap(models.Model):
    _name = 'tafel.field.map'
    _description = 'Mapeo de Campos API — Factura Electrónica'
    _order = 'sequence, id'
    _rec_name = 'api_field_label'

    provider_config_id = fields.Many2one(
        'tafel.provider.config',
        required=True,
        ondelete='cascade',
    )
    company_id = fields.Many2one(
        related='provider_config_id.company_id',
        store=True,
    )
    sequence = fields.Integer(default=10)
    api_field_key = fields.Char(string='Clave API', required=True, readonly=True)
    api_field_label = fields.Char(string='Campo API', required=True, readonly=True)
    api_field_description = fields.Text(string='Descripción', readonly=True)
    api_field_required = fields.Boolean(string='Requerido', readonly=True)
    source_model = fields.Selection([
        ('move', 'Factura'),
        ('line', 'Línea de Factura'),
    ], string='Contexto', required=True, default='move', readonly=True,
        help='Registro sobre el que se evalúa la expresión Odoo.')
    source_model_technical = fields.Char(
        compute='_compute_source_model_technical',
        store=False,
    )
    odoo_expr = fields.Char(
        string='Expresión Odoo',
        help='Ruta de campo relativa al Contexto indicado. '
             'Factura: partner_id.vat, currency_id.name | '
             'Línea: name, product_id.detailed_type',
    )
    default_value = fields.Char(
        string='Valor por Defecto',
        help='Valor fijo a usar cuando la expresión Odoo no aplica o está vacía.',
    )

    # --- Helpers de selección de campo ---
    odoo_field_id = fields.Many2one(
        'ir.model.fields',
        string='Campo',
        ondelete='set null',
        domain="[('model_id.model', '=', source_model_technical), "
               " ('ttype', 'not in', ['one2many', 'many2many', 'binary'])]",
        help='Selector de campo del modelo indicado en Contexto.',
    )
    odoo_field_relation = fields.Char(
        related='odoo_field_id.relation',
        store=False,
    )
    odoo_related_field_id = fields.Many2one(
        'ir.model.fields',
        string='Campo Secundario',
        ondelete='set null',
        domain="[('model_id.model', '=', odoo_field_relation), "
               " ('ttype', 'not in', ['one2many', 'many2many', 'binary'])]",
        help='Campo del modelo relacionado (ej: vat dentro de res.partner).',
    )

    @api.depends('source_model')
    def _compute_source_model_technical(self):
        mapping = {'move': 'account.move', 'line': 'account.move.line'}
        for rec in self:
            rec.source_model_technical = mapping.get(rec.source_model, 'account.move')

    @api.onchange('odoo_field_id')
    def _onchange_odoo_field_id(self):
        self.odoo_related_field_id = False
        if self.odoo_field_id:
            self.odoo_expr = self.odoo_field_id.name

    @api.onchange('odoo_related_field_id')
    def _onchange_odoo_related_field_id(self):
        if self.odoo_related_field_id and self.odoo_field_id:
            self.odoo_expr = f'{self.odoo_field_id.name}.{self.odoo_related_field_id.name}'
