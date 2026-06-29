from odoo import fields, models

class ResCompany(models.Model):
    """ Almacena la configuración global y fechas de sincronización por compañía """
    """ Stores global configuration and synchronization dates per company """
    _inherit = 'res.company'

    # Credenciales de API / API Credentials
    whub_api_key = fields.Char(string='API Key WispHub', groups="base.group_system")
    
    # Parámetros del Middleware / Middleware Settings
    whub_middleware_url = fields.Char(string='URL del Middleware')
    whub_allowed_notice_statuses = fields.Char(string='Estados de Avisos Permitidos', default='pending,pendiente,pendiente de pago,unpaid')
    whub_customers_page_size = fields.Integer(string='Tamaño de página de Clientes', default=200)
    whub_customers_max_pages = fields.Integer(string='Páginas máximas de Clientes', default=50)

    # Metadatos de sincronización / Sync metadata
    whub_sync_date = fields.Datetime(string='Último Mapeo General', readonly=True)
    whub_sync_cat = fields.Datetime(string='Sinc. Categorías', readonly=True)
    whub_sync_prod = fields.Datetime(string='Sinc. Productos', readonly=True)
    whub_sync_plan = fields.Datetime(string='Sinc. Planes', readonly=True)
    whub_sync_cust = fields.Datetime(string='Sinc. Clientes', readonly=True)
    whub_sync_inv = fields.Datetime(string='Punto de Partida (Avisos de Cobro)', readonly=True,
                                     help="Fecha y hora de la última orden de venta sincronizada. "
                                          "El cron de Avisos de Cobro continúa automáticamente desde aquí.")
