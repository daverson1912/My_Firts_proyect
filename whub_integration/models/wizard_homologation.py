import json
import requests
import logging
import concurrent.futures
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.modules.module import get_module_resource

_logger = logging.getLogger(__name__)

# ==========================================================================================
# MIXIN PARA LÍNEAS / LINE MIXIN
# ==========================================================================================
class WHubLineMixin(models.AbstractModel):
    """ Campos comunes para todas las líneas de homologación """
    _name = 'whub.line.mixin'
    _description = 'WHub Line Mixin'
    
    is_selected = fields.Boolean('Seleccionado', default=False)
    match_found = fields.Boolean('Coincidencia Encontrada', default=False)

# ==========================================================================================
# MODELOS DE LÍNEAS / LINE MODELS
# ==========================================================================================
class WHubHomologationCategoryLine(models.Model):
    _name = 'whub.homologation.category.line'
    _inherit = 'whub.line.mixin'
    _description = 'Línea de Homologación de Categorías'
    wizard_id = fields.Many2one('whub.homologation.wizard', ondelete='cascade')
    whub_category_name = fields.Char('Categoría WispHub')
    odoo_category_id = fields.Many2one('product.category', string='Categoría Odoo')

class WHubHomologationProductLine(models.Model):
    _name = 'whub.homologation.product.line'
    _inherit = 'whub.line.mixin'
    _description = 'Línea de Homologación de Productos'
    wizard_id = fields.Many2one('whub.homologation.wizard', ondelete='cascade')
    whub_product_name = fields.Char('Producto WispHub')
    whub_product_id = fields.Char('ID WispHub')
    whub_description = fields.Char('Descripción WispHub')
    whub_category_name = fields.Char('Categoría WispHub')
    whub_price = fields.Float('Precio WispHub')
    odoo_product_id = fields.Many2one('product.product', string='Producto Odoo')
    odoo_product_categ_name = fields.Char(string='Categoría Odoo', compute='_compute_odoo_categ')

    @api.depends('odoo_product_id')
    def _compute_odoo_categ(self):
        for rec in self:
            rec.odoo_product_categ_name = rec.odoo_product_id.categ_id.name if rec.odoo_product_id else ''

class WHubHomologationPlanLine(models.Model):
    _name = 'whub.homologation.plan.line'
    _inherit = 'whub.line.mixin'
    _description = 'Línea de Homologación de Planes'
    wizard_id = fields.Many2one('whub.homologation.wizard', ondelete='cascade')
    whub_plan_name = fields.Char('Plan WispHub')
    whub_plan_id = fields.Char('ID WispHub')
    whub_category_name = fields.Char('Categoría WispHub')
    whub_price = fields.Float('Precio WispHub')
    whub_type = fields.Selection([('Internet', 'Internet'), ('Adicional', 'Adicional')], string='Tipo', readonly=True)
    odoo_product_id = fields.Many2one('product.product', string='Producto Odoo')
    odoo_product_categ_name = fields.Char(string='Categoría Odoo', compute='_compute_odoo_categ')

    @api.depends('odoo_product_id')
    def _compute_odoo_categ(self):
        for rec in self:
            rec.odoo_product_categ_name = rec.odoo_product_id.categ_id.name if rec.odoo_product_id else ''

class WHubHomologationCustomerLine(models.Model):
    _name = 'whub.homologation.customer.line'
    _inherit = 'whub.line.mixin'
    _description = 'Línea de Homologación de Clientes'
    wizard_id = fields.Many2one('whub.homologation.wizard', ondelete='cascade')
    whub_customer_name = fields.Char('Cliente WispHub')
    whub_customer_id = fields.Char('ID WispHub')
    whub_fiscal_id = fields.Char('Cédula/RIF')
    whub_person_type = fields.Char('Tipo de Persona')
    whub_phone = fields.Char('Teléfono WispHub')
    whub_email = fields.Char('Email WispHub')
    whub_address = fields.Char('Dirección WispHub')
    odoo_partner_id = fields.Many2one('res.partner', string='Contacto Odoo')

