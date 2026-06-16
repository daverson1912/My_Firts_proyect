# -*- coding: utf-8 -*-

from odoo import models, api, _



class AccountWhIvaTxtExportWizard(models.TransientModel):

    _inherit = 'account.wh.iva.txt.export.wizard'



    def action_generate_txt(self):

        """

        Extensión para que el TXT use los montos en Bolívares (VES)

        si la integración fiscal multimoneda está activa.

        """

        # Verificamos si la integración fiscal está activa para la compañía actual

        config = self.env['l10n_ve_ta_multicurrency.api.config'].search([

            ('company_id', '=', self.env.company.id)

        ], limit=1)



        if not config or not config.l10n_ve_ta_multicurrency_enable_fiscal:

            return super(AccountWhIvaTxtExportWizard, self).action_generate_txt()



        # Re-implementamos parcialmente la construcción del payload pero usando campos VES

        # Nota: Idealmente deberíamos interceptar el payload, pero el método original 

        # lo construye y lo envía en una sola función.

        self.ensure_one()

        items = []

        for wh in self.wh_iva_ids:

            period = wh.date.strftime('%Y%m')

            doc_type = '03' if wh.wh_type == 'refund' else '01'

            agent_rif = (wh.company_id.vat or wh.company_id.partner_id.vat or '').replace('-', '').strip()

            supplier_rif = (wh.partner_id.vat or '').replace('-', '').strip()



            item = {

                "agentFiscalId": agent_rif,

                "period": period,

                "invoiceDate": wh.invoice_date.strftime('%Y-%m-%d'),

                "operationType": "C",

                "documentType": doc_type,

                "supplierFiscalId": supplier_rif,

                "invoiceNumber": wh.supplier_invoice_number or wh.invoice_number,

                "controlNumber": wh.control_number or '0',

                # USAR CAMPOS EN BOLIVARES (VES)

                "totalAmount": float(wh.l10n_ve_ta_multicurrency_total_invoice),

                "taxBase": float(wh.l10n_ve_ta_multicurrency_taxable_base),

                "withheldAmount": float(wh.l10n_ve_ta_multicurrency_amount_total_ret),

                "affectedDocumentNumber": wh.affected_invoice_number or "0",

                "voucherNumber": wh.name,

                "exemptAmount": float(wh.l10n_ve_ta_multicurrency_exempt),

                "taxRate": int(wh.tax_aliquot),

                "caseNumber": "0"

            }

            items.append(item)



        # Aquí "engañamos" al wizard original inyectando nuestro payload

        # pero como no podemos inyectarlo fácilmente en medio de la función,

        # llamaremos a un método que haga el POST (que es lo mismo que hace el original)

        return self.with_context(l10n_ve_ta_multicurrency_items=items)._execute_api_call_txt()



    def _execute_api_call_txt(self):

        """

        Método auxiliar para ejecutar la llamada al API con los items modificados.

        """

        import requests

        import base64

        import json

        from odoo.exceptions import UserError

        from ...l10n_ve_simplit_fiscal.models.utils import get_api_url



        items = self._context.get('l10n_ve_ta_multicurrency_items')

        payload = {"items": items}

        

        api_host = get_api_url()

        url = f"{api_host.rstrip('/')}/api/v1/fiscal-reports/iva-txt"

        

        company = self.wh_iva_ids[0].company_id

        config = self.env['simplitfiscal.config'].search([('company_id', '=', company.id)], limit=1)

        api_key = config.ta_api_key if config else False



        headers = {}

        if api_key:

            headers['X-API-Key'] = api_key



        try:

            response = requests.post(url, json=payload, headers=headers, timeout=30)

            response.raise_for_status()

            

            period = self.wh_iva_ids[0].date.strftime('%Y%m')

            self.write({

                'txt_file': base64.b64encode(response.content),

                'txt_filename': f"IVA_RET_{period}_VES.txt",

                'state': 'done'

            })

            return {

                'type': 'ir.actions.act_window',

                'res_model': self._name,

                'res_id': self.id,

                'view_mode': 'form',

                'target': 'new',

            }

        except Exception as e:

            raise UserError(_("Error al conectar con el servidor de reportes (VES): %s") % str(e))





class AccountWhIslrXmlExportWizard(models.TransientModel):

    _inherit = 'account.wh.islr.xml.export.wizard'



    def action_generate_xml(self):

        """

        Extensión para que el XML de ISLR use montos en Bolívares (VES).

        """

        config = self.env['l10n_ve_ta_multicurrency.api.config'].search([

            ('company_id', '=', self.env.company.id)

        ], limit=1)



        if not config or not config.l10n_ve_ta_multicurrency_enable_fiscal:

            return super(AccountWhIslrXmlExportWizard, self).action_generate_xml()



        self.ensure_one()

        items = []

        agent_rif = self.company_id.vat.replace("-", "").strip()

        first_date = self.wh_islr_ids[0].date

        period = first_date.strftime('%Y%m')



        for wh in self.wh_islr_ids:

            supplier_rif = wh.partner_id.vat.replace("-", "").strip()

            for line in wh.line_ids:

                items.append({

                    "supplierFiscalId": supplier_rif,

                    "invoiceNumber": wh.move_id.l10n_ve_supplier_invoice_number or "",

                    "controlNumber": wh.move_id.l10n_ve_control_number or "",

                    "operationDate": wh.date.strftime('%d/%m/%Y'),

                    "conceptCode": line.fiscal_code or "",

                    # USAR CAMPOS EN BOLIVARES (VES)

                    "operationAmount": float(line.l10n_ve_ta_multicurrency_base_amount),

                    "retentionPercentage": float(line.retention_percentage)

                })



        payload = {

            "agentFiscalId": agent_rif,

            "period": period,

            "items": items

        }



        # Ejecutamos la llamada al API similar al original

        import requests

        import base64

        from odoo.exceptions import UserError

        from ...l10n_ve_simplit_fiscal.models.utils import get_api_url



        api_host = get_api_url()

        url = f"{api_host.rstrip('/')}/api/v1/fiscal-reports/islr-xml"

        

        fiscal_config = self.env['simplitfiscal.config'].search([('company_id', '=', self.company_id.id)], limit=1)

        api_key = fiscal_config.ta_api_key if fiscal_config else False



        headers = {'X-API-Key': api_key} if api_key else {}



        try:

            response = requests.post(url, json=payload, headers=headers, timeout=30)

            response.raise_for_status()

            

            filename = f"ISLR_{agent_rif}_{period}_VES.xml"

            self.write({

                'xml_file': base64.b64encode(response.content),

                'xml_filename': filename,

                'state': 'done'

            })

            

            return {

                'type': 'ir.actions.act_window',

                'res_model': self._name,

                'res_id': self.id,

                'view_mode': 'form',

                'target': 'new',

            }

        except Exception as e:

            raise UserError(_("Error al generar XML ISLR (VES): %s") % str(e))

