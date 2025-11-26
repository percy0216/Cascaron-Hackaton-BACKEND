import xmlrpc.client
import datetime

class OdooClient:
    def __init__(self):
        # TUS DATOS (Ya los tenías bien, asegúrate que sean estos)
        self.url = 'http://18.221.230.36:8069' 
        self.db = 'erpcrm_db'
        self.username = '2019110453@udh.edu.pe'
        self.password = 'admin123'
        
        self.common = xmlrpc.client.ServerProxy(f'{self.url}/xmlrpc/2/common')
        self.models = xmlrpc.client.ServerProxy(f'{self.url}/xmlrpc/2/object')
        self.uid = None

    def conectar(self):
        try:
            self.uid = self.common.authenticate(self.db, self.username, self.password, {})
            return True if self.uid else False
        except:
            return False

    def crear_producto(self, producto_django):
        if not self.uid: self.conectar()
        try:
            id = self.models.execute_kw(self.db, self.uid, self.password, 'product.product', 'create', [{
                'name': producto_django.nombre,
                'list_price': float(producto_django.precio_venta),     
                'standard_price': float(producto_django.costo_unitario),
                'type': 'consu',
            }])
            return id
        except: return None

    # --- NUEVA FUNCIÓN: CREAR FACTURA ---
    def crear_factura(self, items_venta):
        """
        items_venta es una lista: [{'odoo_id': 43, 'qty': 2, 'price': 250.0}]
        """
        if not self.uid: self.conectar()
        
        try:
            # 1. Buscar un cliente genérico (Para la hackathon usamos el ID 1 o creamos uno rápido)
            # Usaremos el ID 1 (Suele ser el admin o la propia empresa) o un partner genérico
            partner_id = 1 
            
            # 2. Preparar las líneas de la factura
            invoice_lines = []
            for item in items_venta:
                # Odoo necesita (0, 0, {datos}) para crear líneas hijas
                line = (0, 0, {
                    'product_id': item['odoo_id'],
                    'quantity': item['qty'],
                    'price_unit': item['price'],
                })
                invoice_lines.append(line)

            # 3. Crear la Factura (Account Move)
            factura_id = self.models.execute_kw(self.db, self.uid, self.password, 'account.move', 'create', [{
                'move_type': 'out_invoice', # Tipo: Factura de Cliente
                'partner_id': partner_id,   # Cliente
                'invoice_date': str(datetime.date.today()),
                'invoice_line_ids': invoice_lines,
            }])
            
            # 4. (Opcional) Publicar la factura para que no esté en borrador
            # self.models.execute_kw(self.db, self.uid, self.password, 'account.move', 'action_post', [[factura_id]])
            
            print(f"📄 FACTURA CREADA EN ODOO ID: {factura_id}")
            return factura_id
            
        except Exception as e:
            print(f"❌ Error creando factura Odoo: {e}")
            return None