# ==========================================================================================
# WIZARD PRINCIPAL / MAIN WIZARD
# ==========================================================================================
class WHubHomologationWizard(models.Model):
    _name = 'whub.homologation.wizard'
    _description = 'Asistente de Homologación WispHub'
    _rec_name = 'whub_title'

    whub_title = fields.Char(default='Espacio de Homologación', readonly=True)

    # Relaciones / Relations
    category_line_ids = fields.One2many('whub.homologation.category.line', 'wizard_id', string='Categorías')
    product_line_ids = fields.One2many('whub.homologation.product.line', 'wizard_id', string='Productos')
    plan_line_ids = fields.One2many('whub.homologation.plan.line', 'wizard_id', string='Planes')
    customer_line_ids = fields.One2many('whub.homologation.customer.line', 'wizard_id', string='Clientes')
    
    company_id = fields.Many2one('res.company', string='Compañía', default=lambda self: self.env.company)
    active_section = fields.Selection([('category', 'Categorías'), ('product', 'Productos'), ('plan', 'Planes'), ('customer', 'Clientes')], default='category')

    # Búsqueda / Search
    search_cat = fields.Char('Buscar Categoría')
    search_prod = fields.Char('Buscar Producto')
    search_plan = fields.Char('Buscar Plan')
    search_cust = fields.Char('Buscar Cliente')

    # Indicador de selección activa / Active selection indicator
    has_selection = fields.Boolean(compute='_compute_has_selection', store=False)
    
    @api.depends(
        'active_section',
        'category_line_ids.is_selected',
        'product_line_ids.is_selected',
        'plan_line_ids.is_selected',
        'customer_line_ids.is_selected'
    )
    def _compute_has_selection(self):
        for rec in self:
            field_map = {
                'category': rec.category_line_ids,
                'product':  rec.product_line_ids,
                'plan':     rec.plan_line_ids,
                'customer': rec.customer_line_ids,
            }
            lines = field_map.get(rec.active_section)
            rec.has_selection = bool(lines and any(l.is_selected for l in lines))

    # Líneas Filtradas / Filtered Lines
    filtered_category_line_ids = fields.One2many('whub.homologation.category.line', compute='_compute_filtered_lines', inverse='_inverse_filtered_lines')
    filtered_product_line_ids = fields.One2many('whub.homologation.product.line', compute='_compute_filtered_lines', inverse='_inverse_filtered_lines')
    filtered_plan_line_ids = fields.One2many('whub.homologation.plan.line', compute='_compute_filtered_lines', inverse='_inverse_filtered_lines')
    filtered_customer_line_ids = fields.One2many('whub.homologation.customer.line', compute='_compute_filtered_lines', inverse='_inverse_filtered_lines')

    def _inverse_filtered_lines(self): pass

    @api.depends('search_cat', 'search_prod', 'search_plan', 'search_cust', 
                 'category_line_ids', 'product_line_ids', 'plan_line_ids', 'customer_line_ids')
    def _compute_filtered_lines(self):
        """ Lógica centralizada de filtrado / Centralized filtering logic """
        for rec in self:
            rec.filtered_category_line_ids = rec.category_line_ids.filtered(lambda l: not rec.search_cat or rec.search_cat.lower() in (l.whub_category_name or '').lower())
            rec.filtered_product_line_ids = rec.product_line_ids.filtered(lambda l: not rec.search_prod or rec.search_prod.lower() in (l.whub_product_name or '').lower())
            rec.filtered_plan_line_ids = rec.plan_line_ids.filtered(lambda l: not rec.search_plan or rec.search_plan.lower() in (l.whub_plan_name or '').lower())
            rec.filtered_customer_line_ids = rec.customer_line_ids.filtered(
                lambda l: not rec.search_cust
                or rec.search_cust.lower() in (l.whub_customer_name or '').lower()
                or rec.search_cust.lower() in (l.whub_fiscal_id or '').lower()
                or rec.search_cust.lower() in (l.whub_person_type or '').lower()
            )

    # ----------------------------------------------------------------------------------
    # HELPER: MAPEAR TIPO DE PERSONA DE WISPHUB A company_type DE ODOO
    # ----------------------------------------------------------------------------------
    def _map_whub_person_type(self, value):
        text = (value or '').strip().lower()
        if not text:
            return False
        juridical_tokens = ['jurid', 'empresa', 'compañ', 'compania', 'corpor', 'moral']
        natural_tokens = ['fisic', 'natural', 'persona']
        if any(token in text for token in juridical_tokens):
            return 'company'
        if any(token in text for token in natural_tokens):
            return 'person'
        return False

    # Fechas de sincronización (Delegadas directamente a res.company)
    sync_cat = fields.Datetime(related='company_id.whub_sync_cat', readonly=True)
    sync_prod = fields.Datetime(related='company_id.whub_sync_prod', readonly=True)
    sync_plan = fields.Datetime(related='company_id.whub_sync_plan', readonly=True)
    sync_cust = fields.Datetime(related='company_id.whub_sync_cust', readonly=True)

    # ---------------------------------------------------------
    # ACCIONES / ACTIONS
    # ---------------------------------------------------------

    def dummy(self):
        """ Método vacío para botones que funcionan como etiquetas visuales """
        pass

    def _propagate_category_to_products(self, category_lines):
        """ Reasigna la categoría Odoo homologada a todos los productos/planes de WispHub
        que pertenezcan a esas categorías y ya estén vinculados a un producto Odoo. """
        for l in category_lines.filtered('odoo_category_id'):
            for line_set in (self.product_line_ids, self.plan_line_ids):
                linked_lines = line_set.filtered(
                    lambda p: p.whub_category_name == l.whub_category_name and p.odoo_product_id
                )
                for p in linked_lines:
                    p.odoo_product_id.product_tmpl_id.categ_id = l.odoo_category_id.id

    def action_apply_batch_link(self):
        """ Aplica el vínculo de la cabecera a todos los registros marcados con el check """
        sec = self.active_section
        res_id = False
        if sec == 'category': res_id = self.batch_odoo_category_id.id
        elif sec in ['product', 'plan']: res_id = self.batch_odoo_product_id.id
        elif sec == 'customer': res_id = self.batch_odoo_partner_id.id

        if not res_id:
            raise UserError("Seleccione primero un registro de Odoo en el campo superior para aplicar masivamente.")

        field_map = {
            'category': ('category_line_ids', 'odoo_category_id'),
            'product': ('product_line_ids', 'odoo_product_id'),
            'plan': ('plan_line_ids', 'odoo_product_id'),
            'customer': ('customer_line_ids', 'odoo_partner_id'),
        }
        f_name, o_attr = field_map[sec]
        lines = self[f_name].filtered(lambda l: l.is_selected)
        
        if not lines:
            raise UserError("No hay registros seleccionados con el check en la tabla.")

        lines.write({o_attr: res_id})

        if sec == 'category':
            self._propagate_category_to_products(lines)

        # Limpiar el campo batch tras aplicar
        self.write({
            'batch_odoo_category_id': False,
            'batch_odoo_product_id': False,
            'batch_odoo_partner_id': False
        })
        
        return self._reopen_self()

    # ---------------------------------------------------------
    # CARGA Y DESCARGA / LOAD AND FETCH
    # ---------------------------------------------------------

    def action_load_wisphub_data(self):
        """ Inicia la descarga síncrona manual (congela la pantalla del usuario) """
        self._execute_sync(self.company_id)
        return self._reopen_self()

    @api.model
    def action_cron_sync_homologation_data(self):
        """ Método del Cron Job: sincroniza silenciosamente las homologaciones de todas las compañías con API Key """
        companies = self.env['res.company'].search([('whub_api_key', '!=', False)])
        for company in companies:
            wizard = self.search([('company_id', '=', company.id)], limit=1)
            if not wizard:
                wizard = self.create({'company_id': company.id})
            try:
                wizard._execute_sync(company)
            except Exception as e:
                _logger.error("Error en la sincronización en segundo plano de catálogos para compañía %s: %s", company.name, e)

    def _execute_sync(self, company):
        """ Lógica interna de sincronización (se ejecuta dentro del hilo) """
        url = (company.whub_middleware_url or '').strip().rstrip('/')
        if not url:
            raise UserError("No se ha configurado la URL del Middleware en los Ajustes de WispHub.")
        
        headers = {'Content-Type': 'application/json'}
        payload = {"auth": {"api_key": company.whub_api_key}}

        # Obtener los IDs ya existentes en las tablas del wizard para no duplicar ni eliminar trabajo
        existing_cats = set(self.category_line_ids.mapped('whub_category_name'))
        existing_prods = set(self.product_line_ids.mapped('whub_product_id'))
        existing_plans = set(self.plan_line_ids.mapped('whub_plan_id'))
        existing_custs = set(self.customer_line_ids.mapped('whub_customer_id'))

        # 1. Artículos y Categorías (Incremental si aplica)
        payload_art = dict(payload)
        if company.whub_sync_prod:
            payload_art['filters'] = {
                'updated_at__gte': company.whub_sync_prod.strftime('%Y-%m-%d %H:%M:%S')
            }
        
        res = requests.post(f"{url}/api/v1/wisphub/articles", json=payload_art, headers=headers, timeout=60)
        data = self._extract_data(res)
        for art in data:
            c_name = art.get('category', 'Sin Categoría')
            if c_name not in existing_cats:
                name_match = self.env['product.category'].search([('name', '=', c_name)], limit=1)
                self.env['whub.homologation.category.line'].create({
                    'wizard_id': self.id,
                    'whub_category_name': c_name,
                    'odoo_category_id': False,
                    'match_found': bool(name_match)
                })
                existing_cats.add(c_name)
            
            w_id = str(art.get('id', ''))
            desc = art.get('description') or art.get('descripcion') or ''
            price = float(art.get('price') or 0.0)
            name = art.get('name')
            
            if w_id in existing_prods:
                existing_line = self.product_line_ids.filtered(lambda l: l.whub_product_id == w_id)
                if existing_line:
                    existing_line.write({
                        'whub_description': desc,
                        'whub_product_name': name,
                        'whub_category_name': c_name,
                        'whub_price': price,
                    })
                continue
            existing_prods.add(w_id)
            
            prod_odoo = self._find_odoo_record('product.product', 'whub_product_id', w_id)
            name_match = self.env['product.product'].search([('name', '=', name), ('whub_product_id', 'in', [False, ''])], limit=1) if not prod_odoo else None
            self.env['whub.homologation.product.line'].create({
                'wizard_id': self.id,
                'whub_product_name': name,
                'whub_product_id': w_id,
                'whub_description': desc,
                'whub_category_name': c_name,
                'whub_price': price,
                'odoo_product_id': prod_odoo.id if prod_odoo else False,
                'match_found': bool(not prod_odoo and name_match)
            })

        # 2. Planes e Internet (Incremental si aplica)
        payload_plan = dict(payload)
        if company.whub_sync_plan:
            payload_plan['filters'] = {
                'updated_at__gte': company.whub_sync_plan.strftime('%Y-%m-%d %H:%M:%S')
            }
        
        self._sync_simple(url, "/api/v1/wisphub/plans", 'whub.homologation.plan.line', 'whub_plan_id', 'product.product', payload_plan, headers, extra={'whub_type': 'Internet', 'whub_category_name': 'Planes Internet'}, existing_set=existing_plans, fetch_price=True)
        self._sync_simple(url, "/api/v1/wisphub/additional-plans", 'whub.homologation.plan.line', 'whub_plan_id', 'product.product', payload_plan, headers, extra={'whub_type': 'Adicional', 'whub_category_name': 'Planes Adicionales'}, existing_set=existing_plans, fetch_price=True)
        
        # 3. Clientes (Incremental si aplica)
        payload_cust = dict(payload)
        if company.whub_sync_cust:
            payload_cust['filters'] = {
                'updated_at__gte': company.whub_sync_cust.strftime('%Y-%m-%d %H:%M:%S')
            }
        self._sync_customers(url, payload_cust, headers, existing_set=existing_custs)
        
        # Actualizar fechas de sincronización
        self._update_sync_dates('all')

    def _update_sync_dates(self, section='all'):
        """ Actualiza las fechas de sincronización en res.company """
        now = fields.Datetime.now()
        vals = {'whub_sync_date': now}
        if section == 'all':
            vals.update({
                'whub_sync_cat': now,
                'whub_sync_prod': now,
                'whub_sync_plan': now,
                'whub_sync_cust': now,
            })
        else:
            suffix = 'cat' if section == 'category' else section[:4]
            vals[f'whub_sync_{suffix}'] = now
        self.env.company.write(vals)

    def _get_plan_price(self, url, plan_id, payload, headers):
        """ Obtiene el precio de un plan individual llamando a /api/v1/wisphub/plans/detail """
        try:
            detail_payload = dict(payload)
            detail_payload['plan_id'] = plan_id
            res = requests.post(f"{url}/api/v1/wisphub/plans/detail", json=detail_payload, headers=headers, timeout=30)
            if res.status_code in [200, 201]:
                data = self._extract_data(res)
                if isinstance(data, dict):
                    return float(data.get('price') or 0.0)
                elif isinstance(data, list) and len(data) > 0:
                    return float(data[0].get('price') or 0.0)
            _logger.warning(f"Failed to get price for plan_id {plan_id}: status {res.status_code}")
            return 0.0
        except Exception as e:
            _logger.warning(f"Error getting price for plan_id {plan_id}: {str(e)}")
            return 0.0

    def _sync_simple(self, url, route, line_model, id_field, odoo_model, payload, headers, extra=None, existing_set=None, fetch_price=False):
        """ Helper para sincronización simple / Simple sync helper
        
        Args:
            fetch_price: Si True, obtiene el precio llamando a /api/v1/wisphub/plans/detail por cada registro
        """
        if existing_set is None: existing_set = set()
        res = requests.post(f"{url}{route}", json=payload, headers=headers)
        if res.status_code not in [200, 201]: return
        data = self._extract_data(res)

        new_records = [d for d in data if str(d.get('id', '')) not in existing_set]

        # Obtener precios en paralelo para evitar una petición secuencial por cada plan
        prices_by_id = {}
        if fetch_price and new_records:
            ids_to_fetch = [str(d.get('id', '')) for d in new_records]
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                futures = {
                    executor.submit(self._get_plan_price, url, w_id, payload, headers): w_id
                    for w_id in ids_to_fetch
                }
                for future in concurrent.futures.as_completed(futures):
                    prices_by_id[futures[future]] = future.result()

        for d in new_records:
            w_id = str(d.get('id', ''))
            existing_set.add(w_id)

            name = d.get('name', '')
            # Solo vincula si ya tiene el ID de WispHub registrado (homologación previa).
            odoo_rec = self._find_odoo_record(odoo_model, 'whub_product_id', w_id)
            name_match = self.env[odoo_model].search([('name', '=', name), ('whub_product_id', 'in', [False, ''])], limit=1) if not odoo_rec else None

            # Obtener precio: del listado original o del resultado paralelo del endpoint de detalle
            if fetch_price:
                price = prices_by_id.get(w_id, 0.0)
            else:
                price = float(d.get('price') or 0.0)
            
            vals = {
                'wizard_id': self.id,
                'whub_plan_name': name,
                'whub_price': price,
                id_field: w_id,
                'odoo_product_id': odoo_rec.id if odoo_rec else False,
                'match_found': bool(not odoo_rec and name_match)
            }
            if extra: vals.update(extra)
            self.env[line_model].create(vals)

    def _sync_customers(self, url, payload, headers, existing_set=None):
        """ Sincronización de clientes con paginación / Customer sync (paginated) """
        if existing_set is None: existing_set = set()

        company = self.env.company
        page_size = company.whub_customers_page_size or 200
        max_pages = company.whub_customers_max_pages or 50

        offset = 0
        page_count = 0
        total_customers_added = 0
        total_customers_skipped = 0
        
        _logger.info(f"Starting customer sync: page_size={page_size}, max_pages={max_pages}")
        
        while page_count < max_pages:
            page_payload = dict(payload)
            page_payload['filters'] = {
                **(payload.get('filters') or {}),
                'limit': page_size,
                'offset': offset,
            }

            res = requests.post(
                f"{url}/api/v1/wisphub/customers",
                json=page_payload,
                headers=headers,
            )
            if res.status_code not in [200, 201]:
                _logger.warning(f"Failed to fetch customers page {page_count}: status {res.status_code}")
                return

            data = self._extract_data(res)
            if not data:
                _logger.info(f"No more customers found at page {page_count}, offset {offset}")
                _logger.info(f"Customer sync completed: {total_customers_added} added, {total_customers_skipped} skipped, {page_count} pages processed")
                return

            _logger.info(f"Page {page_count}: {len(data)} records received (offset: {offset})")
            
            # Si recibimos menos registros que el page_size, es la última página
            if len(data) < page_size:
                _logger.info(f"Last page reached: {len(data)} records (page_size: {page_size})")
            
            page_added = 0
            page_skipped = 0
            page_refreshed = 0

            for c in data:
                # WispHub usa el username/user como identificador en los Avisos de Cobro (Invoices),
                # por lo que debemos priorizarlo sobre el ID numérico interno para que la homologación funcione.
                w_id = str(c.get('username') or c.get('user') or c.get('id', ''))
                if not w_id:
                    page_skipped += 1
                    _logger.warning(f"Skipping customer with no username/user/id: {c}")
                    continue

                name = c.get('full_name') or c.get('name') or c.get('username')
                contact = c.get('contact') or {}
                line_vals = {
                    'whub_customer_name': name,
                    'whub_fiscal_id': c.get('fiscal_id'),
                    'whub_person_type': c.get('person_type'),
                    'whub_phone': contact.get('phone'),
                    'whub_email': contact.get('email'),
                    'whub_address': c.get('address'),
                }

                if w_id in existing_set:
                    # Ya existe en este wizard: refrescar sus datos (tel/email/etc. pueden
                    # haber estado vacíos en una sincronización anterior). No se toca el
                    # vínculo de homologación (odoo_partner_id) que ya tenga.
                    existing_line = self.customer_line_ids.filtered(lambda l: l.whub_customer_id == w_id)
                    if existing_line:
                        existing_line.write(line_vals)
                        page_refreshed += 1
                    continue
                existing_set.add(w_id)

                c_odoo = self._find_odoo_record('res.partner', 'whub_customer_id', w_id)
                name_match = self.env['res.partner'].search([('name', '=', name), ('whub_customer_id', 'in', [False, ''])], limit=1) if not c_odoo else None
                line_vals.update({
                    'wizard_id': self.id,
                    'whub_customer_id': w_id,
                    'odoo_partner_id': c_odoo.id if c_odoo else False,
                    'match_found': bool(not c_odoo and name_match)
                })
                self.env['whub.homologation.customer.line'].create(line_vals)
                page_added += 1
            
            total_customers_added += page_added
            total_customers_skipped += page_skipped
            _logger.info(f"Page {page_count} processed: {page_added} added, {page_refreshed} refreshed, {page_skipped} skipped")

            # Si recibimos menos registros que el page_size, terminamos
            if len(data) < page_size:
                _logger.info(f"Customer sync completed: {total_customers_added} added, {total_customers_skipped} skipped, {page_count + 1} pages processed")
                return
            
            offset += page_size
            page_count += 1
        
        _logger.warning(f"Reached max_pages limit ({max_pages}) without completing sync. Total: {total_customers_added} added, {total_customers_skipped} skipped")

    # Eliminados _get_global_config y helpers obsoletos de configuración

    def _extract_data(self, response):
        """ Extractor genérico de JSON / Generic JSON extractor """
        try: d = response.json()
        except: raise UserError("Respuesta no válida.")
        if isinstance(d, dict) and d.get('error'): raise UserError(f"API Error: {d.get('message')}")
        if isinstance(d, list): return d
        return d.get('data', {}).get('records') or d.get('records') or self._find_records(d)

    def _find_records(self, node):
        """ Búsqueda recursiva / Recursive search """
        if isinstance(node, dict):
            if 'records' in node: return node['records']
            for v in node.values():
                if isinstance(v, (dict, list)):
                    res = self._find_records(v)
                    if res: return res
        return []

    # ---------------------------------------------------------
    # GUARDADO Y CREACIÓN / SAVE AND CREATE
    # ---------------------------------------------------------

    def action_apply_mapping(self):
        """ Guarda los cambios en Odoo / Saves changes to Odoo """
        self._propagate_category_to_products(self.category_line_ids)
        for l in self.product_line_ids.filtered('odoo_product_id'):
            self._append_whub_id(l.odoo_product_id.product_tmpl_id, 'whub_product_id', l.whub_product_id)
        for l in self.plan_line_ids.filtered('odoo_product_id'): 
            self._append_whub_id(l.odoo_product_id.product_tmpl_id, 'whub_product_id', l.whub_plan_id)
            l.odoo_product_id.type = 'service'
        for l in self.customer_line_ids.filtered('odoo_partner_id'):
            self._append_whub_id(l.odoo_partner_id, 'whub_customer_id', l.whub_customer_id)
            self._fill_missing_partner_data(l.odoo_partner_id, l.whub_fiscal_id, l.whub_phone, l.whub_email, l.whub_address)
            mapped_type = self._map_whub_person_type(l.whub_person_type)
            if mapped_type:
                l.odoo_partner_id.write({
                    'company_type': mapped_type,
                    'is_company': mapped_type == 'company'
                })
        
        now = fields.Datetime.now()
        # Ajustar nombre de campo: category -> cat, los demás (prod, plan, cust) usan 4 letras
        suffix = 'cat' if self.active_section == 'category' else self.active_section[:4]
        vals = {'whub_sync_date': now, f'whub_sync_{suffix}': now}
        self.env.company.write(vals)

        # Reprocesar logs automáticamente tras homologar
        self.env['whub.notice.sync.log']._auto_reprocess_failed_logs(self.company_id.id)
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Éxito'),
                'message': _('Los vínculos se han guardado correctamente en los registros de Odoo.'),
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'}
            }
        }

    def action_open_batch_homologation(self):
        """ Abre el popup para homologar registros seleccionados """
        sec = self.active_section or 'category'
        lines = self[f'{sec}_line_ids'].filtered(lambda l: l.is_selected and not (l.odoo_category_id if sec == 'category' else l.odoo_product_id if sec in ['product', 'plan'] else l.odoo_partner_id))
        
        if not lines:
            raise UserError(_("Seleccione al menos un registro para homologar."))

        batch_vals = []
        for l in lines:
            name = l.whub_category_name if sec == 'category' else l.whub_product_name if sec == 'product' else l.whub_plan_name if sec == 'plan' else l.whub_customer_name
            w_id = l.whub_category_name if sec == 'category' else l.whub_product_id if sec == 'product' else l.whub_plan_id if sec == 'plan' else l.whub_customer_id
            desc = l.whub_description if sec == 'product' else ''
            batch_vals.append((0, 0, {
                'res_type': sec,
                'name': name,
                'whub_id': w_id,
                'whub_description': desc,
                'source_line_id': f"{sec[:4]}_{l.id}"
            }))
        
        new_wiz = self.env['whub.homologation.batch.wizard'].create({'parent_wizard_id': self.id, 'res_type': sec, 'line_ids': batch_vals})
        return {'name': 'Relacionar Registros', 'type': 'ir.actions.act_window', 'res_model': 'whub.homologation.batch.wizard', 'res_id': new_wiz.id, 'view_mode': 'form', 'target': 'new'}

    def action_create_selected(self):
        """ Prepara wizard de creación basado en la selección actual """
        sec = self.active_section or 'category'
        # Filtramos por seleccionados Y que no tengan vínculo en Odoo
        lines = self[f'{sec}_line_ids'].filtered(lambda l: l.is_selected and not (l.odoo_category_id if sec == 'category' else l.odoo_product_id if sec in ['product', 'plan'] else l.odoo_partner_id))
        
        if not lines:
            raise UserError(_("Seleccione al menos un registro para crear en Odoo."))
        
        batch_vals = []
        for l in lines:
            name = l.whub_category_name if sec == 'category' else l.whub_product_name if sec == 'product' else l.whub_plan_name if sec == 'plan' else l.whub_customer_name
            w_id = l.whub_category_name if sec == 'category' else l.whub_product_id if sec == 'product' else l.whub_plan_id if sec == 'plan' else l.whub_customer_id
            desc = l.whub_description if sec == 'product' else ''
            batch_vals.append((0, 0, {
                'res_type': sec,
                'name': name,
                'whub_id': w_id,
                'whub_description': desc,
                'source_line_id': f"{sec[:4]}_{l.id}"
            }))
        
        new_wiz = self.env['whub.creation.selection.wizard'].create({'parent_wizard_id': self.id, 'line_ids': batch_vals})
        return {'name': 'Creación Individual', 'type': 'ir.actions.act_window', 'res_model': 'whub.creation.selection.wizard', 'res_id': new_wiz.id, 'view_mode': 'form', 'target': 'new'}

    def _reopen_self(self):
        return {'name': 'Homologación', 'type': 'ir.actions.act_window', 'res_model': 'whub.homologation.wizard', 'res_id': self.id, 'view_mode': 'form', 'target': 'current'}

    def action_switch_tab(self):
        """ Cambia la pestaña activa guardando el estado """
        sec = self.env.context.get('active_section')
        if sec:
            self.write({'active_section': sec})
        return self._reopen_self()

    def action_toggle_selection_main(self):
        """ Alterna la selección de todas las líneas en la pestaña activa """
        # Priorizar la sección que viene por contexto (desde el botón de la pestaña)
        sec = self.env.context.get('active_section') or self.active_section
        if not sec:
            return self._reopen_self()
            
        field_map = {
            'category': ('category_line_ids', 'odoo_category_id'),
            'product': ('product_line_ids', 'odoo_product_id'),
            'plan': ('plan_line_ids', 'odoo_product_id'),
            'customer': ('customer_line_ids', 'odoo_partner_id'),
        }
        line_field, link_field = field_map[sec]
        all_lines = self[line_field]
        if not all_lines:
            return self._reopen_self()
            
        # SOLO actuamos sobre líneas que NO tienen vínculo en Odoo
        lines_to_toggle = all_lines.filtered(lambda l: not l[link_field])
        # Si todas las pendientes están marcadas, no hacemos nada (ya están marcadas). 
        # Si no, marcamos todas las pendientes.
        lines_to_toggle.write({'is_selected': True})
        return self._reopen_self()

    def action_unmark_all(self):
        """ Desmarca absolutamente todo en la pestaña activa """
        sec = self.env.context.get('active_section') or self.active_section
        field_map = {
            'category': 'category_line_ids',
            'product': 'product_line_ids',
            'plan': 'plan_line_ids',
            'customer': 'customer_line_ids',
        }
        if sec in field_map:
            self[field_map[sec]].write({'is_selected': False})
        return self._reopen_self()

    def action_return_to_settings(self):
        """ Regresa a la pantalla de Ajustes / Returns to Settings screen """
        return self.env.ref('whub_integration.action_whub_config_settings').read()[0]
    
    # ---------------------------------------------------------
    # HELPERS DE MULTI-ID
    # ---------------------------------------------------------

    def _append_whub_id(self, record, field, new_id):
        """Agrega un ID a una lista separada por comas, evitando duplicados."""
        if not record or not new_id: return
        current = (record[field] or '').split(',')
        current = [x.strip() for x in current if x.strip()]
        if new_id not in current:
            current.append(new_id)
            record.write({field: ','.join(current)})

    def _fill_missing_partner_data(self, partner, fiscal_id=None, phone=None, email=None, address=None):
        """ Completa solo los campos vacíos del contacto con los datos de WispHub,
        sin sobrescribir información que el contacto ya tenga en Odoo. """
        if not partner:
            return
        vals = {}
        if fiscal_id and not partner.vat:
            vals['vat'] = fiscal_id
        if phone and not partner.phone:
            vals['phone'] = phone
        if email and not partner.email:
            vals['email'] = email
        if address and not partner.street:
            vals['street'] = address
        if vals:
            partner.write(vals)

    def _find_odoo_record(self, model, field, search_id):
        """Busca un registro por ID dentro de una lista separada por comas."""
        domain = ['|', (field, '=', search_id),
                  '|', (field, '=ilike', f'{search_id},%'),
                  '|', (field, '=ilike', f'%,{search_id}'),
                       (field, '=ilike', f'%,{search_id},%')]
        return self.env[model].search(domain, limit=1)

