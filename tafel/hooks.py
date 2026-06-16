from .models.tafel_field_map import DEFAULT_FIELD_MAPS


def _backfill_field_maps(env):
    """Update existing field map records that still have empty odoo_expr
    but DEFAULT_FIELD_MAPS now provides a non-empty value for that key."""
    updates = {
        fm['api_field_key']: fm['odoo_expr']
        for fm in DEFAULT_FIELD_MAPS
        if fm.get('odoo_expr')
    }
    if not updates:
        return
    empty_maps = env['tafel.field.map'].search([
        ('api_field_key', 'in', list(updates.keys())),
        ('odoo_expr', 'in', [False, '']),
    ])
    for rec in empty_maps:
        new_expr = updates.get(rec.api_field_key)
        if new_expr:
            rec.odoo_expr = new_expr


def post_init_hook(env):
    _backfill_field_maps(env)
