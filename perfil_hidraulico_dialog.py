import numpy as np
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from qgis.PyQt.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                                 QPushButton, QMessageBox, QFrame)
from qgis.PyQt.QtCore import Qt
from qgis.gui import QgsMapLayerComboBox, QgsVertexMarker
from qgis.core import QgsMapLayerProxyModel, QgsPointXY
from qgis.utils import iface

# ==========================================================
# FUNCIONES HIDRÁULICAS
# ==========================================================

def Area_Hidraulica(depth, dx):
    depth = np.nan_to_num(depth, nan=0.0)
    try:
        return np.trapezoid(depth, dx=dx)
    except AttributeError:
        return np.trapz(depth, dx=dx)

def Ancho_Mojado(depth, dx):
    return np.sum(depth > 0) * dx

def Perimetro_Mojado(depth, dx):
    depth = np.nan_to_num(depth, nan=0.0)
    wet = depth > 0
    if np.sum(wet) < 2: return 0.0
    y = depth[wet]
    dy = np.diff(y)
    ds = np.sqrt(dx**2 + dy**2)
    return np.sum(ds)

def Velocidad_Media(depth, velocity):
    depth = np.nan_to_num(depth, nan=0.0)
    velocity = np.nan_to_num(velocity, nan=0.0)
    wet = depth > 0
    if not np.any(wet): return 0.0
    return np.sum(velocity[wet] * depth[wet]) / np.sum(depth[wet])

def Numero_Froude(A, T, V_med):
    g = 9.81
    if A <= 0 or T <= 0 or np.isnan(V_med): return 0.0, "Sin flujo"
    D_h = A / T
    Fr = V_med / np.sqrt(g * D_h)
    Fr = float(round(Fr, 2))
    reg = "Subcrítico" if Fr < 1 else ("Crítico" if np.isclose(Fr, 1.0, atol=0.05) else "Supercrítico")
    return Fr, reg

# ==========================================================
# CLASE PRINCIPAL
# ==========================================================

