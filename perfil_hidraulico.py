import os
from qgis.PyQt.QtWidgets import QAction
from qgis.PyQt.QtGui import QIcon
from .perfil_hidraulico_dialog import PerfilHidraulicoDialog

class PerfilHidraulico:
    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.icon_path = os.path.join(self.plugin_dir, "icono.png")
        self.dlg = None 

    def initGui(self):
        self.action = QAction(
            QIcon(self.icon_path),
            "Post-Proceso Hidráulico Hec-Ras",
            self.iface.mainWindow()
        )
        self.action.triggered.connect(self.run)
        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToMenu("&Ingeniería Hidráulica", self.action)

    def unload(self):
        self.iface.removeToolBarIcon(self.action)
        self.iface.removePluginMenu("&Ingeniería Hidráulica", self.action)

    def run(self):
        if self.dlg is None:
            self.dlg = PerfilHidraulicoDialog(self.iface.mainWindow())
        self.dlg.show()