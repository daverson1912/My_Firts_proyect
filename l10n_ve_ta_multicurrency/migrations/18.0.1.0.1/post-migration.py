# -*- coding: utf-8 -*-
import logging
from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """
    Backfill de los campos de referencia ISLR (*_ref) para facturas existentes.

    Motivo: el código anterior aplicaba un round-trip VES->USD->VES que corrompió
    tanto los campos nativos (l10n_ve_islr_subtrahend = 5.54) como dejó vacíos los
    *_ref. El sustraendo real solo lo conoce el API fiscal (no está en master data),
    por lo que la única forma exacta de corregir registros viejos es re-llamar al API.

    Estrategia: re-ejecutar action_calculate_islr_retention por factura. Esto invoca
    _process_islr_line_calculated_amounts (override multimoneda ya corregido) que
    reescribe los *_ref con el valor PURO del API en Bs. No se altera contabilidad:
    _inject_islr_integrated_line ya está protegido por `state == 'draft'`, de modo
    que en facturas publicadas solo se refrescan los campos informativos.

    Robustez: cada factura va en su propio savepoint + try/except, para que un fallo
    del API (o de una factura) no aborte el upgrade ni contamine la transacción.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})

    moves = env['account.move'].search([
        ('move_type', 'in', ('in_invoice', 'in_refund', 'out_invoice', 'out_refund')),
        ('invoice_line_ids.l10n_ve_islr_amount_line', '!=', 0),
    ])
    _logger.info(
        "[MC-MIGRATION 1.0.1] Recalculando campos _ref ISLR para %s facturas...",
        len(moves),
    )

    ok, skipped = 0, 0
    for move in moves:
        # Solo aplica cuando hay moneda de referencia (contexto multimoneda activo)
        if not move.l10n_ve_ta_multicurrency_fiscal_id:
            continue
        try:
            with cr.savepoint():
                move.action_calculate_islr_retention(raise_error=False)
            ok += 1
        except Exception as e:
            skipped += 1
            _logger.warning(
                "[MC-MIGRATION 1.0.1] Factura %s (id=%s) omitida: %s",
                move.name or '(sin nombre)', move.id, e,
            )

    _logger.info(
        "[MC-MIGRATION 1.0.1] Backfill ISLR terminado. Corregidas=%s, Omitidas=%s",
        ok, skipped,
    )
