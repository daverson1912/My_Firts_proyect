# -*- coding: utf-8 -*-
import requests
import logging
from odoo import api, fields

_logger = logging.getLogger(__name__)

def post_init_hook(env):
    """
    Sync ISLR master data from external API after install.
    """
    sync_islr_master_data(env)

def sync_islr_master_data(env, api_key=None):
    from .models.utils import get_api_url
    api_host = get_api_url()
    
    if not api_host:
        _logger.warning("ISLR Sync: No API Host configured. Skipping sync.")
        return

    base_url = f"{api_host.rstrip('/')}/api/v1/master-data"
    headers = {}
    if api_key:
        headers['X-API-Key'] = api_key
    
    try:
        # 1. Sync Provider Types
        url_providers = f"{base_url}/provider-types"
        try:
            response = requests.get(url_providers, headers=headers, timeout=5)
            if response.status_code in (401, 403):
                _logger.warning(f"ISLR Sync: API Key invalid or License expired ({response.status_code}). Skipping sync.")
                return
            response.raise_for_status()
            data_providers = response.json()
        except Exception as e:
            _logger.warning(f"ISLR Sync: Could not connect to {url_providers}: {e}. Skipping.")
            return

        if data_providers.get('error') == 0:
            ProviderType = env['islr.provider.type']
            for item in data_providers.get('data', []):
                existing = ProviderType.search([('code', '=', item['code'])], limit=1)
                vals = {'code': item['code'], 'guid': item['guid'], 'description': item['description']}
                if existing:
                    existing.write(vals)
                else:
                    ProviderType.create(vals)
            _logger.info("ISLR Sync: Provider types synced.")

        # 2. Sync Retention Types
        url_types = f"{base_url}/retention-types"
        try:
            response_types = requests.get(url_types, headers=headers, timeout=5)
            response_types.raise_for_status()
            data_types = response_types.json()
        except Exception as e:
            _logger.warning(f"ISLR Sync: Could not connect to {url_types}: {e}. Skipping.")
            return

        if data_types.get('error') == 0:
            RetentionType = env['islr.retention.type']
            for item in data_types.get('data', []):
                guid = item.get('guid')
                description = item.get('description') or item.get('name') or ''
                if not guid or not description:
                    _logger.warning("ISLR Sync: Retention type item incompleto, se omite: %s", item)
                    continue

                existing = RetentionType.search([('guid', '=', guid)], limit=1)
                vals = {
                    'guid': guid,
                    'description': description,
                }
                if existing:
                    existing.write(vals)
                else:
                    RetentionType.create(vals)
            _logger.info("ISLR Sync: Retention types synced.")

    except Exception as e:
        _logger.warning(f"ISLR Sync: Failed to sync master data: {e}. The system will continue.")
