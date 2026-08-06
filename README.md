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