# ==========================================================================================
# ASISTENTES SECUNDARIOS / SECONDARY WIZARDS
# ==========================================================================================

class WHubHomologationBatchWizard(models.TransientModel):
    _name = 'whub.homologation.batch.wizard'
    _description = 'Selector de Homologación Individual en Masa'
    parent_wizard_id = fields.Many2one('whub.homologation.wizard')
    res_type = fields.Selection([('category', 'Categoría'), ('product', 'Producto'), ('plan', 'Plan'), ('customer', 'Cliente')])
    line_ids = fields.One2many('whub.homologation.batch.line', 'wizard_id')

    def action_confirm_batch_homologation(self):
        """ Aplica los registros seleccionados individualmente en el popup a las tablas base """
        homologated_category_lines = self.env['whub.homologation.category.line']
        for l in self.line_ids:
            tp, sid = l.source_line_id.split('_')
            obj = self.env[f'whub.homologation.{l.res_type}.line'].browse(int(sid))

            if l.res_type == 'category' and l.odoo_category_id:
                obj.odoo_category_id = l.odoo_category_id.id
                homologated_category_lines |= obj
            elif l.res_type == 'product' and l.odoo_product_id:
                obj.odoo_product_id = l.odoo_product_id.id
                self.parent_wizard_id._append_whub_id(l.odoo_product_id.product_tmpl_id, 'whub_product_id', obj.whub_product_id)
            elif l.res_type == 'plan' and l.odoo_plan_id:
                obj.odoo_product_id = l.odoo_plan_id.id
                self.parent_wizard_id._append_whub_id(l.odoo_plan_id.product_tmpl_id, 'whub_product_id', obj.whub_plan_id)
                l.odoo_plan_id.write({'type': 'service'})
            elif l.res_type == 'customer' and l.odoo_partner_id:
                obj.odoo_partner_id = l.odoo_partner_id.id
                self.parent_wizard_id._append_whub_id(l.odoo_partner_id, 'whub_customer_id', obj.whub_customer_id)
                self.parent_wizard_id._fill_missing_partner_data(
                    l.odoo_partner_id, obj.whub_fiscal_id, obj.whub_phone, obj.whub_email, obj.whub_address
                )

        if homologated_category_lines:
            self.parent_wizard_id._propagate_category_to_products(homologated_category_lines)

        self.parent_wizard_id._update_sync_dates(self.res_type)

        # Reprocesar logs automáticamente tras homologar
        self.env['whub.notice.sync.log']._auto_reprocess_failed_logs(self.parent_wizard_id.company_id.id)

        return self.parent_wizard_id._reopen_self()

