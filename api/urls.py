from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ProductoViewSet, VentaViewSet, DashboardView, ChatbotView, RegistrarVentaView

router = DefaultRouter()
router.register(r'productos', ProductoViewSet)
router.register(r'ventas', VentaViewSet) # <--- AGREGAR ESTO PARA VER EL HISTORIAL

urlpatterns = [
    path('', include(router.urls)),
    path('dashboard/', DashboardView.as_view()),
    path('chat/', ChatbotView.as_view()),
    path('vender/', RegistrarVentaView.as_view()), # <--- ESTO ES LO QUE USA EL MODAL
]