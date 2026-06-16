def migrate(cr, version):
    if not version:
        return
    cr.execute("""
        UPDATE tafel_field_map
        SET odoo_expr = vals.expr
        FROM (VALUES
            ('vendor.name', 'invoice_user_id.name'),
            ('vendor.code', 'invoice_user_id.login')
        ) AS vals(key, expr)
        WHERE api_field_key = vals.key
          AND (odoo_expr IS NULL OR odoo_expr = '')
    """)