class PerfilHidraulicoDialog(QDialog):
    def __init__(self, parent=iface.mainWindow()):
        super().__init__(parent)
        self.setWindowTitle("Análisis de Perfil Hidráulico")
        self.resize(1200, 850)
        self.setWindowFlags(Qt.Window)

        # Configuración visual global
        plt.rcParams.update({'font.size': 8})

        self.x_data = np.array([])
        self.z_data = None
        self.depth_data = None
        self.vel_data = None
        self.puntos_geo = []

        self.marker = None
        self.vline_topo = None
        self.hline_topo = None
        self.vline_vel = None
        self.hline_vel = None
        self.annotation = None

        self._setup_ui()
        self.canvas.mpl_connect("motion_notify_event", self._on_move)

    def _setup_ui(self):
        main_layout = QHBoxLayout(self)
        self.fig, (self.ax_topo, self.ax_vel) = plt.subplots(
            2, 1, figsize=(10, 8), sharex=True,
            gridspec_kw={'height_ratios': [2, 1]}
        )

        self.canvas = FigureCanvasQTAgg(self.fig)
        main_layout.addWidget(self.canvas, stretch=1)

        panel = QFrame()
        panel.setFixedWidth(240)
        layout = QVBoxLayout(panel)

        # Selectores
        for label, cb_name in [("Eje:", "cb_line"), ("DEM:", "cb_dem"), 
                               ("Tirante:", "cb_depth"), ("Velocidad:", "cb_velocity")]:
            layout.addWidget(QLabel(f"<b>{label}</b>"))
            cb = QgsMapLayerComboBox()
            if "line" in cb_name: cb.setFilters(QgsMapLayerProxyModel.LineLayer)
            else: cb.setFilters(QgsMapLayerProxyModel.RasterLayer)
            setattr(self, cb_name, cb)
            layout.addWidget(cb)

        self.btn_run = QPushButton("CALCULAR")
        self.btn_run.setStyleSheet("font-weight: bold; height: 35px; background-color: #2ecc71; color: white;")
        layout.addWidget(self.btn_run)

        self.btn_real_scale = QPushButton("ESCALA 1:1")
        self.btn_real_scale.setCheckable(True)
        self.btn_real_scale.setChecked(True)
        layout.addWidget(self.btn_real_scale)

        self.lbl_results = QLabel("Esperando datos...")
        self.lbl_results.setStyleSheet("background-color: #f8f9fa; border: 1px solid #ddd; padding: 8px; font-size: 10px;")
        self.lbl_results.setWordWrap(True)
        layout.addWidget(self.lbl_results)

        layout.addStretch()
        main_layout.addWidget(panel)

        self.btn_run.clicked.connect(self._run_analysis)
        self.btn_real_scale.clicked.connect(self._toggle_scale)

    def _on_move(self, event):
        if not event.inaxes or len(self.x_data) == 0:
            if self.annotation:
                self.annotation.set_visible(False)
                for line in [self.vline_topo, self.hline_topo, self.vline_vel, self.hline_vel]:
                    if line: line.set_visible(False)
                self.canvas.draw_idle()
            return

        idx = np.abs(self.x_data - event.xdata).argmin()
        x, z, d, v = self.x_data[idx], self.z_data[idx], self.depth_data[idx], self.vel_data[idx]
        
        tirante = max(0, d) if not np.isnan(d) else 0.0
        velocidad = max(0, v) if not np.isnan(v) else 0.0

        # Actualizar Cruz del Cursor
        if self.vline_topo:
            self.vline_topo.set_xdata([x])
            self.vline_vel.set_xdata([x])
            self.hline_topo.set_ydata([z])
            self.hline_vel.set_ydata([velocidad])
            
            for line in [self.vline_topo, self.hline_topo, self.vline_vel, self.hline_vel]:
                line.set_visible(True)

        # Tooltip interactivo
        texto = f"Tirante: {tirante:.2f} m\nCT: {z:.1f} m\nVel: {velocidad:.2f} m/s"
        #texto = f"CT: {z:.2f} m\nTirante: {tirante:.2f} m\nVel: {velocidad:.2f} m/s"
        if self.annotation:
            self.annotation.xy = (x, z)
            self.annotation.set_text(texto)
            self.annotation.set_visible(True)

        # Marcador en el mapa de QGIS
        if self.marker: iface.mapCanvas().scene().removeItem(self.marker)
        if idx < len(self.puntos_geo):
            self.marker = QgsVertexMarker(iface.mapCanvas())
            self.marker.setCenter(QgsPointXY(self.puntos_geo[idx].x(), self.puntos_geo[idx].y()))
            self.marker.setColor(Qt.red)
            self.marker.setIconType(QgsVertexMarker.ICON_X)
            self.marker.setIconSize(10)

        self.canvas.draw_idle()

    def _run_analysis(self):
        layers = {'line': self.cb_line.currentLayer(), 'dem': self.cb_dem.currentLayer(), 
                  'depth': self.cb_depth.currentLayer(), 'vel': self.cb_velocity.currentLayer()}

        if any(l is None for l in layers.values()):
            QMessageBox.warning(self, "Error", "Faltan capas por seleccionar")
            return

        features = list(layers['line'].selectedFeatures()) or list(layers['line'].getFeatures())
        if not features: return
        
        geom = features[0].geometry()
        dx = layers['dem'].rasterUnitsPerPixelX()
        dist = np.arange(0, geom.length(), dx)
        pts = [geom.interpolate(d).asPoint() for d in dist]

        # Muestreo de Rásteres
        z = np.array([layers['dem'].dataProvider().sample(p, 1)[0] for p in pts])
        depth_vals = np.array([layers['depth'].dataProvider().sample(p, 1)[0] for p in pts])
        v_vals = np.array([layers['vel'].dataProvider().sample(p, 1)[0] for p in pts])

        self.x_data, self.z_data, self.depth_data, self.vel_data, self.puntos_geo = dist, z, depth_vals, v_vals, pts

        # Cálculos Hidráulicos
        A = Area_Hidraulica(depth_vals, dx)
        T = Ancho_Mojado(depth_vals, dx)
        P = Perimetro_Mojado(depth_vals, dx)
        Rh = A / P if P > 0 else 0.0
        Vmed = Velocidad_Media(depth_vals, v_vals)
        Fr, Reg = Numero_Froude(A, T, Vmed)

        # Mostrar Resultados
        self.lbl_results.setText(
            f"<b>RESULTADOS:</b><br>"
            f"· Area (A): {A:.2f} m²<br>"
            f"· Ancho (T): {T:.2f} m<br>"
            f"· Perímetro (P): {P:.2f} m<br>"
            f"· Radio Hid. (Rh): {Rh:.2f} m<br>"
            f"· Vel. Media: {Vmed:.2f} m/s<br>"
            f"· Froude: {Fr} ({Reg})"
        )

        # --- LÓGICA DE MÁSCARA E INTERSECCIÓN REQUERIDA ---
        mask = (~np.isnan(depth_vals)) & (depth_vals > 0)
        wl = np.full_like(z, np.nan)
        wl[mask] = z[mask] + depth_vals[mask]

        # Detectar bordes de la sección mojada
        cambios = np.diff(mask.astype(int))
        inicio = np.where(cambios == 1)[0] + 1
        fin = np.where(cambios == -1)[0]

        if mask[0]:
            inicio = np.insert(inicio, 0, 0)
        if mask[-1]:
            fin = np.append(fin, len(mask) - 1)

        # Forzar contacto del nivel de agua con el terreno en los extremos
        tramos = list(zip(inicio, fin))
        for ini, f_idx in tramos:
            if ini < len(wl): wl[ini] = z[ini]
            if f_idx < len(wl): wl[f_idx] = z[f_idx]

        self._update_plots(dist[:len(z)], z, wl, v_vals, mask)

    def _update_plots(self, x, z, wl, v, mask):
        self.annotation = None 
        self.ax_topo.clear()
        self.ax_vel.clear()

        l_size = 7 
        v_water = v[mask] if np.any(mask) else np.array([0])

        # Subplot 1: Topografía
        self.ax_topo.plot(x, z, color='#8B4513', lw=1.2, label='Terreno')
        self.ax_topo.plot(x, wl, color='#00BFFF', lw=1.0, label='Agua')
        self.ax_topo.fill_between(x, z, wl, where=mask, color='#00BFFF', alpha=0.3)
        self.ax_topo.set_ylabel("Elevación (msnm)", fontsize=l_size)
        self.ax_topo.tick_params(labelsize=l_size)
        self.ax_topo.grid(True, ls='--', alpha=0.4)

        # Subplot 2: Velocidad
        self.ax_vel.plot(x, np.where(mask, v, np.nan), color='red', lw=1.0)
        self.ax_vel.set_ylabel("Vel. (m/s)", fontsize=l_size)
        self.ax_vel.set_xlabel("Distancia (m)", fontsize=l_size)
        self.ax_vel.tick_params(labelsize=l_size)
        self.ax_vel.grid(True, ls='--', alpha=0.4)

        # Ajuste dinámico del eje de velocidad
        if len(v_water) > 0 and not np.all(np.isnan(v_water)):
            v_min, v_max = np.nanmin(v_water), np.nanmax(v_water)
            padding = (v_max - v_min) * 0.2 if v_max != v_min else 0.5
            ymin = max(0, v_min - padding) if v_min < 1 else v_min - padding
            self.ax_vel.set_ylim(ymin, v_max + padding)

        # Crear Cursor en Cruz
        c_style = dict(ls='--', color='black', lw=0.7, visible=False)
        self.vline_topo = self.ax_topo.axvline(x[0], **c_style)
        self.hline_topo = self.ax_topo.axhline(z[0], **c_style)
        self.vline_vel = self.ax_vel.axvline(x[0], **c_style)
        self.hline_vel = self.ax_vel.axhline(0, **c_style)

        # Anotación flotante
        self.annotation = self.ax_topo.annotate(
            "", xy=(0, 0), xytext=(10, 10), textcoords="offset points",
            bbox=dict(boxstyle="round", fc="white", ec="black", alpha=0.8),
            fontsize=7
        )
        self.annotation.set_visible(False)

        self._toggle_scale()
        self.fig.tight_layout()
        self.canvas.draw()

    def _toggle_scale(self):
        self.ax_topo.set_aspect('equal' if self.btn_real_scale.isChecked() else 'auto', adjustable='datalim')
        self.canvas.draw()

    def closeEvent(self, event):
        if self.marker: iface.mapCanvas().scene().removeItem(self.marker)
        event.accept()