class WHubHomologationBatchLine(models.TransientModel):
    _name = 'whub.homologation.batch.line'
    wizard_id = fields.Many2one('whub.homologation.batch.wizard')
    res_type = fields.Selection([('category', 'Categoría'), ('product', 'Producto'), ('plan', 'Plan'), ('customer', 'Cliente')])
    name = fields.Char('Nombre')
    whub_id = fields.Char('ID WH')
    whub_description = fields.Char('Descripción WispHub')
    source_line_id = fields.Char('Ref')
    
    # Selectores individuales con filtros de dominio
    # Selectores individuales con filtros de dominio para evitar duplicados
    odoo_category_id = fields.Many2one('product.category')
    odoo_product_id = fields.Many2one('product.product', domain="['|', ('whub_product_id', '=', False), ('whub_product_id', '=', '')]")
    odoo_plan_id = fields.Many2one('product.product', domain="['&', '|', ('whub_product_id', '=', False), ('whub_product_id', '=', ''), ('type', '=', 'service')]")
    odoo_partner_id = fields.Many2one('res.partner', domain="['|', ('whub_customer_id', '=', False), ('whub_customer_id', '=', '')]")

class WHubCreationSelectionWizard(models.TransientModel):
    _name = 'whub.creation.selection.wizard'
    _description = 'Selector de Creación'
    parent_wizard_id = fields.Many2one('whub.homologation.wizard')
    line_ids = fields.One2many('whub.creation.selection.line', 'wizard_id')
    has_product_lines = fields.Boolean(compute='_compute_has_product_lines')

    @api.depends('line_ids.res_type')
    def _compute_has_product_lines(self):
        for rec in self:
            rec.has_product_lines = bool(rec.line_ids.filtered(lambda l: l.res_type == 'product'))

    def _resolve_category(self, whub_category_name):
        """ Devuelve la categoría Odoo homologada para esta categoría de WispHub.
        Si no hay homologación, busca/crea una categoría con el nombre de WispHub. """
        homolog_line = self.parent_wizard_id.category_line_ids.filtered(
            lambda c: c.whub_category_name == whub_category_name and c.odoo_category_id
        )
        if homolog_line:
            return homolog_line[0].odoo_category_id
        return self.env['product.category'].search([('name', '=', whub_category_name)], limit=1) \
            or self.env['product.category'].create({'name': whub_category_name})

    def action_confirm_creation(self):
        """ Ejecuta creación masiva con reporte detallado """
        created_count = 0
        linked_count = 0
        
        for l in self.line_ids.filtered('is_selected'):
            tp, sid = l.source_line_id.split('_')
            obj = self.env[f'whub.homologation.{l.res_type}.line'].browse(int(sid))
            was_linked = False
            
            if tp == 'cate':
                if not obj.odoo_category_id:
                    exist = self.env['product.category'].search([('name', '=', obj.whub_category_name)], limit=1)
                    if exist:
                        obj.odoo_category_id = exist.id
                        was_linked = True
                    else:
                        obj.odoo_category_id = self.env['product.category'].create({'name': obj.whub_category_name}).id
                        created_count += 1
            
            elif tp == 'prod':
                if not obj.odoo_product_id:
                    # Calcular el nombre final según la opción elegida
                    final_name = obj.whub_product_name
                    if l.creation_name_option == 'name_desc':
                        if l.whub_description:
                            final_name = f"{obj.whub_product_name} - {l.whub_description}"
                    elif l.creation_name_option == 'desc':
                        if l.whub_description:
                            final_name = l.whub_description
                    
                    # 1. Búsqueda por ID (Prioridad)
                    exist = self.env['product.product'].search([('whub_product_id', '=', obj.whub_product_id)], limit=1)
                    # 2. Búsqueda por Nombre (Fallback para evitar duplicados si ya existe sin ID)
                    if not exist:
                        exist = self.env['product.product'].search([('name', '=', final_name), ('whub_product_id', 'in', [False, ''])], limit=1)
                    
                    if exist:
                        obj.odoo_product_id = exist.id
                        self.parent_wizard_id._append_whub_id(exist.product_tmpl_id, 'whub_product_id', obj.whub_product_id)
                        was_linked = True
                    else:
                        cat = self._resolve_category(obj.whub_category_name)
                        obj.odoo_product_id = self.env['product.product'].create({
                            'name': final_name,
                            'type': 'consu',
                            'categ_id': cat.id,
                            'lst_price': obj.whub_price,
                            'taxes_id': [(5, 0, 0)],
                            'supplier_taxes_id': [(5, 0, 0)],
                            'whub_product_id': obj.whub_product_id
                        }).id
                        created_count += 1
            
            elif tp == 'plan':
                if not obj.odoo_product_id:
                    # 1. Búsqueda por ID
                    exist = self.env['product.product'].search([('whub_product_id', '=', obj.whub_plan_id)], limit=1)
                    # 2. Búsqueda por Nombre
                    if not exist:
                        exist = self.env['product.product'].search([('name', '=', obj.whub_plan_name), ('whub_product_id', 'in', [False, ''])], limit=1)
                    
                    if exist:
                        obj.odoo_product_id = exist.id
                        self.parent_wizard_id._append_whub_id(exist.product_tmpl_id, 'whub_product_id', obj.whub_plan_id)
                        was_linked = True
                    else:
                        cat = self._resolve_category(obj.whub_category_name)
                        obj.odoo_product_id = self.env['product.product'].create({
                            'name': obj.whub_plan_name,
                            'type': 'service',
                            'categ_id': cat.id,
                            'lst_price': obj.whub_price,
                            'taxes_id': [(5, 0, 0)],
                            'supplier_taxes_id': [(5, 0, 0)],
                            'whub_product_id': obj.whub_plan_id
                        }).id
                        created_count += 1
            
            elif tp == 'cust':
                if not obj.odoo_partner_id:
                    mapped_type = self.parent_wizard_id._map_whub_person_type(obj.whub_person_type)
                    # 1. Búsqueda por ID
                    exist = self.env['res.partner'].search([('whub_customer_id', '=', obj.whub_customer_id)], limit=1)
                    # 2. Búsqueda por Nombre
                    if not exist:
                        exist = self.env['res.partner'].search([('name', '=', obj.whub_customer_name), ('whub_customer_id', 'in', [False, ''])], limit=1)
                    # 3. Búsqueda por RIF/Cédula (para evitar duplicación e impedir fallo de restricción única)
                    if not exist and obj.whub_fiscal_id:
                        normalized_vat = self.env['res.partner']._normalize_vat(obj.whub_fiscal_id)
                        exist = self.env['res.partner'].search([
                            '|', ('vat', '=', obj.whub_fiscal_id),
                            '|', ('vat', '=', normalized_vat),
                            '|', ('vat', '=', obj.whub_fiscal_id.replace('-', '')),
                                 ('vat', '=', normalized_vat.replace('-', ''))
                        ], limit=1)
                    
                    if exist:
                        obj.odoo_partner_id = exist.id
                        self.parent_wizard_id._append_whub_id(exist, 'whub_customer_id', obj.whub_customer_id)
                        self.parent_wizard_id._fill_missing_partner_data(
                            exist, obj.whub_fiscal_id, obj.whub_phone, obj.whub_email, obj.whub_address
                        )
                        if mapped_type:
                            exist.write({
                                'company_type': mapped_type,
                                'is_company': mapped_type == 'company'
                            })
                        was_linked = True
                    else:
                        obj.odoo_partner_id = self.env['res.partner'].create({
                            'name': obj.whub_customer_name,
                            'vat': obj.whub_fiscal_id,
                            'phone': obj.whub_phone,
                            'email': obj.whub_email,
                            'street': obj.whub_address,
                            'whub_customer_id': obj.whub_customer_id,
                            'company_type': mapped_type or 'person',
                            'is_company': False if mapped_type == 'person' else True
                        }).id
                        created_count += 1
            
            if was_linked:
                linked_count += 1

        msg = _("Proceso completado:")
        if created_count > 0:
            msg += _("\n- %s registros creados nuevos.") % created_count
        if linked_count > 0:
            msg += _("\n- %s registros vinculados (ya existían).") % linked_count
        
        # Actualizar fecha de la sección procesada
        sec = self.line_ids[0].res_type if self.line_ids else 'all'
        self.parent_wizard_id._update_sync_dates(sec)

        # Reprocesar logs automáticamente tras homologar
        self.env['whub.notice.sync.log']._auto_reprocess_failed_logs(self.parent_wizard_id.company_id.id)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Resultado de la operación'),
                'message': msg,
                'sticky': False,
                'type': 'success',
                'next': {'type': 'ir.actions.act_window_close'}
            }
        }

    def action_toggle_selection(self):
        self.line_ids.write({'is_selected': not all(self.line_ids.mapped('is_selected'))})
        return {'type': 'ir.actions.act_window', 'res_model': self._name, 'res_id': self.id, 'view_mode': 'form', 'target': 'new'}

    def action_return_to_settings(self): return self.parent_wizard_id._reopen_self()

# Modelos de Vinculación Masiva eliminados por redundancia

class WHubCreationSelectionLine(models.TransientModel):
    _name = 'whub.creation.selection.line'
    wizard_id = fields.Many2one('whub.creation.selection.wizard')
    is_selected = fields.Boolean('Crear', default=True)
    res_type = fields.Selection([('category', 'Categoría'), ('product', 'Producto'), ('plan', 'Plan'), ('customer', 'Cliente')])
    name, whub_id, source_line_id = fields.Char('Nombre'), fields.Char('ID WH'), fields.Char('Ref')
    whub_description = fields.Char('Descripción WispHub')
    creation_name_option = fields.Selection([
        ('name', 'Solo Nombre'),
        ('name_desc', 'Nombre + Descripción'),
        ('desc', 'Solo Descripción')
    ], string='Formato Nombre', default='name', required=True)
