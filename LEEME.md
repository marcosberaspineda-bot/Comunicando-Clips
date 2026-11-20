# Comunicando Clips 1.2 — Editor local de clips para Mac M2

## Qué incluye y qué no

Esta es una **aplicación de escritorio con interfaz gráfica** (PySide6), no una web. Incluye motor Python, pruebas automatizadas y **script que compila `.app` y crea un `.dmg` real en macOS**. El ZIP NO contiene todavía un `.dmg` ya compilado: la compilación nativa y `hdiutil` requieren macOS. No declares finalizado el DMG hasta ejecutarlo en Mac. También se puede generar con el flujo GitHub Actions incluido.

## Cómo conseguir `Comunicando_Clips_Mac_M2.dmg`

1. Descomprime el ZIP **en tu Mac M2**.
2. Instala [Homebrew](https://brew.sh) si no está instalado.
3. Entra a `comunicando_clips` y haz **clic derecho → Abrir** en `Crear_DMG_en_Mac.command`.
4. El script instala FFmpeg, Python 3.12 y dependencias, corre las pruebas, compila `Comunicando Clips.app`, genera y verifica el DMG.
5. El resultado estará en `comunicando_clips/entrega/Comunicando_Clips_Mac_M2.dmg`.
6. Abre el DMG y arrastra la aplicación a la carpeta Aplicaciones.

**IMPORTANTE:** FFmpeg de Homebrew debe seguir instalado para analizar y exportar. El DMG no empaqueta FFmpeg. El primer uso de Whisper descarga el modelo, y YouTube requiere internet. Los videos locales se procesan localmente. El DMG se crea con firma ad hoc, pero **no está notarizado** por Apple; macOS puede pedir permiso para abrirlo. La compilación requiere internet para instalar componentes. Se necesita espacio libre suficiente para dependencias y modelos.

**No abras un archivo `.dmg` falso o renombrado:** solo un DMG creado por `hdiutil` en macOS es el instalador adecuado.

## Funciones del programa

- Acepta videos locales `.mp4`, `.mov`, `.mkv`, `.m4v`, `.webm`, `.avi` y enlaces de YouTube. Solo usa videos que tengas derecho a procesar.
- Detecta hasta **15** ventanas interesantes, basándose en transcripción local con `faster-whisper` y ritmo/intensidad del audio; la puntuación **no garantiza** viralidad.
- Puedes seleccionar duración mínima y máxima; por defecto 30–90 segundos.
- Reproduce los fragmentos y cambia los segundos de inicio y final antes de guardarlos.
- Exporta MP4 H.264, 1080×1920, 9:16, en recorte central o con fondo desenfocado.
- Genera subtítulos incrustados si está disponible la transcripción y el FFmpeg instalado admite el filtro `subtitles`.
- **Cada clip debe aprobarse individualmente** para exportarse. No sobrescribe un clip anterior.
- Guarda un inventario de los clips y la transcripción en un JSON para registro.

## Limitaciones conocidas

- No hay seguimiento inteligente de rostros, subtítulos palabra por palabra ni editor de palabras.
- Puedes reabrir proyectos guardados desde «Archivo → Abrir proyecto guardado…» o desde el botón «Abrir proyecto…». El video original debe conservarse en su ruta.
- Los modelos Whisper se ejecutan por CPU, aunque el Mac M2 tenga GPU; videos largos pueden tardar.
- El editor cambia inicios/finales y estilo del encuadre; no es un editor multipista.
- Algunos enlaces de YouTube pueden fallar por restricciones, derechos, autenticación o cambios de plataforma.
- No se ha verificado el lanzamiento de la interfaz ni el DMG en un dispositivo macOS M2. Las pruebas automatizadas del motor se han ejecutado en Linux.

## Archivos principales

- `app.py` — aplicación de escritorio PySide6.
- `engine.py` — detección, voz, subtítulos, descarga y exportación.
- `Crear_DMG_en_Mac.command` — compila `.app` Apple Silicon y crea DMG mediante `hdiutil`.
- `Instalar_en_Mac.command` — acceso compatible que ejecuta el constructor DMG.
- `Abrir_sin_compilar.command` — modo de desarrollo.
- `.github/workflows/crear-dmg-mac.yml` — alternativa para ejecutar compilación ARM64 en GitHub Actions; requiere subir este proyecto a un repositorio y ejecutar el flujo (archivo DMG disponible como artefacto del flujo).
- `tests/test_engine.py` — pruebas del motor FFmpeg, subtítulos, URLs y proyecto.
- `tests/test_gui.py` — prueba de arranque de controles PySide6 en macOS (por ejecutar en entorno Mac).

## Privacidad

El procesamiento de videos locales no envía su contenido a servidores externos. Las conexiones a internet se usan para dependencias, descarga del modelo de voz y videos de YouTube cuando los solicitas.

## Verificación independiente del instalador

Después de que se construya en macOS, ejecuta `Verificar_instalador_en_Mac.command`. Monta el DMG en modo lectura, comprueba que contiene `Comunicando Clips.app` y un ejecutable, verifica su firma ad hoc y desmonta la imagen. El flujo de GitHub Actions comprueba además que el ejecutable es Mach-O arm64. No sustituye pruebas manuales de importación y exportación en un Mac.

## Compilación en GitHub Actions (sin compilar en tu computadora)

Publica **el contenido de la carpeta `comunicando_clips` en la raíz** de un repositorio de GitHub (incluyendo la carpeta `.github`, que está oculta en Finder). En GitHub abre **Actions → Crear instalador DMG para Mac M2 → Run workflow**. Tras una compilación correcta descarga el artefacto `Comunicando-Clips-Mac-M2-DMG`, que contiene el archivo `.dmg`. GitHub puede requerir activar Actions y disponer de capacidad de ejecución. El instalador no estará creado hasta que el flujo haya terminado correctamente.
