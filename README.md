# DataForge Simulator

## Descripción general

DataForge es un framework genérico y reproducible para simular datos empresariales.
No genera filas aleatorias aisladas: los datos emergen de un universo configurado,
reglas de negocio, comportamiento de clientes y eventos temporales.

> Los datos deben emerger de un universo simulado, no de filas aleatorias
> independientes.

El núcleo no está acoplado a un país ni a una industria. Los archivos de Colombia y
taquería incluidos en `examples/` son documentación ejecutable, no convenciones del
runtime.

## ¿Por qué DataForge?

Los generadores tradicionales pueden producir registros válidos individualmente
pero incoherentes entre sí. DataForge mantiene relaciones y causalidad durante una
simulación: una ubicación pertenece a una geografía, ofrece un surtido, recibe
demanda, genera intenciones, cotiza líneas, completa o rechaza transacciones,
modifica inventario y programa reposiciones.

Con el mismo escenario y la misma semilla, la ejecución es reproducible.

## Capacidades actuales

- Configuración YAML de geografía, catálogo de productos y escenario.
- Bootstrap determinista de ubicaciones, productos, clientes, inventario y
  patrones promocionales.
- Demanda temporal, comportamiento de clientes, pricing, baskets y líneas de
  transacción.
- Movimientos de inventario, señales de reorden y reposición con lead time.
- Métricas por tick, totales de corrida y validación de invariantes.
- Salida operacional incremental con liberación del histórico por tick.
- Exportación física CSV y Parquet, individual o simultánea.
- CLI con Typer y API síncrona con FastAPI.

## Cómo funciona

```text
Scenario
   ↓
Bootstrap Generators
   ↓
SimulationRunner
   ↓
SimulationOrchestrator
   ↓
Simulation Engines
   ↓
Operational Data Model
   ↓
OperationalDataSink
   ├── CSV
   └── Parquet
```

El pipeline estándar ejecuta, en orden, `TimeEngine`, `PromotionEngine`,
`DemandEngine`, `CustomerBehaviorEngine`, `PricingEngine`, `TransactionEngine`,
`InventoryEngine`, `ReplenishmentEngine`, `MetricsEngine` y
`StateValidationEngine`.

Cuando existe un sink de exportación, cada ciclo sigue este orden:

```text
tick → validate → operational records → sink → evict tick history → next tick
```

La ejecución sin sink conserva el histórico completo para inspección. La
exportación incremental conserva el estado maestro y operativo necesario para los
ticks futuros, pero libera los contextos históricos ya validados y escritos.

## Instalación

Requisitos:

