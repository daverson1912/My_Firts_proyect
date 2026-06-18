# -*- coding: utf-8 -*-
{
    'name': 'Venezuela - Simplit Fiscal',
    'version': '18.0.1.0.0',
    'category': 'Accounting/Localizations',
    'summary': 'Sistema híbrido de retenciones IVA para Contribuyentes Especiales en Venezuela',
    'description': """
Venezuela - Gestión Fiscal Híbrida (Simplit)
=============================================

Este módulo automatiza el cálculo y gestión de retenciones de IVA para empresas
designadas como Contribuyentes Especiales (Agentes de Retención) en Venezuela.

Características principales:
-----------------------------
* Aplicación independiente con interfaz centralizada
* Configuración automática de impuestos y retenciones
* Reemplazo automático de impuestos en facturas de proveedor
* Sistema híbrido: contabilización inmediata, numeración diferida vía API

Estructura:
-----------
* Configuración: Datos de la empresa, activación de agente de retención
* Impuestos: Generación automática de impuestos y grupos
* Automatización: Reglas de reemplazo automático
    """,
    'author': 'TotalAplicaciones',
    'website': 'https://www.totalaplicaciones.com',
    'license': 'OPL-1',
    'depends': [
        'base',
        'account',
        'l10n_ve',
        'mail',  # Requerido por account.wh.iva (hereda mail.thread)
    ],
    'data': [
        'security/ir.model.access.csv',          # Seguridad
        'report/account_wh_iva_report.xml',      # Registro del reporte (Cargar antes de templates)
        'report/account_wh_islr_report.xml',     # Reporte ISLR
        'report/account_iva_purchase_ledger_report.xml', # Reporte Libro de Compras IVA
        'report/account_iva_purchase_ledger_templates.xml', # Template Libro de Compras IVA
        'report/account_igtf_report.xml',         # Registro Reporte IGTF
        'report/account_igtf_report_templates.xml', # Template Reporte IGTF
        'report/account_iva_sales_ledger_report.xml',    # Registro Libro de Ventas con IGTF
        'report/account_iva_sales_ledger_templates.xml', # Template Libro de Ventas con IGTF
        'data/simplitfiscal_data.xml',           # Auto-sync data on update
        'data/mail_template_data.xml',           # Plantilla de correo
        'data/cron_data.xml',                    # Cron envío automático de comprobantes
        'wizard/simplitfiscal_sequence_wizard_views.xml',  # Wizard de configuración de correlativo
        'wizard/simplitfiscal_islr_seq_wizard_views.xml',  # Wizard de correlativo ISLR
        'wizard/account_wh_iva_send_wizard_views.xml',    # Wizard de envío masivo
        'wizard/account_wh_islr_send_wizard_views.xml',   # Wizard de envío ISLR
        'wizard/account_wh_iva_txt_export_views.xml',     # Wizard de exportación TXT IVA
        'wizard/account_wh_iva_customer_unifier_views.xml', # Wizard de unificador ventas
        'wizard/account_wh_islr_xml_export_views.xml',    # Wizard de exportación XML ISLR
        'wizard/account_wh_islr_customer_unifier_views.xml', # Wizard de unificador ISLR ventas
        'wizard/account_igtf_report_views.xml',           # Reporte IGTF General
        'wizard/account_iva_sales_ledger_views.xml',      # Libro de Ventas con IGTF
        'wizard/account_iva_purchase_ledger_views.xml',  # Libro de Compras IVA
        'wizard/account_iva_resumen_views.xml',           # Resumen de IVA
        'report/resumen_iva_report.xml',                  # Resumen IVA Report
        'report/resumen_iva_templates.xml',               # Resumen IVA Templates
        'report/account_wh_iva_templates.xml',   # Template del reporte
        'report/account_wh_islr_templates.xml',  # Template ISLR
        'views/simplitfiscal_config_views.xml',  # Config views
        'views/account_wh_iva_views.xml',        # Withholding views
        'views/account_wh_iva_unifier_views.xml',# Unifier views
        'views/account_wh_iva_customer_views.xml', # Sales Withholding views
        'views/account_wh_islr_views.xml',       # ISLR Withholding views
        'views/account_wh_islr_customer_views.xml', # ISLR Sales Withholding views
        'views/account_wh_islr_unifier_views.xml',# ISLR Unifier views
        'views/simplitfiscal_menu.xml',          # Menu
        'views/res_partner_views.xml',           # Vista de proveedor
        'views/product_template_views.xml',      # Vista de producto (ISLR)
        'views/res_company_views.xml',           # Vista de compañía (Firma/Sello)
        'views/account_move_views.xml',          # Vista de factura con badge de retención
        'views/account_journal_views.xml',       # Flags de libros fiscales en diarios
    ],
    'assets': {},
    'installable': True,
    'application': True,  # ⭐ Ahora es una aplicación independiente
    'auto_install': False,
    'post_init_hook': 'post_init_hook',
}
