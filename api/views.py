from rest_framework import viewsets, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db import transaction
from django.db.models import Sum, F
from django.utils import timezone
from datetime import timedelta

# Importamos tus modelos y serializers
from .models import Producto, Venta, DetalleVenta, Empresa
from .serializers import ProductoSerializer, VentaSerializer
from .odoo_service import OdooClient

# =================================================
# 1. GESTIÓN DE PRODUCTOS (INVENTARIO + ODOO)
# =================================================
class ProductoViewSet(viewsets.ModelViewSet):
    queryset = Producto.objects.all().order_by('-id')
    serializer_class = ProductoSerializer

    def perform_create(self, serializer):
        producto = serializer.save()
        try:
            # Sincronización automática al crear producto
            client = OdooClient()
            odoo_id = client.crear_producto(producto)
            if odoo_id:
                producto.odoo_id = odoo_id
                producto.save()
                print(f"✅ Sincronizado con Odoo (ID: {odoo_id})")
        except Exception as e:
            print(f"❌ Error Odoo: {e}")

# =================================================
# 2. LISTADO DE VENTAS
# =================================================
class VentaViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Venta.objects.all().order_by('-fecha')
    serializer_class = VentaSerializer

# =================================================
# 3. REGISTRAR VENTA (CON DESCUENTO + FACTURA ODOO)
# =================================================
class RegistrarVentaView(APIView):
    def post(self, request):
        data = request.data
        try:
            with transaction.atomic():
                # A. Validaciones básicas
                if 'producto_id' not in data:
                    return Response({"error": "Falta producto_id"}, status=400)
                
                prod = Producto.objects.get(id=data['producto_id'])
                cantidad = int(data['cantidad'])
                tipo_venta = data.get('tipo', 'MENOR')

                # B. Validar Stock
                if prod.stock_actual < cantidad:
                    return Response({"error": f"Stock insuficiente. Quedan {prod.stock_actual}"}, status=400)

                # C. Calcular Precio (Lógica Mayorista 5%)
                precio_base = float(prod.precio_venta)
                if tipo_venta == 'MAYOR':
                    precio_final_unitario = precio_base * 0.95 
                else:
                    precio_final_unitario = precio_base

                total_calculado = precio_final_unitario * cantidad

                # D. Crear Venta en BD Local
                venta = Venta.objects.create(
                    total_venta=total_calculado,
                    ganancia_total=(precio_final_unitario - float(prod.costo_unitario)) * cantidad
                )

                # E. Crear Detalle
                DetalleVenta.objects.create(
                    venta=venta,
                    producto=prod,
                    cantidad=cantidad,
                    precio_unitario=precio_final_unitario,
                    subtotal=total_calculado
                )

                # F. Descontar Stock
                prod.stock_actual -= cantidad
                prod.save()

                # ---------------------------------------------------------
                # G. INTEGRACIÓN ODOO: CREAR FACTURA AUTOMÁTICA EN LA NUBE
                # ---------------------------------------------------------
                try:
                    if prod.odoo_id:
                        client = OdooClient()
                        # Preparamos los datos para la factura
                        items_factura = [{
                            'odoo_id': prod.odoo_id,
                            'qty': cantidad,
                            'price': precio_final_unitario
                        }]
                        # Enviamos a AWS
                        client.crear_factura(items_factura)
                        print("✅ Factura enviada a Odoo AWS")
                except Exception as e:
                    print(f"⚠️ Venta guardada local, pero falló Odoo: {e}")

                return Response({"mensaje": "Venta registrada", "id": venta.id}, status=201)
                
        except Producto.DoesNotExist:
            return Response({"error": "El producto no existe"}, status=404)
        except Exception as e:
            return Response({"error": str(e)}, status=400)

# =================================================
# 4. DASHBOARD
# =================================================
# backend/api/views.py (Solo la clase DashboardView)