- Python 3.12 o superior.
- [uv](https://docs.astral.sh/uv/).
- Docker, opcional.

Instala el proyecto y sus dependencias de desarrollo:

```bash
uv sync --dev
```

Los comandos siguientes pueden ejecutarse como `uv run dataforge ...`. Si el
entorno virtual está activo, también puede usarse directamente `dataforge ...`.

## Inicio rápido

Ejecuta el escenario oficial de un mes:

```bash
uv run dataforge simulate examples/scenarios/taqueria-colombia.yaml
```

Exporta sus datasets a CSV:

```bash
uv run dataforge simulate examples/scenarios/taqueria-colombia.yaml \
  --format csv \
  --output outputs/example-csv
```

Exporta a Parquet:

```bash
uv run dataforge simulate examples/scenarios/taqueria-colombia.yaml \
  --format parquet \
  --output outputs/example-parquet
```

Exporta ambos formatos durante una única simulación:

```bash
uv run dataforge simulate examples/scenarios/taqueria-colombia.yaml \
  --format both \
  --output outputs/example-both
```

`--format` y `--output` deben proporcionarse juntos. DataForge no sobrescribe los
archivos esperados de una corrida anterior.

## Configuración de escenarios

La configuración pública se divide en tres niveles:

1. [Geografía](examples/geography/colombia.yaml): país, regiones, áreas
   administrativas y ciudades.
2. [Catálogo](examples/products/taqueria.yaml): moneda, categorías y productos con
   precios, costos y estado.
3. [Escenario](examples/scenarios/taqueria-colombia.yaml): rango temporal, semilla y
   parámetros de generación y simulación.

Las rutas `geography.source` y `products.source` se resuelven respecto al archivo
del escenario, no respecto al directorio de trabajo. El nombre y la ruta no tienen
semántica de negocio: `mexico.yaml`, `farmacia.yaml` o `my-company.yaml` son nombres
válidos cuando su contenido cumple el contrato correspondiente.

El rango base de `demand.base_demand_min` y `base_demand_max` representa demanda
esperada por hora y se escala según la duración del tick. Los lead times de
reposición se expresan en días, independientemente de `tick_unit`. Las promociones
son patrones anuales recurrentes con ocurrencias deterministas por año.

`configs/scenarios/smoke-test.yaml` es un fixture técnico pequeño para pruebas; no
es el ejemplo público de negocio.

## Ejecución de simulaciones

La CLI acepta un path de escenario. Para escenarios bajo `configs/scenarios/`,
también acepta el nombre sin extensión:

```bash
uv run dataforge simulate smoke-test
uv run dataforge simulate configs/scenarios/smoke-test.yaml
```

La salida muestra ticks, ejecuciones de engines y métricas acumuladas de toda la
corrida. Una `Transaction` representa un basket o checkout finalizado;
`TransactionLine` representa el resultado de una línea de producto.

## Exportación de datos

Cada dataset lógico genera exactamente un archivo. CSV serializa valores de forma
textual; Parquet conserva tipos físicos, incluidos `Decimal`, fechas y timestamps.
Ambos representan los mismos datasets lógicos.

CSV:

```text
output/
├── countries.csv
├── transactions.csv
└── metrics.csv
```

Parquet:

```text
output/
├── countries.parquet
├── transactions.parquet
└── metrics.parquet
```

Ambos formatos:

```text
output/
├── csv/
└── parquet/
```

La exportación es incremental y utiliza buffers acotados; no necesita conservar en
memoria el histórico completo de la simulación.

## Operational Data Model

El Operational Data Model (ODM) separa el dominio simulado de los formatos físicos:

```text
Simulation Domain → ODM → CSV / Parquet
```

El ODM es lógico e independiente del formato. Define datasets, columnas, tipos,
claves y relaciones. Los exporters traducen ese contrato sin recalcular reglas de
negocio.

## Datasets generados

| Dataset | Contenido |
| --- | --- |
| `countries` | Países configurados. |
| `regions` | Regiones geográficas. |
| `administrative_areas` | Divisiones administrativas y sus regiones. |
| `cities` | Ciudades y sus áreas administrativas. |
| `locations` | Sedes comerciales generadas. |
| `categories` | Categorías del catálogo. |
| `products` | Productos, precios, costos y atributos generados. |
| `customers` | Clientes sintéticos y preferencias de comportamiento. |
| `promotions` | Patrones promocionales anuales. |
| `promotion_targets` | Targets asociados a promociones. |
| `transactions` | Baskets o checkouts agregados. |
| `transaction_lines` | Resultados por producto dentro de cada basket. |
| `transaction_line_promotions` | Promociones aplicadas a líneas. |
| `inventory` | Snapshot final del surtido y stock. |
| `inventory_movements` | Salidas por venta y entradas por reposición. |
| `replenishments` | Solicitudes de reposición y su estado final. |
| `metrics` | Métricas operacionales por tick. |

## API

Inicia la API local:

```bash
uv run dataforge run
```

OpenAPI queda disponible en `http://127.0.0.1:8000/docs`.

Endpoints actuales:

- `GET /ping`: health check.
- `POST /simulations/preview`: preview determinista de entidades genéricas.
- `POST /simulation/verify`: ejecuta y valida un escenario local.
- `POST /simulation/export`: ejecuta y exporta al filesystem del servidor.

Ejemplo de exportación síncrona:

```http
POST /simulation/export
Content-Type: application/json

{
  "scenario": "examples/scenarios/taqueria-colombia.yaml",
  "format": "both",
  "output": "api-example"
}
```

La API restringe `output` a una ruta relativa bajo `outputs/`. No devuelve archivos
binarios ni crea trabajos en background.

## Estructura del proyecto

```text
src/dataforge/
├── api/
├── bootstrap/
├── cli/
├── config/
├── core/
├── engines/
├── export/
├── generators/
├── runtime/
└── scenario/
```

Los ejemplos públicos viven en `examples/`; los fixtures técnicos y configuraciones
internas permanecen en `configs/`.

## Calidad y pruebas

Ejecuta todas las validaciones locales principales:

```bash
uv run dataforge check
```

Ejecuta Pytest directamente:

```bash
uv run pytest
```

La suite incluye pruebas unitarias, integración del pipeline, smoke tests y
regresiones temporales. Las pruebas largas están marcadas con `slow`:

```bash
uv run pytest -m slow
```

Construcción opcional del contenedor:

```bash
docker build -t dataforge-simulator .
```

## Reproducibilidad

La misma configuración, la misma semilla y el mismo instante inicial producen la
misma simulación. DataForge preserva consistencia de prefijo: ampliar el horizonte
no modifica el bootstrap ni los ticks que ya pertenecían al horizonte corto.

## Alcance actual del MVP

El MVP incluye el pipeline empresarial configurable, validación, métricas y
exportación operacional CSV/Parquet. Actualmente no incluye:

- Excel.
- SQL, DuckDB ni persistencia en bases de datos.
- Star Schema o analytics dimensionales.
- selección dinámica de engines, plugins o registries.
- almacenamiento cloud.
- jobs asíncronos o ejecución distribuida.
- descargas ZIP desde la API.

Estas exclusiones delimitan el alcance actual y no constituyen compromisos de
roadmap.

## Contribuir

Antes de enviar cambios, conserva los contratos públicos, añade pruebas acordes al
cambio y ejecuta:

```bash
uv sync --dev
uv run dataforge check
```
