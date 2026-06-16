from odoo import models, fields, api


class L10nVeTaMulticurrencyRateSyncLog(models.Model):
    """
    EN: Store the history of currency rate synchronizations from BCV API.
    ES: Almacena el historial de sincronizaciones de tasas de cambio desde el API del BCV.
    """
    _name = 'l10n_ve_ta_multicurrency.rate.sync.log'
    _description = 'BCV Rate Synchronization Log'
    _order = 'create_date desc'

    name = fields.Char(
        string='Sync Label',
        compute='_compute_name',
        store=True,
        help="EN: Auto-generated label with sync date and time. | ES: Etiqueta auto-generada con fecha y hora de sincronización.",
    )
    l10n_ve_ta_multicurrency_fetched_rate = fields.Float(
        string='Fetched Rate',
        digits=(12, 6),
        readonly=True,
        help="EN: Exchange rate obtained from the API. | ES: Tasa de cambio obtenida del API.",
    )
    l10n_ve_ta_multicurrency_status = fields.Selection([
        ('success', 'Success'),
        ('failed', 'Failed'),
    ], string='Status', readonly=True)

    l10n_ve_ta_multicurrency_response_msg = fields.Text(
        string='Response Message',
        readonly=True,
        help="EN: Raw server response for debugging. | ES: Respuesta cruda del servidor para depuración.",
    )

    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        readonly=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        default=lambda self: self.env.company,
        readonly=True,
    )

    @api.depends('create_date')
    def _compute_name(self):
        """
        EN: Auto-compute the display name from the creation date.
        ES: Calcula automáticamente el nombre visible desde la fecha de creación.
        """
        for rec in self:
            if rec.create_date:
                rec.name = rec.create_date.strftime('%Y-%m-%d %H:%M:%S')
            else:
                rec.name = 'New'
