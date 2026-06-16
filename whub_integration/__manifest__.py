{
    'name': 'Integración WHub',
    'version': '18.0.2.0.3',
    'category': 'Sales',
    'summary': 'Integración con Middleware WispHub / WispHub Middleware Integration',
    'description': """
        Módulo para integrar Odoo con el Middleware de WispHub.
        Module to integrate Odoo with the WispHub Middleware.
        
        Características / Features:
        - Soporte Multi-Compañía / Multi-Company Support
        - Sincronización de clientes, productos y categorías / Sync for customers, products and categories
        - Flujo de creación masiva profesional / Professional batch creation workflow
        - Avisos de Cobro → Órdenes de Venta / Payment Notices → Sales Orders
        - Log de sincronización con re-procesamiento / Sync log with reprocessing
    """,
    'depends': ['base', 'product', 'sale', 'contacts', 'account', 'payment'],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_cron_data.xml',
        'views/whub_notice_sync_wizard_views.xml',
        'views/res_config_settings_views.xml',
        'views/wizard_config_views.xml',
        'views/wizard_homologation_views.xml',
        'views/res_partner_views.xml',
        'views/product_views.xml',
        'views/sale_order_views.xml',
        'views/account_move_views.xml',
        'views/whub_notice_sync_log_views.xml',
        'views/menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
        ],
    },
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
