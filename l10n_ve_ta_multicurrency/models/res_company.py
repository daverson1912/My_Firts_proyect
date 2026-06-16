from odoo import models

class ResCompany(models.Model):
    """
    EN: Extend res.company to remove the BCV sync activation flag.
        This setting was moved to the centralized configuration model
        l10n_ve_ta_multicurrency.api.config following the reviewer's request.
    ES: Extiende res.company para remover el flag de activación de sincronización BCV.
        Este ajuste se movió al modelo de configuración centralizado
        l10n_ve_ta_multicurrency.api.config siguiendo la solicitud del revisor.
    """
    _inherit = 'res.company'
