# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
import logging

_logger = logging.getLogger(__name__)


class WhEmailBackgroundService(models.Model):
    """
    Servicio de envío automático de correos para comprobantes de retención.
    
    Este servicio es ejecutado por un cron cada 15 minutos. Busca comprobantes
    IVA/ISLR con email_state='pending', genera el PDF vía la plantilla de correo
    y envía el comprobante al proveedor correspondiente.
    """
    _name = 'wh.email.background.service'
    _description = 'Servicio de Envío de Correos de Retenciones'

    MAX_RETRIES = 3
    BATCH_SIZE = 20  # Maximum records to process per cron execution

    @api.model
    def _cron_send_pending_wh_emails(self):
        """
        Entry point for the cron job. Processes pending IVA and ISLR emails.
        """
        _logger.info("[EMAIL-BG] Iniciando cron de envío de comprobantes...")
        
        iva_count = self._process_pending_model(
            model_name='account.wh.iva',
            summary_model_name='account.wh.iva.summary',
            template_xmlid='l10n_ve_simplit_fiscal.email_template_wh_iva',
            wh_type='iva',
        )
        islr_count = self._process_pending_model(
            model_name='account.wh.islr',
            summary_model_name='account.wh.islr.summary',
            template_xmlid='l10n_ve_simplit_fiscal.email_template_wh_islr',
            wh_type='islr',
        )
        
        _logger.info(
            f"[EMAIL-BG] Cron finalizado. "
            f"IVA: {iva_count} enviados. ISLR: {islr_count} enviados."
        )

    @api.model
    def _process_pending_model(self, model_name, summary_model_name, template_xmlid, wh_type):
        """
        Finds pending records for a given model, groups them by summary key,
        and sends emails for each group.
        
        Returns the number of successfully sent emails.
        """
        Model = self.env[model_name]
        
        pending = Model.search([
            ('email_state', '=', 'pending'),
            ('state', 'in', ['posted', 'declared']),
            ('name', '!=', False),
        ], limit=self.BATCH_SIZE, order='date asc')
        
        if not pending:
            _logger.info(f"[EMAIL-BG-{wh_type.upper()}] Sin comprobantes pendientes.")
            return 0
        
        _logger.info(
            f"[EMAIL-BG-{wh_type.upper()}] "
            f"Encontrados {len(pending)} registros pendientes."
        )
        
        # Group by summary key: (name, partner_id, company_id, type)
        groups = {}
        for rec in pending:
            key = (rec.name, rec.partner_id.id, rec.company_id.id, rec.type)
            if key not in groups:
                groups[key] = Model
            groups[key] |= rec
        
        sent_count = 0
        for key, records in groups.items():
            success = self._send_email_for_group(
                records=records,
                summary_model_name=summary_model_name,
                template_xmlid=template_xmlid,
                wh_type=wh_type,
            )
            if success:
                sent_count += 1
        
        return sent_count

    @api.model
    def _send_email_for_group(self, records, summary_model_name, template_xmlid, wh_type):
        """
        Sends an email for a group of records that share the same summary.
        
        Steps:
        1. Find the corresponding summary record
        2. Get the mail template
        3. Send the email via template (which auto-attaches the PDF report)
        4. Update email_state on success
        5. Handle errors with retry logic
        
        Returns True if sent successfully, False otherwise.
        """
        first_rec = records[0]
        label = f"{first_rec.name} ({first_rec.partner_id.name})"
        
        try:
            # 1. Find the summary record in the SQL View
            SummaryModel = self.env[summary_model_name]
            summary = SummaryModel.search([
                ('name', '=', first_rec.name),
                ('partner_id', '=', first_rec.partner_id.id),
                ('company_id', '=', first_rec.company_id.id),
                ('type', '=', first_rec.type),
            ], limit=1)
            
            if not summary:
                _logger.warning(
                    f"[EMAIL-BG-{wh_type.upper()}] "
                    f"No se encontró el resumen para {label}. Saltando."
                )
                records.write({
                    'email_state': 'failed',
                    'last_email_error': _('No se encontró el registro de resumen correspondiente.'),
                    'last_email_at': fields.Datetime.now(),
                })
                return False
            
            # 2. Get the mail template
            template = self.env.ref(template_xmlid, raise_if_not_found=False)
            if not template:
                _logger.error(
                    f"[EMAIL-BG-{wh_type.upper()}] "
                    f"Plantilla de correo '{template_xmlid}' no encontrada."
                )
                records.write({
                    'email_state': 'failed',
                    'last_email_error': _('Plantilla de correo no encontrada: %s') % template_xmlid,
                    'last_email_at': fields.Datetime.now(),
                })
                return False
            
            # 3. Validate partner has email
            if not first_rec.partner_id.email:
                _logger.warning(
                    f"[EMAIL-BG-{wh_type.upper()}] "
                    f"Proveedor {first_rec.partner_id.name} sin email. Marcando skipped."
                )
                records.write({
                    'email_state': 'skipped',
                    'last_email_at': fields.Datetime.now(),
                })
                return False
            
            # Comportamiento Nativo Odoo (SMTP)
            _logger.info(f"[EMAIL-BG-{wh_type.upper()}] Enviando vía SMTP nativo de Odoo...")
            with self.env.cr.savepoint():
                template.send_mail(summary.id, force_send=True, raise_exception=True)
            
            # 5. Success — update all base records
            now = fields.Datetime.now()
            records.write({
                'email_state': 'sent',
                'last_email_at': now,
                'last_email_error': False,
            })
            
            # 6. Post audit message in the summary chatter
            try:
                summary.message_post(
                    body=_(
                        '✅ Correo enviado automáticamente a <b>%s</b> (%s).',
                    ) % (first_rec.partner_id.name, first_rec.partner_id.email),
                    message_type='notification',
                    subtype_xmlid='mail.mt_note',
                )
            except Exception:
                pass  # Non-critical, don't fail the whole operation
            
            _logger.info(
                f"[EMAIL-BG-{wh_type.upper()}] "
                f"Correo enviado exitosamente para {label}."
            )
            return True
            
        except Exception as e:
            _logger.exception(
                f"[EMAIL-BG-{wh_type.upper()}] "
                f"Error enviando correo para {label}: {str(e)}"
            )
            
            # Retry logic
            now = fields.Datetime.now()
            max_retry = max(rec.email_retry_count for rec in records) + 1
            
            if max_retry >= self.MAX_RETRIES:
                # Max retries exceeded — mark as failed
                records.write({
                    'email_state': 'failed',
                    'last_email_at': now,
                    'last_email_error': str(e)[:500],
                    'email_retry_count': max_retry,
                })
                
                # Post failure in chatter
                try:
                    SummaryModel = self.env[summary_model_name]
                    summary = SummaryModel.search([
                        ('name', '=', first_rec.name),
                        ('partner_id', '=', first_rec.partner_id.id),
                        ('company_id', '=', first_rec.company_id.id),
                        ('type', '=', first_rec.type),
                    ], limit=1)
                    if summary:
                        summary.message_post(
                            body=_(
                                '❌ Error al enviar correo a <b>%s</b> después de %s intentos.<br/>'
                                'Error: %s',
                            ) % (first_rec.partner_id.name, max_retry, str(e)[:200]),
                            message_type='notification',
                            subtype_xmlid='mail.mt_note',
                        )
                except Exception:
                    pass
                
                _logger.error(
                    f"[EMAIL-BG-{wh_type.upper()}] "
                    f"Máximo de reintentos ({self.MAX_RETRIES}) alcanzado para {label}."
                )
            else:
                # Still has retries left — keep as pending with incremented count
                records.write({
                    'email_state': 'pending',
                    'last_email_at': now,
                    'last_email_error': str(e)[:500],
                    'email_retry_count': max_retry,
                })
                _logger.warning(
                    f"[EMAIL-BG-{wh_type.upper()}] "
                    f"Reintento {max_retry}/{self.MAX_RETRIES} para {label}."
                )
            
            return False
