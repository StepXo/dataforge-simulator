# DataForge Simulator

DataForge Simulator es la base de un futuro framework para simular datos
empresariales sint?ticos. La versi?n actual ofrece una API REST con un endpoint de
salud y una previsualizaci?n reproducible de entidades gen?ricas.

Todav?a no existen clientes, productos, ventas, inventarios ni otros dominios
empresariales concretos.

## Requisitos

- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- Docker (opcional, para construir y ejecutar la imagen)

## Instalaci?n y ejecuci?n local

```bash
uv sync --dev
uv run uvicorn dataforge.main:app --reload
```

La documentaci?n OpenAPI queda disponible en `http://127.0.0.1:8000/docs`.

## Developer CLI

La CLI agrupa las operaciones locales habituales. Puede ejecutarse a trav?s de
`uv`:

```bash
uv run dataforge setup
uv run dataforge run
uv run dataforge test
uv run dataforge lint
uv run dataforge format
uv run dataforge typecheck
uv run dataforge check
uv run dataforge dev --test
uv run dataforge dev --check
```

| Comando | Prop?sito |
| --- | --- |
| `setup` | Sincroniza el entorno y las dependencias de desarrollo. |
| `run` | Inicia la API con recarga autom?tica. |
| `test` | Ejecuta Pytest y permite reenviar argumentos despu?s de `--`. |
| `lint` | Comprueba el c?digo con Ruff; `--fix` aplica correcciones. |
| `format` | Comprueba el formato; `--write` aplica cambios. |
| `typecheck` | Comprueba los tipos de `src` con mypy. |
| `check` | Ejecuta formato, lint, tipos y pruebas como las validaciones principales de CI. |
| `dev` | Inicia la API; `--test` o `--check` validan antes de iniciarla. |

`setup` prepara el entorno, `run` solo inicia la API, `check` reproduce localmente
las validaciones principales de CI y `dev --check` valida antes de iniciar la API.

Despu?s de activar el entorno virtual o instalar el proyecto en modo editable,
tambi?n se puede omitir `uv run`:

```bash
dataforge run
dataforge check
```

Ejemplos adicionales:

```bash
uv run dataforge run --host 127.0.0.1 --port 8080 --no-reload
uv run dataforge test -- -k preview
uv run dataforge lint --fix
uv run dataforge format --write
```

## Endpoints

### `GET /ping`

Responde con HTTP 200:

```json
{
  "status": "ok",
  "message": "pong"
}
```

### `POST /simulations/preview`

Genera una previsualizaci?n en memoria:

```json
{
  "seed": 42,
  "start_date": "2026-01-01",
  "end_date": "2026-01-07",
  "entity_count": 5
}
```

Ejemplo de respuesta:

```json
{
  "simulation_id": "preview-42",
  "seed": 42,
  "period": {
    "start_date": "2026-01-01",
    "end_date": "2026-01-07",
    "days": 7
  },
  "entities": [
    {
      "id": "entity-001",
      "activity_factor": 1.14
    },
    {
      "id": "entity-002",
      "activity_factor": 0.53
    }
  ]
}
```

La respuesta contiene exactamente la cantidad solicitada. El periodo incluye ambos
extremos y cada factor est? entre `0.50` y `1.50`, redondeado a dos decimales. La
misma configuraci?n y semilla generan exactamente la misma respuesta; cambiar la
semilla cambia la secuencia sin alterar el estado aleatorio global.

La API responde HTTP 422 ante campos ausentes o tipos inv?lidos, semillas fuera de
`0..4294967295`, cantidades fuera de `1..1000` o una fecha final anterior a la
inicial.

## Domain Events

Un Domain Event representa algo que ya ocurri? dentro de la aplicaci?n. Cada evento
contiene un UUID, un tipo, una marca de tiempo y un payload tipado.

El `EventBus` es s?ncrono y funciona exclusivamente en memoria: primero guarda cada
evento y luego llama a los handlers registrados para su tipo. El `EventStore`
mantiene temporalmente los eventos durante la vida del proceso y permite
consultarlos, contarlos y limpiarlos; no utiliza persistencia.

Actualmente existe un solo evento, `EntityCreated`. El preview publica uno por cada
entidad gen?rica generada con su identificador y factor de actividad. Un handler lo
registra en la consola mediante el sistema est?ndar de logging. Los eventos son
infraestructura interna y no forman parte de la respuesta HTTP.

## Core Domain

El Core Domain define el lenguaje b?sico compartido sin depender de HTTP,
persistencia ni motores concretos. `Entity` es la base inmutable para cualquier
objeto identificable y contiene solamente un UUID, su fecha de creaci?n y metadata
opcional. `Identifier` representa un identificador basado en UUID.

`DateRange` representa un periodo calendario v?lido y calcula su duraci?n inclusiva.
`SimulationContext` agrupa la semilla, el rango de fechas, el generador aleatorio y
el bus de eventos utilizados durante una ejecuci?n. El preview existente utiliza
estas abstracciones sin modificar su contrato HTTP.

Definir primero este n?cleo mantiene consistentes las primitivas compartidas y evita
acoplar las simulaciones a transporte, almacenamiento o infraestructura externa.

## Calidad y pruebas

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```

Para aplicar el formato autom?ticamente:

```bash
uv run ruff format .
```

## Docker

```bash
docker build -t dataforge-simulator .
docker run --rm -p 8000:8000 dataforge-simulator
```

## Alcance actual

Esta versi?n solo genera entidades gen?ricas en memoria. No incluye dominios de
negocio, persistencia, bases de datos, archivos de configuraci?n o exportaci?n,
autenticaci?n, procesamiento as?ncrono, interfaces web ni despliegue.
