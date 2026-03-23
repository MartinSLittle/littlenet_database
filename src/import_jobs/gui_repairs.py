from __future__ import annotations

from pathlib import Path
import sys

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except ModuleNotFoundError as exc:
    if exc.name != "tkinter":
        raise
    print(
        "Tkinter no esta disponible en esta instalacion de Python.\n"
        "En Linux suele resolverse instalando el paquete del sistema `python3-tk`.\n"
        "En Windows, Tkinter normalmente ya viene incluido con Python oficial.",
        file=sys.stderr,
    )
    raise SystemExit(1) from exc

from app_runtime import get_default_db_path
from repair_service import (
    RepairFormData,
    RepairSearchFilters,
    RepairUpdateData,
    create_repair_record,
    load_repair_detail,
    search_repairs,
    update_repair_record,
)
from schema import REPAIR_STATUS_LABELS


class RepairsApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Registro de reparaciones")
        self.root.geometry("1180x860")
        self.root.minsize(980, 680)

        self.db_path_var = tk.StringVar(value=str(get_default_db_path()))

        self.cliente_nombre_var = tk.StringVar()
        self.cliente_celular_var = tk.StringVar()
        self.cliente_correo_var = tk.StringVar()
        self.equipo_marca_var = tk.StringVar()
        self.equipo_modelo_original_var = tk.StringVar()
        self.equipo_serie_var = tk.StringVar()
        self.fecha_ingreso_var = tk.StringVar()
        self.fecha_egreso_var = tk.StringVar()
        self.falla_reportada_var = tk.StringVar()
        self.diagnostico_tecnico_var = tk.StringVar()
        self.costo_var = tk.StringVar()
        self.status_var = tk.StringVar()
        self.message_var = tk.StringVar(value="Completa el formulario y guarda la reparacion.")
        self.multimedia_paths: list[Path] = []

        self.search_field_map = {
            "ID reparacion": "id_reparacion",
            "Nombre cliente": "cliente_nombre",
            "Numero de serie": "nro_serie",
            "Marca": "marca",
            "Modelo": "modelo",
        }
        self.search_field_var = tk.StringVar(value="Nombre cliente")
        self.search_value_var = tk.StringVar()
        self.search_open_filter_var = tk.StringVar(value="Todas")
        self.search_status_var = tk.StringVar(value="Todos")
        self.search_message_var = tk.StringVar(value="Busca una reparacion para verla o editarla.")

        self.edit_repair_id: int | None = None
        self.edit_client_id: int | None = None
        self.edit_equipment_id: int | None = None
        self.edit_cliente_nombre_var = tk.StringVar()
        self.edit_cliente_celular_var = tk.StringVar()
        self.edit_cliente_correo_var = tk.StringVar()
        self.edit_equipo_marca_var = tk.StringVar()
        self.edit_equipo_modelo_original_var = tk.StringVar()
        self.edit_equipo_serie_var = tk.StringVar()
        self.edit_fecha_ingreso_var = tk.StringVar()
        self.edit_fecha_egreso_var = tk.StringVar()
        self.edit_costo_var = tk.StringVar()
        self.edit_status_var = tk.StringVar()
        self.edit_message_var = tk.StringVar(value="Selecciona una reparacion para editarla.")
        self.edit_multimedia_existing: list[str] = []
        self.edit_multimedia_new_paths: list[Path] = []

        self.state_options = {
            f"{label} ({code})": code for code, label in REPAIR_STATUS_LABELS.items()
        }
        self.state_label_for_code = {
            code: f"{label} ({code})" for code, label in REPAIR_STATUS_LABELS.items()
        }
        first_state = next(iter(self.state_options))
        self.status_var.set(first_state)
        self.edit_status_var.set(first_state)

        self._build_ui()

    def _build_ui(self) -> None:
        container = ttk.Frame(self.root)
        container.pack(fill=tk.BOTH, expand=True)
        container.columnconfigure(0, weight=1)
        container.rowconfigure(0, weight=1)

        self.main_canvas = tk.Canvas(container, highlightthickness=0)
        self.main_canvas.grid(row=0, column=0, sticky="nsew")

        main_scrollbar = ttk.Scrollbar(
            container,
            orient="vertical",
            command=self.main_canvas.yview,
        )
        main_scrollbar.grid(row=0, column=1, sticky="ns")
        self.main_canvas.configure(yscrollcommand=main_scrollbar.set)

        main = ttk.Frame(self.main_canvas, padding=12)
        main.columnconfigure(0, weight=1)
        main.rowconfigure(1, weight=1)
        self.main_window_id = self.main_canvas.create_window((0, 0), window=main, anchor="nw")

        self.main_canvas.bind("<Configure>", self._on_main_canvas_configure)
        main.bind("<Configure>", self._on_main_frame_configure)

        self._build_db_section(main)

        self.notebook = ttk.Notebook(main)
        self.notebook.bind("<<NotebookTabChanged>>", self._on_notebook_tab_changed)
        self._bind_scroll_events(self.main_canvas)
        self._bind_scroll_events(main)

        notebook = self.notebook
        notebook.grid(row=1, column=0, sticky="nsew", pady=(10, 0))

        create_tab = ttk.Frame(notebook, padding=12)
        create_tab.columnconfigure(0, weight=1)
        create_tab.rowconfigure(3, weight=1)
        notebook.add(create_tab, text="Nueva reparacion")
        self._build_create_tab(create_tab)
        self._bind_scroll_events(create_tab)

        search_tab = ttk.Frame(notebook, padding=12)
        search_tab.columnconfigure(0, weight=1)
        search_tab.rowconfigure(1, weight=1)
        notebook.add(search_tab, text="Buscar y editar")
        self._build_search_tab(search_tab)
        self._bind_scroll_events(search_tab)

        self.root.after_idle(self._refresh_scroll_region)

    def _build_db_section(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Base de datos", padding=10)
        frame.grid(row=0, column=0, sticky="ew")
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="Archivo SQLite").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(frame, textvariable=self.db_path_var).grid(row=0, column=1, sticky="ew", pady=4)
        ttk.Button(frame, text="Elegir...", command=self.pick_db_path).grid(row=0, column=2, sticky="ew", padx=(8, 0), pady=4)

    def _build_create_tab(self, parent: ttk.Frame) -> None:
        self._build_client_section(parent)
        self._build_equipment_section(parent)
        self._build_repair_section(parent)
        self._build_multimedia_section(parent)

        actions = ttk.Frame(parent, padding=(0, 12, 0, 0))
        actions.grid(row=4, column=0, sticky="ew")
        actions.columnconfigure(0, weight=1)

        ttk.Label(actions, textvariable=self.message_var, foreground="#1f4d2e").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Button(actions, text="Guardar reparacion", command=self.submit).grid(row=0, column=1, sticky="e")

    def _build_client_section(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Cliente", padding=10)
        frame.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="Nombre").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(frame, textvariable=self.cliente_nombre_var).grid(row=0, column=1, sticky="ew", pady=4)
        ttk.Label(frame, text="Celular").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(frame, textvariable=self.cliente_celular_var).grid(row=1, column=1, sticky="ew", pady=4)
        ttk.Label(frame, text="Correo").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(frame, textvariable=self.cliente_correo_var).grid(row=2, column=1, sticky="ew", pady=4)

    def _build_equipment_section(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Equipo", padding=10)
        frame.grid(row=1, column=0, sticky="ew", pady=8)
        frame.columnconfigure(1, weight=1)

        fields = [
            ("Marca", self.equipo_marca_var),
            ("Modelo", self.equipo_modelo_original_var),
            ("Nro serie", self.equipo_serie_var),
        ]
        for row_index, (label, variable) in enumerate(fields):
            ttk.Label(frame, text=label).grid(row=row_index, column=0, sticky="w", padx=(0, 8), pady=4)
            ttk.Entry(frame, textvariable=variable).grid(row=row_index, column=1, sticky="ew", pady=4)

    def _build_repair_section(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Reparacion", padding=10)
        frame.grid(row=2, column=0, sticky="ew", pady=8)
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="Fecha ingreso").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(frame, textvariable=self.fecha_ingreso_var).grid(row=0, column=1, sticky="ew", pady=4)
        ttk.Label(frame, text="Fecha egreso").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(frame, textvariable=self.fecha_egreso_var).grid(row=1, column=1, sticky="ew", pady=4)
        ttk.Label(frame, text="Falla reportada").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(frame, textvariable=self.falla_reportada_var).grid(row=2, column=1, sticky="ew", pady=4)
        ttk.Label(frame, text="Diagnostico tecnico").grid(row=3, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(frame, textvariable=self.diagnostico_tecnico_var).grid(row=3, column=1, sticky="ew", pady=4)
        ttk.Label(frame, text="Estado").grid(row=4, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Combobox(
            frame,
            textvariable=self.status_var,
            values=list(self.state_options.keys()),
            state="readonly",
        ).grid(row=4, column=1, sticky="ew", pady=4)
        ttk.Label(frame, text="Costo").grid(row=5, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(frame, textvariable=self.costo_var).grid(row=5, column=1, sticky="ew", pady=4)

        ttk.Label(frame, text="Formato de fecha: YYYY-MM-DD. Fecha egreso puede quedar vacia.").grid(
            row=6, column=1, sticky="w", pady=(4, 0)
        )

    def _build_multimedia_section(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Multimedia", padding=10)
        frame.grid(row=3, column=0, sticky="nsew", pady=8)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        parent.rowconfigure(3, weight=1)

        self.multimedia_list = tk.Listbox(frame, height=10)
        self.multimedia_list.grid(row=0, column=0, sticky="nsew")

        button_frame = ttk.Frame(frame)
        button_frame.grid(row=0, column=1, sticky="ns", padx=(10, 0))
        ttk.Button(button_frame, text="Agregar archivos...", command=self.add_files).grid(row=0, column=0, sticky="ew", pady=(0, 6))
        ttk.Button(button_frame, text="Quitar seleccionado", command=self.remove_selected_file).grid(row=1, column=0, sticky="ew")

    def _build_search_tab(self, parent: ttk.Frame) -> None:
        filters = ttk.LabelFrame(parent, text="Buscar reparaciones", padding=10)
        filters.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        filters.columnconfigure(1, weight=1)
        filters.columnconfigure(3, weight=1)
        filters.columnconfigure(5, weight=1)

        ttk.Label(filters, text="Buscar por").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Combobox(
            filters,
            textvariable=self.search_field_var,
            values=list(self.search_field_map.keys()),
            state="readonly",
        ).grid(row=0, column=1, sticky="ew", pady=4)
        ttk.Label(filters, text="Valor").grid(row=0, column=2, sticky="w", padx=(12, 8), pady=4)
        ttk.Entry(filters, textvariable=self.search_value_var).grid(row=0, column=3, sticky="ew", pady=4)
        ttk.Label(filters, text="Apertura").grid(row=0, column=4, sticky="w", padx=(12, 8), pady=4)
        ttk.Combobox(
            filters,
            textvariable=self.search_open_filter_var,
            values=["Todas", "Solo abiertas"],
            state="readonly",
        ).grid(row=0, column=5, sticky="ew", pady=4)

        ttk.Label(filters, text="Estado").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Combobox(
            filters,
            textvariable=self.search_status_var,
            values=["Todos", *self.state_options.keys()],
            state="readonly",
        ).grid(row=1, column=1, sticky="ew", pady=4)
        ttk.Button(filters, text="Buscar", command=self.search_existing_repairs).grid(row=1, column=3, sticky="e", pady=4)
        ttk.Button(filters, text="Limpiar", command=self.clear_search_filters).grid(row=1, column=5, sticky="e", pady=4)
        ttk.Label(filters, textvariable=self.search_message_var, foreground="#1f4d2e").grid(
            row=2, column=0, columnspan=6, sticky="w", pady=(6, 0)
        )

        content = ttk.Panedwindow(parent, orient=tk.HORIZONTAL)
        content.grid(row=1, column=0, sticky="nsew")

        results_frame = ttk.Frame(content, padding=(0, 0, 10, 0))
        results_frame.columnconfigure(0, weight=1)
        results_frame.rowconfigure(0, weight=1)
        content.add(results_frame, weight=3)

        columns = ("id", "cliente", "marca", "modelo", "serie", "estado", "ingreso", "egreso")
        self.results_tree = ttk.Treeview(results_frame, columns=columns, show="headings", height=16)
        headings = {
            "id": "ID",
            "cliente": "Cliente",
            "marca": "Marca",
            "modelo": "Modelo",
            "serie": "Serie",
            "estado": "Estado",
            "ingreso": "Ingreso",
            "egreso": "Egreso",
        }
        widths = {
            "id": 70,
            "cliente": 170,
            "marca": 110,
            "modelo": 180,
            "serie": 120,
            "estado": 140,
            "ingreso": 90,
            "egreso": 90,
        }
        for column in columns:
            self.results_tree.heading(column, text=headings[column])
            self.results_tree.column(column, width=widths[column], anchor="w")
        self.results_tree.grid(row=0, column=0, sticky="nsew")
        self.results_tree.bind("<<TreeviewSelect>>", self.on_result_selected)

        results_scroll = ttk.Scrollbar(results_frame, orient="vertical", command=self.results_tree.yview)
        results_scroll.grid(row=0, column=1, sticky="ns")
        self.results_tree.configure(yscrollcommand=results_scroll.set)

        detail = ttk.Frame(content)
        detail.columnconfigure(0, weight=1)
        detail.rowconfigure(3, weight=1)
        content.add(detail, weight=4)

        self._build_edit_client_section(detail)
        self._build_edit_equipment_section(detail)
        self._build_edit_repair_section(detail)
        self._build_edit_multimedia_section(detail)

        actions = ttk.Frame(detail, padding=(0, 10, 0, 0))
        actions.grid(row=4, column=0, sticky="ew")
        actions.columnconfigure(0, weight=1)
        ttk.Label(actions, textvariable=self.edit_message_var, foreground="#1f4d2e").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Button(actions, text="Guardar cambios", command=self.save_existing_repair).grid(row=0, column=1, sticky="e")

    def _build_edit_client_section(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Cliente", padding=10)
        frame.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="Nombre").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(frame, textvariable=self.edit_cliente_nombre_var).grid(row=0, column=1, sticky="ew", pady=4)
        ttk.Label(frame, text="Celular").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(frame, textvariable=self.edit_cliente_celular_var).grid(row=1, column=1, sticky="ew", pady=4)
        ttk.Label(frame, text="Correo").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(frame, textvariable=self.edit_cliente_correo_var).grid(row=2, column=1, sticky="ew", pady=4)

    def _build_edit_equipment_section(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Equipo", padding=10)
        frame.grid(row=1, column=0, sticky="ew", pady=8)
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="Marca").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(frame, textvariable=self.edit_equipo_marca_var).grid(row=0, column=1, sticky="ew", pady=4)
        ttk.Label(frame, text="Modelo").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(frame, textvariable=self.edit_equipo_modelo_original_var).grid(row=1, column=1, sticky="ew", pady=4)
        ttk.Label(frame, text="Nro serie").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(frame, textvariable=self.edit_equipo_serie_var).grid(row=2, column=1, sticky="ew", pady=4)

    def _build_edit_repair_section(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Reparacion", padding=10)
        frame.grid(row=2, column=0, sticky="ew", pady=8)
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="ID").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        self.edit_id_label = ttk.Label(frame, text="-")
        self.edit_id_label.grid(row=0, column=1, sticky="w", pady=4)
        ttk.Label(frame, text="Fecha ingreso").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(frame, textvariable=self.edit_fecha_ingreso_var, state="readonly").grid(row=1, column=1, sticky="ew", pady=4)
        ttk.Label(frame, text="Fecha egreso").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(frame, textvariable=self.edit_fecha_egreso_var).grid(row=2, column=1, sticky="ew", pady=4)
        ttk.Label(frame, text="Estado").grid(row=3, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Combobox(
            frame,
            textvariable=self.edit_status_var,
            values=list(self.state_options.keys()),
            state="readonly",
        ).grid(row=3, column=1, sticky="ew", pady=4)
        ttk.Label(frame, text="Costo").grid(row=4, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(frame, textvariable=self.edit_costo_var).grid(row=4, column=1, sticky="ew", pady=4)

        ttk.Label(frame, text="Falla reportada").grid(row=5, column=0, sticky="nw", padx=(0, 8), pady=4)
        self.edit_falla_reportada_text = tk.Text(frame, height=3, wrap="word")
        self.edit_falla_reportada_text.grid(row=5, column=1, sticky="ew", pady=4)
        ttk.Label(frame, text="Diagnostico tecnico").grid(row=6, column=0, sticky="nw", padx=(0, 8), pady=4)
        self.edit_diagnostico_tecnico_text = tk.Text(frame, height=4, wrap="word")
        self.edit_diagnostico_tecnico_text.grid(row=6, column=1, sticky="ew", pady=4)
        ttk.Label(frame, text="Formato de fecha: YYYY-MM-DD. Deja fecha egreso vacia si sigue abierta.").grid(
            row=7, column=1, sticky="w", pady=(4, 0)
        )

    def _build_edit_multimedia_section(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Multimedia asociada", padding=10)
        frame.grid(row=3, column=0, sticky="nsew", pady=8)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        self.edit_multimedia_list = tk.Listbox(frame, height=10)
        self.edit_multimedia_list.grid(row=0, column=0, sticky="nsew")

        button_frame = ttk.Frame(frame)
        button_frame.grid(row=0, column=1, sticky="ns", padx=(10, 0))
        ttk.Button(button_frame, text="Agregar archivos...", command=self.add_files_to_existing_repair).grid(
            row=0, column=0, sticky="ew", pady=(0, 6)
        )
        ttk.Button(button_frame, text="Quitar pendiente", command=self.remove_pending_existing_file).grid(
            row=1, column=0, sticky="ew"
        )

    def _on_main_canvas_configure(self, event: tk.Event[tk.Canvas]) -> None:
        self.main_canvas.itemconfigure(self.main_window_id, width=event.width)
        self._refresh_scroll_region()

    def _on_main_frame_configure(self, _event: tk.Event[ttk.Frame]) -> None:
        self._refresh_scroll_region()

    def _on_notebook_tab_changed(self, _event: tk.Event[ttk.Notebook]) -> None:
        self.root.after_idle(self._refresh_scroll_region)

    def _refresh_scroll_region(self) -> None:
        self.main_canvas.update_idletasks()
        self.main_canvas.configure(scrollregion=self.main_canvas.bbox("all"))

    def _bind_scroll_events(self, widget: tk.Misc) -> None:
        widget.bind("<MouseWheel>", self._on_mousewheel, add="+")
        widget.bind("<Button-4>", self._on_mousewheel, add="+")
        widget.bind("<Button-5>", self._on_mousewheel, add="+")

    def _on_mousewheel(self, event: tk.Event[tk.Misc]) -> str | None:
        if getattr(event, "delta", 0):
            step = -1 if event.delta > 0 else 1
        elif getattr(event, "num", None) == 4:
            step = -1
        elif getattr(event, "num", None) == 5:
            step = 1
        else:
            return None

        self.main_canvas.yview_scroll(step, "units")
        return "break"

    def pick_db_path(self) -> None:
        selected = filedialog.asksaveasfilename(
            title="Elegir base SQLite",
            defaultextension=".sqlite3",
            filetypes=[("SQLite", "*.sqlite3 *.db"), ("Todos", "*.*")],
            initialdir=str(Path(self.db_path_var.get()).expanduser().resolve().parent),
            initialfile=Path(self.db_path_var.get()).name or "littlenet_database.sqlite3",
        )
        if selected:
            self.db_path_var.set(selected)

    def add_files(self) -> None:
        selected = filedialog.askopenfilenames(
            title="Seleccionar archivos multimedia",
            filetypes=[("Todos los archivos", "*.*")],
        )
        for raw_path in selected:
            path = Path(raw_path)
            if path in self.multimedia_paths:
                continue
            self.multimedia_paths.append(path)
            self.multimedia_list.insert(tk.END, str(path))

    def remove_selected_file(self) -> None:
        selection = self.multimedia_list.curselection()
        if not selection:
            return
        index = selection[0]
        self.multimedia_list.delete(index)
        del self.multimedia_paths[index]

    def add_files_to_existing_repair(self) -> None:
        if self.edit_repair_id is None:
            messagebox.showerror("Sin seleccion", "Selecciona primero una reparacion.", parent=self.root)
            return
        selected = filedialog.askopenfilenames(
            title="Agregar multimedia a reparacion existente",
            filetypes=[("Todos los archivos", "*.*")],
        )
        for raw_path in selected:
            path = Path(raw_path)
            if path in self.edit_multimedia_new_paths:
                continue
            self.edit_multimedia_new_paths.append(path)
        self.refresh_edit_multimedia_list()

    def remove_pending_existing_file(self) -> None:
        selection = self.edit_multimedia_list.curselection()
        if not selection:
            return
        index = selection[0]
        if index < len(self.edit_multimedia_existing):
            return
        pending_index = index - len(self.edit_multimedia_existing)
        del self.edit_multimedia_new_paths[pending_index]
        self.refresh_edit_multimedia_list()

    def parse_cost(self, raw_value: str) -> float | None:
        cleaned = raw_value.strip()
        if not cleaned:
            return None
        try:
            return float(cleaned.replace(",", "."))
        except ValueError as exc:
            raise ValueError("El costo debe ser numerico.") from exc

    def selected_status_code(self, raw_value: str) -> int:
        return self.state_options[raw_value]

    def submit(self) -> None:
        try:
            result = create_repair_record(
                self.db_path_var.get().strip() or "littlenet_database.sqlite3",
                RepairFormData(
                    cliente_nombre=self.cliente_nombre_var.get(),
                    cliente_celular=self.cliente_celular_var.get(),
                    cliente_correo=self.cliente_correo_var.get(),
                    equipo_marca=self.equipo_marca_var.get(),
                    equipo_modelo_original=self.equipo_modelo_original_var.get(),
                    equipo_serie=self.equipo_serie_var.get(),
                    fecha_ingreso=self.fecha_ingreso_var.get(),
                    fecha_egreso=self.fecha_egreso_var.get(),
                    falla_reportada=self.falla_reportada_var.get(),
                    diagnostico_tecnico=self.diagnostico_tecnico_var.get(),
                    estado=self.selected_status_code(self.status_var.get()),
                    costo=self.parse_cost(self.costo_var.get()),
                    archivos=list(self.multimedia_paths),
                ),
            )
        except ValueError as exc:
            self.message_var.set(str(exc))
            messagebox.showerror("Error de validacion", str(exc), parent=self.root)
            return
        except Exception as exc:  # noqa: BLE001
            self.message_var.set(str(exc))
            messagebox.showerror("Error", str(exc), parent=self.root)
            return

        success_message = (
            f"Reparacion guardada. Cliente {result.client_id}, "
            f"equipo {result.equipment_id}, reparacion {result.repair_id}."
        )
        self.message_var.set(success_message)
        messagebox.showinfo("Registro completado", success_message, parent=self.root)
        self.clear_form()

    def search_existing_repairs(self) -> None:
        try:
            filters = RepairSearchFilters(
                field=self.search_field_map[self.search_field_var.get()],
                value=self.search_value_var.get(),
                only_open=self.search_open_filter_var.get() == "Solo abiertas",
                estado=None if self.search_status_var.get() == "Todos" else self.selected_status_code(self.search_status_var.get()),
            )
            results = search_repairs(
                self.db_path_var.get().strip() or "littlenet_database.sqlite3",
                filters,
            )
        except ValueError as exc:
            self.search_message_var.set(str(exc))
            messagebox.showerror("Error de busqueda", str(exc), parent=self.root)
            return
        except Exception as exc:  # noqa: BLE001
            self.search_message_var.set(str(exc))
            messagebox.showerror("Error", str(exc), parent=self.root)
            return

        self.results_tree.delete(*self.results_tree.get_children())
        for result in results:
            self.results_tree.insert(
                "",
                tk.END,
                iid=str(result.repair_id),
                values=(
                    result.repair_id,
                    result.cliente_nombre,
                    result.equipo_marca or "",
                    result.equipo_modelo or "",
                    result.equipo_serie or "",
                    REPAIR_STATUS_LABELS[result.estado],
                    result.fecha_ingreso,
                    result.fecha_egreso or "",
                ),
            )

        self.search_message_var.set(f"Resultados encontrados: {len(results)}")
        if not results:
            self.clear_edit_form()

    def clear_search_filters(self) -> None:
        self.search_field_var.set("Nombre cliente")
        self.search_value_var.set("")
        self.search_open_filter_var.set("Todas")
        self.search_status_var.set("Todos")
        self.results_tree.delete(*self.results_tree.get_children())
        self.search_message_var.set("Filtros reiniciados.")
        self.clear_edit_form()

    def on_result_selected(self, _event: object) -> None:
        selection = self.results_tree.selection()
        if not selection:
            return
        repair_id = int(selection[0])
        self.load_selected_repair(repair_id)

    def load_selected_repair(self, repair_id: int) -> None:
        try:
            detail = load_repair_detail(
                self.db_path_var.get().strip() or "littlenet_database.sqlite3",
                repair_id,
            )
        except ValueError as exc:
            self.edit_message_var.set(str(exc))
            messagebox.showerror("Error de carga", str(exc), parent=self.root)
            return
        except Exception as exc:  # noqa: BLE001
            self.edit_message_var.set(str(exc))
            messagebox.showerror("Error", str(exc), parent=self.root)
            return

        self.edit_repair_id = detail.repair_id
        self.edit_client_id = detail.client_id
        self.edit_equipment_id = detail.equipment_id
        self.edit_id_label.config(text=str(detail.repair_id))
        self.edit_cliente_nombre_var.set(detail.cliente_nombre)
        self.edit_cliente_celular_var.set(detail.cliente_celular or "")
        self.edit_cliente_correo_var.set(detail.cliente_correo or "")
        self.edit_equipo_marca_var.set(detail.equipo_marca or "")
        self.edit_equipo_modelo_original_var.set(detail.equipo_modelo_original or "")
        self.edit_equipo_serie_var.set(detail.equipo_serie or "")
        self.edit_fecha_ingreso_var.set(detail.fecha_ingreso)
        self.edit_fecha_egreso_var.set(detail.fecha_egreso or "")
        self.edit_costo_var.set("" if detail.costo is None else str(detail.costo))
        self.edit_status_var.set(self.state_label_for_code[detail.estado])
        self.set_text_widget(self.edit_falla_reportada_text, detail.falla_reportada or "")
        self.set_text_widget(self.edit_diagnostico_tecnico_text, detail.diagnostico_tecnico or "")
        self.edit_multimedia_existing = [item.ruta_archivo for item in detail.multimedia]
        self.edit_multimedia_new_paths = []
        self.refresh_edit_multimedia_list()
        self.edit_message_var.set(f"Editando reparacion {detail.repair_id}.")

    def save_existing_repair(self) -> None:
        if self.edit_repair_id is None or self.edit_client_id is None or self.edit_equipment_id is None:
            messagebox.showerror("Sin seleccion", "Selecciona una reparacion para guardar cambios.", parent=self.root)
            return

        try:
            result = update_repair_record(
                self.db_path_var.get().strip() or "littlenet_database.sqlite3",
                RepairUpdateData(
                    client_id=self.edit_client_id,
                    equipment_id=self.edit_equipment_id,
                    repair_id=self.edit_repair_id,
                    cliente_nombre=self.edit_cliente_nombre_var.get(),
                    cliente_celular=self.edit_cliente_celular_var.get(),
                    cliente_correo=self.edit_cliente_correo_var.get(),
                    equipo_marca=self.edit_equipo_marca_var.get(),
                    equipo_modelo_original=self.edit_equipo_modelo_original_var.get(),
                    equipo_serie=self.edit_equipo_serie_var.get(),
                    fecha_egreso=self.edit_fecha_egreso_var.get(),
                    falla_reportada=self.get_text_widget(self.edit_falla_reportada_text),
                    diagnostico_tecnico=self.get_text_widget(self.edit_diagnostico_tecnico_text),
                    estado=self.selected_status_code(self.edit_status_var.get()),
                    costo=self.parse_cost(self.edit_costo_var.get()),
                    archivos=list(self.edit_multimedia_new_paths),
                ),
            )
        except ValueError as exc:
            self.edit_message_var.set(str(exc))
            messagebox.showerror("Error de validacion", str(exc), parent=self.root)
            return
        except Exception as exc:  # noqa: BLE001
            self.edit_message_var.set(str(exc))
            messagebox.showerror("Error", str(exc), parent=self.root)
            return

        success_message = f"Cambios guardados en reparacion {result.repair_id}. Multimedia agregada: {result.attached_files}."
        self.edit_message_var.set(success_message)
        self.search_message_var.set(success_message)
        messagebox.showinfo("Edicion completada", success_message, parent=self.root)
        self.search_existing_repairs()
        self.load_selected_repair(result.repair_id)

    def refresh_edit_multimedia_list(self) -> None:
        self.edit_multimedia_list.delete(0, tk.END)
        for path in self.edit_multimedia_existing:
            self.edit_multimedia_list.insert(tk.END, f"[existente] {path}")
        for path in self.edit_multimedia_new_paths:
            self.edit_multimedia_list.insert(tk.END, f"[pendiente] {path}")

    def clear_form(self) -> None:
        self.cliente_nombre_var.set("")
        self.cliente_celular_var.set("")
        self.cliente_correo_var.set("")
        self.equipo_marca_var.set("")
        self.equipo_modelo_original_var.set("")
        self.equipo_serie_var.set("")
        self.fecha_ingreso_var.set("")
        self.fecha_egreso_var.set("")
        self.falla_reportada_var.set("")
        self.diagnostico_tecnico_var.set("")
        self.costo_var.set("")
        self.status_var.set(next(iter(self.state_options)))
        self.multimedia_paths.clear()
        self.multimedia_list.delete(0, tk.END)

    def clear_edit_form(self) -> None:
        self.edit_repair_id = None
        self.edit_client_id = None
        self.edit_equipment_id = None
        self.edit_id_label.config(text="-")
        self.edit_cliente_nombre_var.set("")
        self.edit_cliente_celular_var.set("")
        self.edit_cliente_correo_var.set("")
        self.edit_equipo_marca_var.set("")
        self.edit_equipo_modelo_original_var.set("")
        self.edit_equipo_serie_var.set("")
        self.edit_fecha_ingreso_var.set("")
        self.edit_fecha_egreso_var.set("")
        self.edit_costo_var.set("")
        self.edit_status_var.set(next(iter(self.state_options)))
        self.set_text_widget(self.edit_falla_reportada_text, "")
        self.set_text_widget(self.edit_diagnostico_tecnico_text, "")
        self.edit_multimedia_existing = []
        self.edit_multimedia_new_paths = []
        self.refresh_edit_multimedia_list()
        self.edit_message_var.set("Selecciona una reparacion para editarla.")

    def set_text_widget(self, widget: tk.Text, value: str) -> None:
        widget.delete("1.0", tk.END)
        widget.insert("1.0", value)

    def get_text_widget(self, widget: tk.Text) -> str:
        return widget.get("1.0", tk.END).strip()


def main() -> int:
    root = tk.Tk()
    style = ttk.Style()
    if "clam" in style.theme_names():
        style.theme_use("clam")
    RepairsApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
