# Registro local de reparaciones tecnicas

Aplicacion local en Python para registrar reparaciones tecnicas sobre una base SQLite simple y mantenible.

El sistema esta centrado en la reparacion como entidad principal. Los archivos adjuntos se guardan solamente como rutas asociadas a cada reparacion.

## Modelo de datos

La base usa cuatro tablas principales:

- `clientes`: persona o entidad atendida.
- `equipos`: equipo asociado a un cliente.
- `reparaciones`: historial tecnico de cada equipo. Esta es la entidad principal del sistema.
- `multimedia`: rutas de archivos asociados a una reparacion.

Relaciones:

- un cliente puede tener varios equipos;
- un equipo puede tener varias reparaciones;
- una reparacion puede tener varios archivos multimedia.

Estados numericos de `reparaciones.estado`:

- `0`: ingresado
- `1`: en_proceso
- `2`: esperando_repuestos
- `3`: listo_para_entrega
- `4`: entregado

## Entidad principal: reparaciones

El sistema no toma a los archivos como registros principales.

JPG, PNG, PDF, videos y otros archivos:

- no representan casos por si mismos;
- no definen la estructura central de la base;
- solo se vinculan a una reparacion existente mediante la tabla `multimedia`.

En otras palabras, el flujo correcto del sistema es:

`cliente -> equipo -> reparacion -> multimedia`

## Base SQLite

La informacion se guarda en un unico archivo SQLite, por ejemplo:

- `littlenet_database.sqlite3`
- `repairs.db`

Ese archivo contiene los datos estructurados del sistema:

- clientes
- equipos
- reparaciones
- rutas de multimedia asociada

Ese archivo no guarda el contenido binario de fotos, PDFs o videos. Solo guarda sus rutas, para mantener la base simple y liviana.

## Estructura del proyecto

Archivos principales del proyecto:

- `src/import_jobs/schema.py`: define el esquema SQLite, activa foreign keys y contiene helpers de persistencia.
- `src/import_jobs/repair_service.py`: concentra la logica reutilizable para crear o reutilizar cliente y equipo, registrar una reparacion y asociar multimedia.
- `src/import_jobs/gui_repairs.py`: interfaz grafica local en Tkinter para el uso diario.
- `src/import_jobs/manage_repairs.py`: carga manual por linea de comandos usando la misma logica de negocio que la GUI.
- `src/import_jobs/import_zip.py`: herramienta opcional para importar historiales viejos desde un archivo ZIP.
- `src/import_jobs/extractor.py`: heuristicas simples para inferir algunos datos durante la importacion historica.
- `tests/test_sqlite_flow.py`: validaciones minimas del flujo principal y de la importacion.

## Uso recomendado

El uso diario recomendado es registrar casos nuevos directamente en el sistema:

- con la interfaz grafica Tkinter;
- o con la linea de comandos si preferis un flujo manual/scriptable.

La importacion desde ZIP no es el flujo principal. Se conserva como herramienta opcional para migrar historiales tecnicos viejos que ya existen en carpetas y archivos.

## Ejecutar la GUI

Desde la carpeta del proyecto:

```bash
python3 src/import_jobs/gui_repairs.py
```

La GUI permite:

- elegir la base SQLite o usar `littlenet_database.sqlite3`;
- completar cliente, equipo y reparacion;
- dejar `fecha_egreso` vacia cuando la reparacion sigue abierta;
- seleccionar multiples archivos multimedia;
- guardar usando la misma logica de negocio que el CLI;
- buscar reparaciones por cliente, numero de serie, marca, modelo o ID;
- filtrar todas, solo abiertas o por estado;
- seleccionar una reparacion existente para verla completa, editarla y agregar multimedia.

### Buscar y editar reparaciones

En la pestaña `Buscar y editar`:

- usa los filtros superiores para ubicar la reparacion;
- selecciona un resultado de la tabla para cargar el detalle;
- edita cliente, equipo o reparacion segun necesites;
- deja `fecha_egreso` vacia si el equipo todavia no fue entregado;
- agrega archivos nuevos desde la seccion de multimedia;
- guarda cambios sin crear una reparacion nueva.

## Empaquetar la GUI para Windows

La GUI principal se puede distribuir como ejecutable `.exe` usando PyInstaller.

Punto de entrada de la aplicacion:

- `src/import_jobs/gui_repairs.py`

Archivos de build incluidos:

- `pyinstaller/windows_gui.spec`: configuracion de PyInstaller para la GUI.
- `build_windows.bat`: script unico de build para Windows.
- `requirements-build-windows.txt`: dependencia minima para empaquetado.
- `assets/windows/README.md`: convencion para un icono opcional.

### Recomendacion de build

Se recomienda `onedir` para uso interno y pruebas porque:

- es mas facil de depurar;
- suele dar menos problemas con antivirus;
- deja los archivos empaquetados en una carpeta visible.

`onefile` tambien esta preparado y sirve mejor para distribucion simple por archivo unico, pero arranca un poco mas lento y puede ser mas sensible a falsos positivos de antivirus.