class DashboardView(APIView):
    def get(self, request):
        hoy = timezone.now().date()
        qs = Venta.objects.filter(fecha__date=hoy)
        
        # --- LÓGICA DE STOCK MEJORADA ---
        stock_bajos_qs = Producto.objects.filter(stock_actual__lte=F('stock_minimo'))
        stock_bajo_count = stock_bajos_qs.count()
        # Obtenemos los nombres de los primeros 3 productos en peligro
        low_stock_names = list(stock_bajos_qs.values_list('nombre', flat=True)[:3])
        
        total = qs.aggregate(Sum('total_venta'))['total_venta__sum'] or 0
        ganancia = qs.aggregate(Sum('ganancia_total'))['ganancia_total__sum'] or 0
        
        return Response({
            "kpis": {
                "ventas_hoy": f"S/ {total:.2f}",
                "ganancia_hoy": f"S/ {ganancia:.2f}",
                "pedidos_hoy": qs.count(),
                "productos_stock_bajo": stock_bajo_count,
                "low_stock_names": low_stock_names, # <--- NUEVO CAMPO
            },
            "sunat": { "estado": "🟢 En Rango" if total < 5000 else "🟡 Cuidado (Límite RUS)", "mensaje": "Proyección fiscal controlada." }
        })

# =================================================
# 5. CHATBOT SUNAT (CÁLCULO REAL)
# =================================================
class ChatbotView(APIView):
    def post(self, request):
        mensaje = request.data.get('mensaje', '').lower()
        empresa = Empresa.objects.first()
        
        respuesta = "🤖 Soy TaxBot. Pregúntame: 'impuesto hoy', 'deuda' o 'stock'."
        
        if not empresa:
            return Response({"bot_response": "⚠️ Error: Configura tu Empresa en el Admin."})

        # --- A. CÁLCULO DE IMPUESTOS SOBRE VENTAS REALES ---
        if 'impuesto' in mensaje or 'cuanto pago' in mensaje:
            # 1. Buscar ventas de HOY en la BD
            hoy = timezone.now().date()
            total_ventas = Venta.objects.filter(fecha__date=hoy).aggregate(Sum('total_venta'))['total_venta__sum'] or 0
            total_ventas = float(total_ventas)

            if total_ventas == 0:
                respuesta = "📉 Aún no tienes ventas hoy para calcular impuestos. ¡Vende algo primero!"
            else:
                # Simulación RUS
                if total_ventas <= 5000:
                    cuota = 20
                    cat = "Categoría 1"
                else:
                    cuota = 50
                    cat = "Categoría 2"
                
                respuesta = (
                    f"📊 **Análisis Fiscal de Hoy:**\n"
                    f"Ventas del día: **S/ {total_ventas:.2f}**\n"
                    f"Régimen: Nuevo RUS ({cat})\n"
                    f"----------------------------------\n"
                    f"💰 **Pago Estimado SUNAT: S/ {cuota}.00**\n"
                    f"✅ Todo en orden."
                )

        # --- B. CONSULTA DE STOCK INTELIGENTE ---
        elif 'stock' in mensaje:
            # Limpiamos palabras comunes para buscar el nombre del producto
            busqueda = mensaje.replace('stock', '').replace('alerta', '').replace('ver', '').replace('de', '').strip()
            
            if busqueda:
                # Búsqueda específica
                productos = Producto.objects.filter(nombre__icontains=busqueda)
                if productos.exists():
                    lista = ""
                    for p in productos[:3]:
                        estado = "✅" if p.stock_actual > p.stock_minimo else "⚠️ Bajo"
                        lista += f"\n📦 {p.nombre}: **{p.stock_actual}** ({estado})"
                    respuesta = f"🔍 **Stock de '{busqueda}':**{lista}"
                else:
                    respuesta = f"🚫 No encontré productos llamados '{busqueda}'."
            else:
                # Búsqueda general (si no escribe nombre)
                bajos = Producto.objects.filter(stock_actual__lte=F('stock_minimo'))
                count = bajos.count()
                if count > 0:
                    respuesta = f"⚠️ ALERTA: Tienes {count} productos con stock crítico."
                else:
                    respuesta = "✅ Todo tu inventario tiene stock suficiente."

        # --- C. DEUDA HISTÓRICA ---
        elif 'deuda' in mensaje:
            if empresa.deuda_historica_sunat > 0:
                respuesta = f"🚨 ALERTA: Tienes una deuda coactiva de **S/ {empresa.deuda_historica_sunat}**.\nRUC: {empresa.ruc}"
            else:
                respuesta = "✅ Estás 100% limpio con la SUNAT."

        elif 'ventas' in mensaje:
             hoy = timezone.now().date()
             total = Venta.objects.filter(fecha__date=hoy).aggregate(Sum('total_venta'))['total_venta__sum'] or 0
             respuesta = f"💰 Has vendido **S/ {total:.2f}** hoy."

        return Response({"bot_response": respuesta})