VENDOR_FIELDS = [
    (400, 'vendor.code',          'Vendedor — Código',         'Código del vendedor (máx 20 chars). Dejar vacío si no aplica.',           False, 'move', 'invoice_user_id.login', None),
    (401, 'vendor.name',          'Vendedor — Nombre',         'Nombre del vendedor (máx 255 chars). Dejar vacío si no aplica.',          False, 'move', 'invoice_user_id.name',  None),
    (402, 'vendor.cashierNumber', 'Vendedor — Nro. de Cajero', 'Número de cajero del vendedor (máx 20 chars). Dejar vacío si no aplica.', False, 'move', None,                   None),
]


def migrate(cr, version):
    if not version:
        return

    # Update existing records that still have empty odoo_expr
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

    # Insert missing vendor field maps for providers that don't have them yet
    cr.execute("SELECT id, company_id FROM tafel_provider_config")
    providers = cr.fetchall()

    for provider_id, company_id in providers:
        for seq, key, label, desc, required, source, expr, default in VENDOR_FIELDS:
            cr.execute("""
                INSERT INTO tafel_field_map
                    (provider_config_id, company_id, sequence, api_field_key, api_field_label,
                     api_field_description, api_field_required, source_model, odoo_expr, default_value,
                     create_uid, write_uid, create_date, write_date)
                SELECT %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1, 1, NOW(), NOW()
                WHERE NOT EXISTS (
                    SELECT 1 FROM tafel_field_map
                    WHERE provider_config_id = %s AND api_field_key = %s
                )
            """, (provider_id, company_id, seq, key, label, desc, required, source, expr, default,
                  provider_id, key))
