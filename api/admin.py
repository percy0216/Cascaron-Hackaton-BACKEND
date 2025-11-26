from django.contrib import admin
from .models import Empresa, Producto, Venta, DetalleVenta

# Esto hace que aparezcan en la web
admin.site.register(Empresa)
admin.site.register(Producto)
admin.site.register(Venta)
admin.site.register(DetalleVenta)