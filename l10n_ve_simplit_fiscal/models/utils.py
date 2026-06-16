# -*- coding: utf-8 -*-
import json
import os
import logging

_logger = logging.getLogger(__name__)

def get_api_url():
    """
    Lee la URL base del API desde el archivo globalConfig.json en la raíz del módulo.
    Si el archivo no existe o no tiene el campo, devuelve el fallback vacío.
    """
    try:
        from odoo.modules.module import get_module_resource
        config_path = get_module_resource('l10n_ve_simplit_fiscal', 'globalConfig.json')
    except ImportError:
        # Fallback si no podemos importar get_module_resource
        current_dir = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(current_dir, '..', 'globalConfig.json')
    
    if not config_path or not os.path.exists(config_path):
        _logger.warning(f"ISLR Config: no hay configurada ruta de api de retenciones (archivo no encontrado en {config_path}).")
        return ""
        
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
            url = config.get('API_URL', "")
            if not url:
                _logger.warning(f"ISLR Config: archivo encontrado en {config_path} pero campo API_URL está vacío.")
            else:
                _logger.info(f"ISLR Config: usando host {url} desde {config_path}")
            return url
    except Exception as e:
        _logger.error(f"ISLR Config: Error leyendo globalConfig.json en {config_path}: {str(e)}")
        return ""


def get_config_value(key, default=None):
    """
    Lee un valor del archivo globalConfig.json.
    """
    try:
        from odoo.modules.module import get_module_resource
        config_path = get_module_resource('l10n_ve_simplit_fiscal', 'globalConfig.json')
    except ImportError:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(current_dir, '..', 'globalConfig.json')

    if not config_path or not os.path.exists(config_path):
        return default

    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
            return config.get(key, default)
    except Exception:
        return default
