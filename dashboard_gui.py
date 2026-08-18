#!/usr/bin/env python3
"""
GUI: arrastra tu Excel de GBM y genera el dashboard
=====================================================

Ventanita para no tener que usar la terminal: arrastras el .xlsx que
exportaste de la app de GBM (o lo eliges con el boton), se lee con
cartera_gbm.leer_cartera, se genera el dashboard con dashboard_html.generar
y se abre solo en el navegador.

Requiere: pip install openpyxl tkinterdnd2
(tkinterdnd2 es opcional: sin el la ventana funciona igual, solo sin
arrastrar-y-soltar -- queda nada mas el boton "Elegir archivo...").
"""

import sys
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    _DND_DISPONIBLE = True
except ImportError:
    _DND_DISPONIBLE = False

import cartera_gbm
import dashboard_html

TINTA = "#1f2328"
GRIS = "#57606a"
GRIS_CLARO = "#f6f8fa"
BORDE = "#d0d7de"
VERDE = "#1a7f37"
AZUL = "#2a78d6"


class DashboardApp:
    def __init__(self, root):
        self.root = root
        root.title("Dashboard de cartera — GBM")
        root.geometry("520x360")
        root.minsize(460, 320)
        root.configure(bg=GRIS_CLARO)

        contenedor = tk.Frame(root, bg=GRIS_CLARO, padx=24, pady=24)
        contenedor.pack(fill="both", expand=True)

        tk.Label(contenedor, text="Cartera GBM → Dashboard", font=("Segoe UI", 16, "bold"),
                 bg=GRIS_CLARO, fg=TINTA).pack(anchor="w")
        tk.Label(contenedor,
                 text="Arrastra aquí el Excel que exportaste de la app de GBM\n"
                      "(Detalle de Portafolio) o elígelo con el botón.",
                 font=("Segoe UI", 10), bg=GRIS_CLARO, fg=GRIS, justify="left").pack(anchor="w", pady=(4, 16))

        self.zona = tk.Label(
            contenedor, text="📄  Suelta el .xlsx aquí",
            font=("Segoe UI", 12), bg="#ffffff", fg=GRIS,
            relief="solid", bd=1, highlightthickness=2,
            highlightbackground=BORDE, highlightcolor=BORDE)
        self.zona.pack(fill="both", expand=True, pady=(0, 16))

        botones = tk.Frame(contenedor, bg=GRIS_CLARO)
        botones.pack(fill="x")

        self.boton_elegir = tk.Button(
            botones, text="Elegir archivo…", command=self.elegir_archivo,
            bg=AZUL, fg="white", activebackground="#1c5cab", activeforeground="white",
            relief="flat", padx=14, pady=8, font=("Segoe UI", 10, "bold"), cursor="hand2")
        self.boton_elegir.pack(side="left")

        self.estado = tk.Label(contenedor, text="", font=("Segoe UI", 9),
                                bg=GRIS_CLARO, fg=GRIS, justify="left", anchor="w", wraplength=460)
        self.estado.pack(fill="x", pady=(12, 0))

        if _DND_DISPONIBLE:
            self.zona.drop_target_register(DND_FILES)
            self.zona.dnd_bind("<<Drop>>", self._al_soltar)
            self.zona.dnd_bind("<<DragEnter>>", lambda e: self.zona.configure(bg="#eef4fc"))
            self.zona.dnd_bind("<<DragLeave>>", lambda e: self.zona.configure(bg="#ffffff"))
        else:
            self.zona.configure(text="📄  Arrastrar y soltar no disponible en esta instalación\n"
                                      "(falta el paquete tkinterdnd2) — usa el botón de abajo")

    def _al_soltar(self, event):
        self.zona.configure(bg="#ffffff")
        rutas = self.root.tk.splitlist(event.data)
        if not rutas:
            return
        self._procesar(Path(rutas[0]))

    def elegir_archivo(self):
        ruta = filedialog.askopenfilename(
            title="Elige el Excel de tu cartera de GBM",
            filetypes=[("Excel", "*.xlsx"), ("Todos los archivos", "*.*")])
        if ruta:
            self._procesar(Path(ruta))

    def _procesar(self, ruta: Path):
        if ruta.suffix.lower() != ".xlsx":
            messagebox.showerror("Archivo inválido", f"'{ruta.name}' no es un archivo .xlsx.")
            return

        self.estado.configure(text=f"Leyendo {ruta.name}…", fg=GRIS)
        self.root.update_idletasks()

        try:
            cartera = cartera_gbm.leer_cartera(ruta)
            if not cartera.posiciones and not cartera.efectivo:
                raise ValueError("No se encontraron posiciones ni efectivo en el archivo. "
                                  "¿Es el Excel de 'Detalle de Portafolio' de GBM?")
            ruta_html = dashboard_html.generar(cartera)
        except Exception as exc:
            self.estado.configure(text=f"Error al procesar {ruta.name}.", fg="#b3261e")
            messagebox.showerror("No se pudo generar el dashboard", str(exc))
            return

        self.estado.configure(
            text=f"Dashboard generado: {ruta_html.name}\n"
                 f"{len(cartera.posiciones)} posiciones · Valor total ${cartera.valor_total:,.2f}",
            fg=VERDE)
        webbrowser.open(ruta_html.resolve().as_uri())


def main():
    root = TkinterDnD.Tk() if _DND_DISPONIBLE else tk.Tk()
    DashboardApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
