import json
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import cv2
import numpy as np
from PIL import Image, ImageTk

try:
    from ultralytics import YOLO
except Exception:
    YOLO = None

BASE = Path(__file__).resolve().parent
CONFIG_PATH = BASE / "data" / "parking_config.json"
RESULTS = BASE / "results"
MODEL_PATH = BASE / "models" / "yolo11m.pt"
VEHICLES = {"car", "motorcycle", "bus", "truck"}


class App:
    def __init__(self, root):
        self.root = root
        root.title("Aforo Inteligente - Panel del Vigilante")
        root.geometry("1300x800")
        root.configure(bg="#0b1220")
        self.config = self.load_config()
        self.reference = None
        self.reference_photo = None
        self.display_photo = None
        self.display_scale = 1
        self.display_offset = (0, 0)
        self.display_size = (0, 0)
        self.points = []
        self.model = None
        self.last_result = None
        self.make_ui()
        self.refresh_map()

    def load_config(self):
        if CONFIG_PATH.exists():
            try:
                return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"spaces": [], "capacity": 0}

    def save_config(self):
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(
            json.dumps(self.config, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def button(self, parent, text, cmd, primary=False):
        return tk.Button(
            parent,
            text=text,
            command=cmd,
            bg="#2563eb" if primary else "#1e293b",
            fg="white",
            activeforeground="white",
            activebackground="#334155",
            relief="flat",
            bd=0,
            padx=12,
            pady=9,
            cursor="hand2",
            font=("Segoe UI", 10, "bold"),
        )

    def make_ui(self):
        head = tk.Frame(self.root, bg="#111827")
        head.pack(fill="x")
        tk.Label(
            head,
            text="AFORO INTELIGENTE",
            bg="#111827",
            fg="white",
            font=("Segoe UI", 18, "bold"),
        ).pack(side="left", padx=20, pady=15)
        self.status = tk.Label(
            head,
            text="● SISTEMA LISTO",
            bg="#111827",
            fg="#22c55e",
            font=("Segoe UI", 10, "bold"),
        )
        self.status.pack(side="right", padx=20)
        self.navigation = tk.Frame(self.root, bg="#0b1220")
        self.navigation.pack(fill="x", padx=14, pady=(12, 0))
        self.content = tk.Frame(self.root, bg="#0b1220")
        self.content.pack(fill="both", expand=True, padx=14, pady=(10, 14))

        self.pages = {
            "guard": tk.Frame(self.content, bg="#0b1220"),
            "photos": tk.Frame(self.content, bg="#0b1220"),
            "spaces": tk.Frame(self.content, bg="#0b1220"),
            "history": tk.Frame(self.content, bg="#0b1220"),
        }
        self.navigation_buttons = {}
        for column, (page, label) in enumerate(
            [
                ("guard", "VIGILANTE"),
                ("photos", "ANALIZAR FOTOS"),
                ("spaces", "ESPACIOS"),
                ("history", "HISTORIAL"),
            ]
        ):
            button = tk.Button(
                self.navigation,
                text=label,
                command=lambda selected=page: self.show_page(selected),
                bg="#1e293b",
                fg="#cbd5e1",
                activebackground="#334155",
                activeforeground="white",
                relief="flat",
                bd=0,
                padx=12,
                pady=11,
                cursor="hand2",
                font=("Segoe UI", 10, "bold"),
            )
            button.grid(row=0, column=column, sticky="ew", padx=4)
            button.bind(
                "<Enter>",
                lambda event: self._hover_navigation(event.widget, True),
            )
            button.bind(
                "<Leave>",
                lambda event: self._hover_navigation(event.widget, False),
            )
            self.navigation_buttons[page] = button
        for column in range(4):
            self.navigation.grid_columnconfigure(column, weight=1, uniform="navigation")

        self.tab_guard = self.pages["guard"]
        self.tab_photos = self.pages["photos"]
        self.tab_spaces = self.pages["spaces"]
        self.tab_history = self.pages["history"]
        self.make_guard()
        self.make_photos()
        self.make_spaces()
        self.make_history()
        self.show_page("guard")

    def show_page(self, page):
        for frame in self.pages.values():
            frame.pack_forget()
        self.pages[page].pack(fill="both", expand=True)
        self.current_page = page
        for name, button in self.navigation_buttons.items():
            selected = name == page
            button.configure(
                bg="#2563eb" if selected else "#1e293b",
                fg="white" if selected else "#cbd5e1",
                activebackground="#1d4ed8" if selected else "#334155",
            )
        if page == "history" and hasattr(self, "history"):
            self.refresh_history()

    def _hover_navigation(self, button, hovering):
        if button is self.navigation_buttons[self.current_page]:
            return
        button.configure(bg="#334155" if hovering else "#1e293b")

    def metric(self, parent, title, color):
        frame = tk.Frame(parent, bg="#172033")
        frame.pack(fill="x", padx=12, pady=(12, 0))
        tk.Label(
            frame, text=title, bg="#172033", fg="#94a3b8", font=("Segoe UI", 9, "bold")
        ).pack(anchor="w", padx=12, pady=(10, 0))
        label = tk.Label(
            frame, text="—", bg="#172033", fg=color, font=("Segoe UI", 25, "bold")
        )
        label.pack(anchor="w", padx=12, pady=(0, 10))
        return label

    def make_guard(self):
        left = tk.Frame(self.tab_guard, bg="#111827")
        left.pack(side="left", fill="both", expand=True, padx=(0, 8))
        right = tk.Frame(self.tab_guard, bg="#111827", width=330)
        right.pack(side="right", fill="y")
        right.pack_propagate(False)
        tk.Label(
            left,
            text="MAPA DE ESPACIOS",
            bg="#111827",
            fg="white",
            font=("Segoe UI", 13, "bold"),
        ).pack(anchor="w", padx=15, pady=12)
        map_area = tk.Frame(left, bg="#020617")
        map_area.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        map_area.grid_rowconfigure(0, weight=1)
        map_area.grid_columnconfigure(0, weight=1)
        self.map = tk.Canvas(map_area, bg="#020617", highlightthickness=0)
        self.map.grid(row=0, column=0, sticky="nsew")
        self.map_scrollbar = ttk.Scrollbar(
            map_area,
            orient="vertical",
            command=self.map.yview,
            style="Map.Vertical.TScrollbar",
        )
        self.map_scrollbar.grid(row=0, column=1, sticky="ns")
        self.map.configure(yscrollcommand=self.map_scrollbar.set)
        self.map.bind(
            "<Configure>",
            lambda event: self.refresh_map(event.width, event.height),
        )
        self.available_label = self.metric(right, "DISPONIBLES", "#22c55e")
        self.occupied_label = self.metric(right, "OCUPADOS", "#ef4444")
        self.occupancy_label = self.metric(right, "OCUPACIÓN", "#f59e0b")
        tk.Label(
            right,
            text="RECOMENDACIÓN AL VIGILANTE",
            bg="#111827",
            fg="#94a3b8",
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w", padx=14, pady=(15, 5))
        self.recommendation = tk.Label(
            right,
            text="Analice una foto para conocer los espacios libres.",
            bg="#111827",
            fg="white",
            wraplength=290,
            justify="left",
            font=("Segoe UI", 11, "bold"),
        )
        self.recommendation.pack(anchor="w", padx=14)

    def make_photos(self):
        bar = tk.Frame(self.tab_photos, bg="#111827")
        bar.pack(fill="x", pady=(0, 10))
        tk.Label(
            bar,
            text="ANÁLISIS DE FOTOGRAFÍAS",
            bg="#111827",
            fg="white",
            font=("Segoe UI", 13, "bold"),
        ).pack(side="left", padx=14, pady=12)
        self.button(bar, "Analizar carpeta", self.analyze_folder).pack(
            side="right", padx=8, pady=8
        )
        self.button(bar, "Seleccionar fotografías", self.select_photos, True).pack(
            side="right", padx=8, pady=8
        )
        body = tk.Frame(self.tab_photos, bg="#0b1220")
        body.pack(fill="both", expand=True)
        self.preview = tk.Label(
            body,
            bg="#020617",
            fg="#64748b",
            text="Cargue una fotografía para analizar.",
            font=("Segoe UI", 12),
        )
        self.preview.pack(side="left", fill="both", expand=True, padx=(0, 8))
        panel = tk.Frame(body, bg="#111827", width=440)
        panel.pack(side="right", fill="y")
        panel.pack_propagate(False)
        tk.Label(
            panel,
            text="RESULTADO POR ESPACIO",
            bg="#111827",
            fg="white",
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w", padx=12, pady=12)
        self.tree = ttk.Treeview(
            panel, columns=("id", "state", "kind", "color"), show="headings"
        )
        for c, label, width in [
            ("id", "ESPACIO", 75),
            ("state", "ESTADO", 100),
            ("kind", "TIPO", 110),
            ("color", "COLOR", 100),
        ]:
            self.tree.heading(c, text=label)
            self.tree.column(c, width=width, anchor="center")
        self.tree.pack(fill="both", expand=True, padx=10, pady=(0, 8))
        self.detection_summary = tk.Label(
            panel,
            text="Detecciones: —",
            bg="#111827",
            fg="#fbbf24",
            font=("Segoe UI", 9),
            wraplength=400,
            justify="left",
        )
        self.detection_summary.pack(anchor="w", padx=12, pady=(0, 12))

    def make_spaces(self):
        bar = tk.Frame(self.tab_spaces, bg="#111827")
        bar.pack(fill="x", pady=(0, 10))
        tk.Label(
            bar,
            text="CONFIGURAR ESPACIOS",
            bg="#111827",
            fg="white",
            font=("Segoe UI", 13, "bold"),
        ).pack(side="left", padx=14, pady=12)
        self.button(bar, "Cargar foto de referencia", self.load_reference, True).pack(
            side="right", padx=8, pady=8
        )
        self.button(bar, "Guardar espacios", self.save_spaces).pack(
            side="right", padx=8, pady=8
        )
        self.button(bar, "Limpiar", self.clear_spaces).pack(
            side="right", padx=8, pady=8
        )
        tk.Label(
            self.tab_spaces,
            text="Cargue una foto fija y marque las 4 esquinas de cada espacio. Cada 4 clics crea un espacio.",
            bg="#0b1220",
            fg="#cbd5e1",
            font=("Segoe UI", 10),
        ).pack(anchor="w", pady=(0, 8))
        self.space_canvas = tk.Canvas(
            self.tab_spaces, bg="#020617", highlightthickness=0
        )
        self.space_canvas.pack(fill="both", expand=True)
        self.space_canvas.bind("<Button-1>", self.space_click)

    def make_history(self):
        bar = tk.Frame(self.tab_history, bg="#111827")
        bar.pack(fill="x")
        tk.Label(
            bar,
            text="HISTORIAL DE ANÁLISIS",
            bg="#111827",
            fg="white",
            font=("Segoe UI", 13, "bold"),
        ).pack(side="left", padx=14, pady=12)
        self.history_count = tk.Label(
            bar,
            text="0 análisis",
            bg="#111827",
            fg="#ffffff",
            font=("Segoe UI", 9),
        )
        self.history_count.pack(side="left", padx=(0, 10))
        self.button(bar, "Actualizar", self.refresh_history).pack(
            side="right", padx=10, pady=8
        )
        self.clear_history_button = self.button(
            bar, "Vaciar historial", self.clear_history
        )
        self.clear_history_button.configure(bg="#7f1d1d", activebackground="#991b1b")
        self.clear_history_button.pack(side="right", padx=4, pady=8)
        self.delete_history_button = self.button(
            bar, "Eliminar seleccionado", self.delete_history_entry
        )
        self.delete_history_button.configure(
            bg="#9a3412", activebackground="#c2410c", state="disabled"
        )
        self.delete_history_button.pack(side="right", padx=4, pady=8)
        self.history = ttk.Treeview(
            self.tab_history,
            columns=("time", "file", "occupied", "free"),
            show="headings",
        )
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure(
            "Map.Vertical.TScrollbar",
            background="#1e293b",
            troughcolor="#020617",
            bordercolor="#020617",
            arrowcolor="#cbd5e1",
            lightcolor="#334155",
            darkcolor="#0f172a",
            relief="flat",
            arrowsize=14,
            width=14,
        )
        style.map(
            "Map.Vertical.TScrollbar",
            background=[
                ("pressed", "#2563eb"),
                ("active", "#334155"),
            ],
            arrowcolor=[("pressed", "white"), ("active", "white")],
        )
        style.configure(
            "Treeview",
            background="#111827",
            fieldbackground="#111827",
            foreground="#e2e8f0",
            rowheight=30,
            font=("Segoe UI", 10),
        )
        style.configure(
            "Treeview.Heading",
            background="#1e293b",
            foreground="white",
            font=("Segoe UI", 9, "bold"),
            relief="flat",
        )
        style.map(
            "Treeview",
            background=[("selected", "#1d4ed8")],
            foreground=[("selected", "white")],
        )
        for c, l, w in [
            ("time", "FECHA/HORA", 160),
            ("file", "FOTOGRAFÍA", 350),
            ("occupied", "OCUPADOS", 120),
            ("free", "DISPONIBLES", 120),
        ]:
            self.history.heading(c, text=l)
            self.history.column(c, width=w)
        self.history.pack(fill="both", expand=True, padx=10, pady=10)
        self.history.bind("<<TreeviewSelect>>", self.update_history_actions)
        self.refresh_history()

    def read_history(self):
        hist = RESULTS / "history.json"
        if not hist.exists():
            return []
        data = json.loads(hist.read_text(encoding="utf-8"))
        required = {"timestamp", "file", "occupied", "available"}
        if not isinstance(data, list) or any(
            not isinstance(record, dict)
            or not required.issubset(record)
            or not isinstance(record["file"], str)
            for record in data
        ):
            raise ValueError("El archivo del historial tiene un formato no válido.")
        return data

    def write_history(self, data):
        RESULTS.mkdir(exist_ok=True)
        (RESULTS / "history.json").write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def history_output_path(self, record):
        return RESULTS / f"{Path(record['file']).stem}_analizada.jpg"

    def update_history_actions(self, event):
        self.delete_history_button.configure(
            state="normal" if event.widget.selection() else "disabled"
        )

    def delete_history_entry(self):
        selection = self.history.selection()
        if not selection:
            messagebox.showinfo(
                "Historial", "Seleccione un análisis de la lista para eliminarlo."
            )
            return
        try:
            data = self.read_history()
            index = int(selection[0])
            if index < 0 or index >= len(data):
                self.refresh_history()
                messagebox.showerror(
                    "Historial",
                    "La lista cambió. Actualice la selección e inténtelo de nuevo.",
                )
                return
            record = data[index]
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            messagebox.showerror("Error al leer el historial", str(exc))
            return

        if not messagebox.askyesno(
            "Eliminar análisis",
            f"¿Eliminar el análisis de «{record['file']}» del historial?\n\n"
            "También se eliminará la imagen analizada generada. "
            "La fotografía original se conservará.",
        ):
            return

        output_path = self.history_output_path(record)
        remaining = data[:index] + data[index + 1 :]
        try:
            self.write_history(remaining)
        except OSError as exc:
            messagebox.showerror("Error al guardar el historial", str(exc))
            return

        output_error = None
        if not any(
            Path(item["file"]).stem == Path(record["file"]).stem for item in remaining
        ):
            try:
                output_path.unlink(missing_ok=True)
            except OSError as exc:
                output_error = exc
        self.refresh_history()
        if output_error:
            messagebox.showwarning(
                "Historial actualizado",
                f"Se eliminó la entrada, pero no se pudo borrar la imagen generada:\n"
                f"{output_error}",
            )

    def clear_history(self):
        try:
            data = self.read_history()
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            messagebox.showerror("Error al leer el historial", str(exc))
            return
        if not data:
            messagebox.showinfo("Historial", "El historial ya está vacío.")
            return
        if not messagebox.askyesno(
            "Vaciar historial",
            f"¿Eliminar los {len(data)} análisis del historial y sus imágenes generadas?\n\n"
            "Las fotografías originales se conservarán.",
        ):
            return

        output_paths = {self.history_output_path(record) for record in data}
        try:
            self.write_history([])
        except OSError as exc:
            messagebox.showerror("Error al guardar el historial", str(exc))
            return

        errors = []
        for output_path in output_paths:
            try:
                output_path.unlink(missing_ok=True)
            except OSError as exc:
                errors.append(f"{output_path.name}: {exc}")
        self.refresh_history()
        if errors:
            messagebox.showwarning(
                "Historial actualizado",
                "Se vació el historial, pero no se pudieron borrar algunos archivos:\n"
                + "\n".join(errors),
            )

    def load_reference(self):
        p = filedialog.askopenfilename(
            filetypes=[("Imágenes", "*.jpg *.jpeg *.png *.bmp")]
        )
        if not p:
            return
        self.reference = cv2.imread(p)
        if self.reference is None:
            messagebox.showerror("Error", "No se pudo abrir la foto.")
            return
        h, w = self.reference.shape[:2]
        self.config["reference_width"], self.config["reference_height"] = w, h
        self.config["reference_path"] = p
        self.config["spaces"] = []
        self.points = []
        self.space_canvas.delete("all")
        self.draw_reference()

    def draw_reference(self):
        if self.reference is None:
            return
        im = Image.fromarray(cv2.cvtColor(self.reference, cv2.COLOR_BGR2RGB))
        cw, ch = max(600, self.space_canvas.winfo_width()), max(
            400, self.space_canvas.winfo_height()
        )
        ow, oh = im.size
        im.thumbnail((cw - 20, ch - 20))
        dw, dh = im.size
        self.display_scale = dw / ow
        self.display_offset = ((cw - dw) // 2, (ch - dh) // 2)
        self.display_size = (dw, dh)
        self.reference_photo = ImageTk.PhotoImage(im)
        self.space_canvas.delete("all")
        self.space_canvas.create_image(
            *self.display_offset, image=self.reference_photo, anchor="nw"
        )

    def space_click(self, event):
        if self.reference is None:
            messagebox.showinfo(
                "Primero cargue una foto", "Vaya a Cargar foto de referencia."
            )
            return
        ox, oy = self.display_offset
        dw, dh = self.display_size
        if not (ox <= event.x <= ox + dw and oy <= event.y <= oy + dh):
            return
        scale = self.display_scale
        h, w = self.reference.shape[:2]
        pt = (
            max(0, min(w - 1, int((event.x - ox) / scale))),
            max(0, min(h - 1, int((event.y - oy) / scale))),
        )
        self.points.append(pt)
        self.space_canvas.create_oval(
            event.x - 3,
            event.y - 3,
            event.x + 3,
            event.y + 3,
            fill="#f59e0b",
            outline="",
        )
        if len(self.points) == 4:
            sid = f"A{len(self.config['spaces'])+1}"
            pts = self.points.copy()
            shown = [(int(ox + x * scale), int(oy + y * scale)) for x, y in pts]
            self.config["spaces"].append({"id": sid, "points": pts})
            self.space_canvas.create_polygon(shown, outline="#22c55e", width=2)
            self.space_canvas.create_text(
                shown[0][0] + 12,
                shown[0][1],
                text=sid,
                fill="#22c55e",
                font=("Segoe UI", 10, "bold"),
            )
            self.points = []

    def save_spaces(self):
        if not self.config.get("spaces"):
            messagebox.showwarning(
                "Sin espacios", "Marque las cuatro esquinas de los espacios."
            )
            return
        self.config["capacity"] = len(self.config["spaces"])
        self.save_config()
        messagebox.showinfo(
            "Guardado", f"Se guardaron {len(self.config['spaces'])} espacios."
        )

    def clear_spaces(self):
        self.config["spaces"] = []
        self.config["capacity"] = 0
        self.points = []
        self.space_canvas.delete("all")
        if self.reference is not None:
            self.draw_reference()

    def select_photos(self):
        files = filedialog.askopenfilenames(
            filetypes=[("Imágenes", "*.jpg *.jpeg *.png *.bmp")]
        )
        if files:
            threading.Thread(
                target=self.analyze_files, args=(list(files),), daemon=True
            ).start()

    def analyze_folder(self):
        folder = filedialog.askdirectory()
        if not folder:
            return
        files = [
            str(p)
            for p in Path(folder).iterdir()
            if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp"}
        ]
        if not files:
            messagebox.showwarning(
                "Sin imágenes", "No se encontraron fotografías en esa carpeta."
            )
            return
        threading.Thread(target=self.analyze_files, args=(files,), daemon=True).start()

    def analyze_files(self, files):
        if not self.config.get("spaces"):
            self.root.after(
                0,
                lambda: messagebox.showwarning(
                    "Configure espacios",
                    "Marque y guarde los espacios antes de analizar fotos.",
                ),
            )
            return
        if YOLO is None:
            self.root.after(
                0,
                lambda: messagebox.showerror(
                    "Falta Ultralytics",
                    "Ejecute: python -m pip install -r requirements.txt",
                ),
            )
            return
        try:
            self.root.after(
                0,
                lambda: self.status.config(
                    text="● CARGANDO MODELO YOLO...", fg="#f59e0b"
                ),
            )
            if self.model is None:
                self.model = YOLO(str(MODEL_PATH))
            for p in files:
                result = self.analyze_one(p)
                self.root.after(0, lambda r=result: self.show_result(r))
        except Exception as e:
            self.root.after(
                0, lambda err=str(e): messagebox.showerror("Error de análisis", err)
            )
        finally:
            self.root.after(
                0, lambda: self.status.config(text="● SISTEMA LISTO", fg="#22c55e")
            )

    def analyze_one(self, path):
        frame = cv2.imread(path)
        if frame is None:
            raise ValueError("No se pudo leer " + path)
        h, w = frame.shape[:2]

        # COCO class IDs: car=2, motorcycle=3, bus=5, truck=7.
        # Restrict classes to vehicles to prevent detections such as "cell phone"
        # from being treated as vehicle candidates.
        vehicle_class_ids = [2, 3, 5, 7]
        candidates = []
        all_seen = []

        # Pass 1: full image with a stronger model and a low confidence threshold.
        # Pass 2: overlapping tiles help detect vehicles that are difficult from a high angle.
        tile_specs = [(0, 0, w, h, 1536)]
        if w > 600 and h > 400:
            xmid = int(w * 0.52)
            ymid = int(h * 0.55)
            tile_specs += [
                (0, 0, xmid, ymid, 960),
                (xmid - int(w * 0.04), 0, w, ymid, 960),
                (0, ymid - int(h * 0.04), xmid, h, 960),
                (xmid - int(w * 0.04), ymid - int(h * 0.04), w, h, 960),
            ]

        for x0, y0, x1, y1, imgsz in tile_specs:
            crop_img = frame[y0:y1, x0:x1]
            if crop_img.size == 0:
                continue
            pred = self.model.predict(
                source=crop_img,
                conf=0.06,
                iou=0.50,
                imgsz=imgsz,
                classes=vehicle_class_ids,
                augment=True,
                verbose=False,
            )[0]
            if pred.boxes is None:
                continue
            for b in pred.boxes:
                cls = int(b.cls[0])
                name = str(pred.names[cls]).lower()
                conf = float(b.conf[0])
                bx1, by1, bx2, by2 = map(float, b.xyxy[0].tolist())
                bx1 += x0
                bx2 += x0
                by1 += y0
                by2 += y0
                bx1 = max(0, min(w - 1, int(bx1)))
                bx2 = max(0, min(w - 1, int(bx2)))
                by1 = max(0, min(h - 1, int(by1)))
                by2 = max(0, min(h - 1, int(by2)))
                if bx2 <= bx1 or by2 <= by1:
                    continue
                candidates.append(
                    {"type": name, "confidence": conf, "bbox": [bx1, by1, bx2, by2]}
                )
                all_seen.append(f"{name} {conf:.2f}")

        # Merge duplicate detections from the full image and overlapping tiles using NMS.
        candidates.sort(key=lambda d: d["confidence"], reverse=True)
        merged = []

        def iou(a, b):
            ax1, ay1, ax2, ay2 = a
            bx1, by1, bx2, by2 = b
            ix1 = max(ax1, bx1)
            iy1 = max(ay1, by1)
            ix2 = min(ax2, bx2)
            iy2 = min(ay2, by2)
            iw = max(0, ix2 - ix1)
            ih = max(0, iy2 - iy1)
            inter = iw * ih
            area_a = max(0, ax2 - ax1) * max(0, ay2 - ay1)
            area_b = max(0, bx2 - bx1) * max(0, by2 - by1)
            union = area_a + area_b - inter
            return inter / union if union else 0

        for cand in candidates:
            if any(
                cand["type"] == kept["type"] and iou(cand["bbox"], kept["bbox"]) > 0.48
                for kept in merged
            ):
                continue
            merged.append(cand)

        detections = []
        for d in merged:
            x1, y1, x2, y2 = d["bbox"]
            vehicle_crop = frame[y1:y2, x1:x2]
            detections.append(
                {
                    "type": d["type"],
                    "color": self.color(vehicle_crop),
                    "bbox": d["bbox"],
                    "center": [(x1 + x2) // 2, (y1 + y2) // 2],
                    "confidence": d["confidence"],
                }
            )

        # Determine occupancy. Test center, lower-center and bbox/polygon overlap.
        occupied = {}
        refw = self.config.get("reference_width", w)
        refh = self.config.get("reference_height", h)
        for sp in self.config["spaces"]:
            pts = np.array(sp["points"], np.float32)
            pts[:, 0] *= w / refw
            pts[:, 1] *= h / refh
            pts = pts.astype(np.int32)
            occupied[sp["id"]] = None
            for det in detections:
                x1, y1, x2, y2 = det["bbox"]
                probes = [
                    ((x1 + x2) // 2, (y1 + y2) // 2),
                    ((x1 + x2) // 2, int(y1 + (y2 - y1) * 0.72)),
                    ((x1 + x2) // 2, int(y1 + (y2 - y1) * 0.82)),
                ]
                inside = any(
                    cv2.pointPolygonTest(pts, (float(x), float(y)), False) >= 0
                    for x, y in probes
                )
                if inside:
                    occupied[sp["id"]] = det
                    break

        annotated = frame.copy()
        for sp in self.config["spaces"]:
            pts = np.array(sp["points"], np.float32)
            pts[:, 0] *= w / refw
            pts[:, 1] *= h / refh
            pts = pts.astype(np.int32)
            det = occupied[sp["id"]]
            col = (0, 0, 255) if det else (0, 220, 0)
            cv2.polylines(annotated, [pts], True, col, 3)
            x, y = pts[0]
            label = sp["id"] + (" OCUPADO" if det else " LIBRE")
            cv2.putText(
                annotated,
                label,
                (int(x), max(25, int(y) - 7)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                col,
                2,
            )

        for det in detections:
            x1, y1, x2, y2 = det["bbox"]
            cv2.rectangle(annotated, (x1, y1), (x2, y2), (255, 180, 0), 3)
            label = f'{det["type"]} {det["color"]} {det["confidence"]:.2f}'
            cv2.putText(
                annotated,
                label,
                (x1, max(22, y1 - 8)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                (255, 180, 0),
                2,
            )

        occupied_count = sum(v is not None for v in occupied.values())
        result = {
            "path": path,
            "image": annotated,
            "detections": detections,
            "all_seen": all_seen,
            "occupied": occupied,
            "occupied_count": occupied_count,
            "available_count": len(occupied) - occupied_count,
            "timestamp": time.strftime("%d/%m/%Y %H:%M:%S"),
        }
        self.save_result(result)
        return result

    def color(self, crop):
        if crop is None or crop.size == 0:
            return "No identificado"
        # Central area is less likely to contain road/background than the full bbox.
        h, w = crop.shape[:2]
        crop = crop[int(h * 0.18) : int(h * 0.78), int(w * 0.18) : int(w * 0.82)]
        if crop.size == 0:
            return "No identificado"
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        pix = hsv.reshape(-1, 3)
        pix = pix[(pix[:, 2] > 35)]
        if len(pix) == 0:
            return "No identificado"
        hue = float(np.median(pix[:, 0]))
        sat = float(np.median(pix[:, 1]))
        val = float(np.median(pix[:, 2]))
        if val < 60:
            return "Negro"
        if sat < 35 and val > 185:
            return "Blanco"
        if sat < 40:
            return "Gris"
        if hue < 10 or hue >= 170:
            return "Rojo"
        if hue < 25:
            return "Naranja"
        if hue < 35:
            return "Amarillo"
        if hue < 90:
            return "Verde"
        if hue < 140:
            return "Azul"
        return "Otro"

    def show_result(self, r):
        self.last_result = r
        im = Image.fromarray(cv2.cvtColor(r["image"], cv2.COLOR_BGR2RGB))
        im.thumbnail((850, 650))
        self.display_photo = ImageTk.PhotoImage(im)
        self.preview.config(image=self.display_photo, text="")
        for item in self.tree.get_children():
            self.tree.delete(item)
        for sp in self.config["spaces"]:
            det = r["occupied"][sp["id"]]
            self.tree.insert(
                "",
                "end",
                values=(
                    sp["id"],
                    "OCUPADO" if det else "DISPONIBLE",
                    det["type"].title() if det else "—",
                    det["color"] if det else "—",
                ),
            )
        total = len(r["occupied"])
        n = r["occupied_count"]
        self.available_label.config(text=str(r["available_count"]))
        self.occupied_label.config(text=str(n))
        self.occupancy_label.config(text=f"{round(n/total*100) if total else 0}%")
        free = [sid for sid, d in r["occupied"].items() if d is None]
        self.recommendation.config(
            text=(
                "Puede indicar el espacio "
                + free[0]
                + ". Disponibles: "
                + ", ".join(free)
                if free
                else "Estacionamiento lleno: no hay espacios disponibles."
            )
        )
        self.detection_summary.config(
            text=f"Vehículos: {len(r['detections'])}. Detecciones del modelo: {', '.join(r['all_seen'][:12]) or 'ninguna'}"
        )
        self.refresh_map()
        if not r["detections"]:
            self.status.config(text="● YOLO NO DETECTÓ VEHÍCULOS", fg="#f59e0b")
        elif n == 0:
            self.status.config(
                text="● DETECTÓ VEHÍCULOS, PERO NINGUNO EN ESPACIOS", fg="#f59e0b"
            )
        else:
            self.status.config(text="● ANÁLISIS COMPLETADO", fg="#22c55e")
        self.show_page("photos")

    def refresh_map(self, width=None, height=None):
        self.map.delete("all")
        spaces = self.config.get("spaces", [])
        cw = max(1, width or self.map.winfo_width())
        ch = max(1, height or self.map.winfo_height())
        if not spaces:
            self.map.configure(scrollregion=(0, 0, cw, ch))
            self.map.create_text(
                cw / 2,
                ch / 2,
                text="Configure espacios en la pestaña ESPACIOS",
                fill="#64748b",
                font=("Segoe UI", 12),
            )
            return
        cols = min(len(spaces), max(1, (cw - 40) // 150))
        rows = int(np.ceil(len(spaces) / cols))
        cellw = max(1, (cw - 40) / cols)
        cellh = max(140, (ch - 40) / rows)
        content_height = max(ch, rows * cellh + 40)
        self.map.configure(scrollregion=(0, 0, cw, content_height))
        occ = self.last_result["occupied"] if self.last_result else {}
        for i, sp in enumerate(spaces):
            row = i // cols
            col = i % cols
            x1 = 20 + col * cellw
            y1 = 20 + row * cellh
            x2 = x1 + cellw - 10
            y2 = y1 + cellh - 10
            det = occ.get(sp["id"])
            color = "#ef4444" if det else "#22c55e"
            self.map.create_rectangle(
                x1,
                y1,
                x2,
                y2,
                fill="#35191e" if det else "#12351f",
                outline=color,
                width=3,
            )
            self.map.create_text(
                (x1 + x2) / 2,
                (y1 + y2) / 2 - 8,
                text=sp["id"],
                fill="white",
                font=("Segoe UI", 14, "bold"),
            )
            self.map.create_text(
                (x1 + x2) / 2,
                (y1 + y2) / 2 + 18,
                text="OCUPADO" if det else "LIBRE",
                fill=color,
                font=("Segoe UI", 10, "bold"),
            )

    def save_result(self, r):
        RESULTS.mkdir(exist_ok=True)
        cv2.imwrite(
            str(RESULTS / (Path(r["path"]).stem + "_analizada.jpg")), r["image"]
        )
        hist = RESULTS / "history.json"
        data = []
        if hist.exists():
            try:
                data = json.loads(hist.read_text(encoding="utf-8"))
            except Exception:
                pass
        data.append(
            {
                "timestamp": r["timestamp"],
                "file": Path(r["path"]).name,
                "occupied": r["occupied_count"],
                "available": r["available_count"],
            }
        )
        hist.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def refresh_history(self):
        if not hasattr(self, "history"):
            return
        for item in self.history.get_children():
            self.history.delete(item)
        try:
            data = self.read_history()
        except (OSError, json.JSONDecodeError, ValueError):
            self.history_count.config(text="Error al leer historial")
            return
        self.history_count.config(text=f"{len(data)} análisis")
        start = max(0, len(data) - 200)
        for index in range(len(data) - 1, start - 1, -1):
            r = data[index]
            self.history.insert(
                "",
                "end",
                iid=str(index),
                values=(r["timestamp"], r["file"], r["occupied"], r["available"]),
            )
        self.delete_history_button.configure(state="disabled")


def main():
    RESULTS.mkdir(exist_ok=True)
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
