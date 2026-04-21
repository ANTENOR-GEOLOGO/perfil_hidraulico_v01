# -*- coding: utf-8 -*-
def classFactory(iface):
    from .perfil_hidraulico import PerfilHidraulico
    return PerfilHidraulico(iface)