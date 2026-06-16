import logging
from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

class AccountWhIslrSendWizard(models.TransientModel):
    _name = 'account.wh.islr.send.wizard'
    _description = 'Asistente de Envío Masivo de Retenciones ISLR'

    def _default_line_ids(self):
        active_ids = self.env.context.get('active_ids')
        _logger.info(f"[FISCAL_DEBUG_ISLR] Inicializando wizard con active_ids: {active_ids}")
        if not active_ids:
            return []
        
        retentions = self.env['account.wh.islr.summary'].browse(active_ids)
        lines = []
        for ret in retentions:
            email = ret.partner_id.email or _('Sin correo configurado')
            _logger.info(f"[FISCAL_DEBUG_ISLR] Agregando línea: {ret.name}, Proveedor: {ret.partner_id.name}, Correo: {email}")
            lines.append((0, 0, {
                'summary_name': ret.name,
                'partner_name': ret.partner_id.name,
                'email': email,
            }))
        return lines

    line_ids = fields.One2many(
        'account.wh.islr.send.wizard.line', 
        'wizard_id', 
        string='Retenciones a Enviar',
        default=_default_line_ids
    )

    def action_send_emails(self):
        self.ensure_one()
        _logger.info(f"[FISCAL_DEBUG_ISLR] action_send_emails disparado. Líneas encontradas: {len(self.line_ids)}")
        
        template = self.env.ref('l10n_ve_simplit_fiscal.email_template_wh_islr', raise_if_not_found=False)
        if not template:
            _logger.error("[FISCAL_DEBUG_ISLR] No se encontró la plantilla 'email_template_wh_islr'")
            raise UserError(_('No se encontró la plantilla de correo para retenciones ISLR.'))

        count = 0
        for line in self.line_ids:
            _logger.info(f"[FISCAL_DEBUG_ISLR] Procesando línea para: {line.summary_name}")
            
            email_to_use = line.email
            if email_to_use == _('Sin correo configurado') or not email_to_use:
                _logger.warning(f"[FISCAL_DEBUG_ISLR] Saltando {line.summary_name} por falta de correo.")
                continue
            
            try:
                summary = self.env['account.wh.islr.summary'].search([('name', '=', line.summary_name)], limit=1)
                if not summary:
                    _logger.error(f"[FISCAL_DEBUG_ISLR] No se encontró el resumen para {line.summary_name}")
                    continue

                _logger.info(f"[FISCAL_DEBUG_ISLR] Enviando vía template.send_mail para summary_id: {summary.id}")
                template.send_mail(summary.id, force_send=True, raise_exception=True)
                
                count += 1
                _logger.info(f"[FISCAL_DEBUG_ISLR] ÉXITO: {summary.name} enviado a {email_to_use}")
            except Exception as e:
                _logger.exception(f"[FISCAL_DEBUG_ISLR] ERROR CRÍTICO enviando correo para {line.summary_name}: {str(e)}")

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Envío Masivo Completado'),
                'message': _('Se han enviado %s correos electrónicos de ISLR correctamente.') % count,
                'type': 'success',
                'sticky': False,
            }
        }

class AccountWhIslrSendWizardLine(models.TransientModel):
    _name = 'account.wh.islr.send.wizard.line'
    _description = 'Línea de Asistente de Envío de Retenciones ISLR'

    wizard_id = fields.Many2one('account.wh.islr.send.wizard', string='Wizard')
    summary_name = fields.Char(string='Comprobante')
    partner_name = fields.Char(string='Proveedor')
    email = fields.Char(string='Correo Electrónico')
