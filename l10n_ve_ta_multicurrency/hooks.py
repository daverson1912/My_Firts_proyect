# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def post_migrate(env):
    """
    Limpia propiedades de bloqueo residuales.
    Los campos ahora son company_dependent, así que limpiamos
    cualquier propiedad de bloqueo que haya quedado de la versión anterior.
    """
    cr = env.cr
    _logger.info("l10n_ve_ta_multicurrency: Limpiando bloqueos residuales (campos ahora son por compañía)...")

    # Limpiar la columna legacy si aún existe y es tipo boolean
    cr.execute("""
        SELECT data_type 
        FROM information_schema.columns 
        WHERE table_name = 'res_currency' 
          AND column_name = 'l10n_ve_ta_multicurrency_is_locked';
    """)
    row = cr.fetchone()
    if row and row[0] == 'boolean':
        cr.execute("""
            UPDATE res_currency
            SET l10n_ve_ta_multicurrency_is_locked = FALSE
            WHERE l10n_ve_ta_multicurrency_is_locked = TRUE
        """)


    # Limpiar propiedades de bloqueo que pudieran haberse migrado (solo si existe la tabla)
    cr.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_name = 'ir_property'
        );
    """)
    if cr.fetchone()[0]:
        cr.execute("""
            DELETE FROM ir_property
            WHERE name = 'l10n_ve_ta_multicurrency_is_locked'
              AND value_text = 'True'
        """)

    _logger.info("l10n_ve_ta_multicurrency: Bloqueos residuales limpiados.")

    _load_fiscal_views(env)


def _load_fiscal_views(env):
    """
    Carga condicionalmente las vistas XML que heredan de l10n_ve_simplit_fiscal
    solo si dicho módulo está instalado.
    """
    from odoo import tools
    cr = env.cr
    module = env['ir.module.module'].sudo().search([
        ('name', '=', 'l10n_ve_simplit_fiscal'),
        ('state', '=', 'installed')
    ], limit=1)

    if not module:
        _logger.info("l10n_ve_ta_multicurrency: l10n_ve_simplit_fiscal no está instalado. Omitiendo vistas fiscales.")
        return

    view_files = [
        'views/account_wh_islr_views.xml',
        'views/account_wh_iva_views.xml',
    ]

    for view_file in view_files:
        try:
            _logger.info("l10n_ve_ta_multicurrency: Cargando vista fiscal %s", view_file)
            tools.convert_file(
                cr,
                'l10n_ve_ta_multicurrency',
                view_file,
                None,
                mode='init',
                noupdate=False,
                kind='init'
            )
        except Exception as e:
            _logger.warning("l10n_ve_ta_multicurrency: No se pudo cargar %s: %s", view_file, e)


def post_init_hook(env):
    """ Hook post-instalación para sincronizar monedas y cargar vistas fiscales si aplica. """
    post_migrate(env)
