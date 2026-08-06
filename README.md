# DataForge Simulator

DataForge Simulator será un framework para simular datos empresariales sintéticos.
Actualmente contiene únicamente una API REST mínima y ejecutable con un endpoint de
salud, además de controles automatizados de calidad e integración continua.

## Requisitos

- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- Docker (opcional, para construir y ejecutar la imagen)

## Instalación

```bash
uv sync --dev
```

## Ejecución local

```bash
uv run uvicorn dataforge.main:app --reload
```

La documentación OpenAPI queda disponible en `http://127.0.0.1:8000/docs`.

## Calidad y pruebas

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```

Para aplicar el formato automáticamente:

```bash
uv run ruff format .
```

## Docker

```bash
docker build -t dataforge-simulator .
docker run --rm -p 8000:8000 dataforge-simulator
```

## Endpoint disponible

`GET /ping` responde con HTTP 200:

```json
{
  "status": "ok",
  "message": "pong"
}
```

## Alcance actual

Esta primera versión no incluye motores de simulación, lógica de dominio,
persistencia, bases de datos, autenticación, mensajería, interfaces web ni
despliegue. Es exclusivamente la base técnica y su flujo de integración continua.