### Importante

El `.exe` de Windows debe construirse en Windows para generar un ejecutable nativo de Windows.

### Build paso a paso en Windows

1. Abri `cmd` o PowerShell en la carpeta del proyecto.
2. Crea o activa tu entorno virtual de Python si queres aislar dependencias.
3. Genera la build recomendada:

```bat
build_windows.bat onedir
```

Ese script instala automaticamente las dependencias de build si hacen falta y luego ejecuta PyInstaller.

4. O genera una build de archivo unico:

```bat
build_windows.bat onefile
```

### Que archivo `.exe` se genera

Si usas `onedir`:

- ejecutable: `dist\LittlenetDatabaseGUI\LittlenetDatabaseGUI.exe`

Si usas `onefile`:

- ejecutable: `dist\LittlenetDatabaseGUI.exe`

### Como ejecutarlo

- en `onedir`, hace doble clic sobre `dist\LittlenetDatabaseGUI\LittlenetDatabaseGUI.exe`
- en `onefile`, hace doble clic sobre `dist\LittlenetDatabaseGUI.exe`

La build esta configurada como aplicacion de ventana, asi que abre la GUI sin consola.

### Base SQLite en modo `.exe`

Cuando la aplicacion corre empaquetada como `.exe`, la ruta por defecto de la base es:

- `%LOCALAPPDATA%\Littlenet Database\littlenet_database.sqlite3`

Si ese archivo no existe, la aplicacion lo crea automaticamente al guardar o consultar datos.

Esto evita depender del directorio desde donde se abre el `.exe` y mantiene una ubicacion local predecible para cada usuario de Windows.

Desde la propia GUI se puede cambiar la ruta de la base si queres trabajar con otro archivo SQLite.

### Icono opcional

Si queres personalizar el icono del `.exe`, coloca este archivo antes de compilar:

- `assets/windows/app.ico`

Si no existe, PyInstaller usa el icono por defecto.

### Limitaciones a tener en cuenta

- el `.exe` de Windows no se genera correctamente desde Linux o macOS;
- `onefile` puede iniciar mas lento porque descomprime recursos en tiempo de arranque;
- algunos antivirus son mas agresivos con binarios `onefile`;
- Tkinter depende del Python de build, por eso conviene compilar en una instalacion de Windows limpia y estable.

## Registrar una reparacion por CLI

Desde la carpeta del proyecto:

```bash
python3 src/import_jobs/manage_repairs.py \
  --db littlenet_database.sqlite3 \
  --cliente-nombre "Juan Perez" \
  --cliente-celular "11-5555-1234" \
  --cliente-correo "juan.perez@email.com" \
  --equipo-marca "Lenovo" \
  --equipo-modelo-original "Legion 5 15I" \
  --equipo-modelo-estandarizado "LEGION 5 15I" \
  --equipo-serie "ABC123456" \
  --fecha-ingreso 2026-03-15 \
  --falla-reportada "No enciende" \
  --diagnostico-tecnico "Falla en fuente y limpieza general" \
  --estado 1 \
  --archivo "/ruta/foto1.jpg" \
  --archivo "/ruta/informe.pdf"
```

Tambien se puede seguir usando `src/import_jobs/reprocess_pdfs.py` como alias del cargador manual, aunque el flujo recomendado hoy es `manage_repairs.py` o la GUI.

## Importacion desde ZIP

La importacion desde ZIP es una funcionalidad secundaria, pensada para migracion de historiales existentes.

Sirve cuando ya tenes trabajos viejos organizados en carpetas con documentos, imagenes, videos y otros archivos, y queres convertir ese material en registros estructurados dentro de SQLite.

No debe interpretarse como el corazon del sistema ni como el flujo normal de alta diaria.

Ejemplo de ejecucion:

```bash
python3 src/import_jobs/import_zip.py \
  --zip "/ruta/a/Trabajos.zip" \
  --db littlenet_database.sqlite3 \
  --workspace workspace \
  --logs-dir logs
```

Durante esta importacion:

- se descomprime el ZIP en `workspace/`;
- se recorren carpetas y archivos historicos;
- se crean o reutilizan clientes y equipos cuando es posible;
- se registran reparaciones;
- los archivos se guardan solo como rutas asociadas en `multimedia`.

## Validacion

Hay tests minimos automatizados para validar:

- creacion del esquema SQLite;
- foreign keys activas;
- alta completa `cliente -> equipo -> reparacion -> multimedia`;
- uso de la logica compartida de alta;
- importacion basica desde un ZIP.

Ejecucion:

```bash
python3 -m unittest discover -s tests
```

## Nota conceptual

Si necesitás entender el proyecto rapidamente, quedate con esta idea:

- la base representa reparaciones tecnicas;
- SQLite guarda estructura y relaciones;
- `multimedia` guarda referencias a archivos;
- GUI y CLI son el flujo principal de trabajo;
- la importacion ZIP existe solo como apoyo para migracion historica.
