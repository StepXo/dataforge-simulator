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

## Simulation Runtime Contracts

`SimulationClock` representa el estado temporal determinista de una ejecuci?n. Usa
un `TimeRange` inclusivo y una granularidad configurable sin superar el instante
final.

`SimulationEngine` es un protocolo estructural con un ?nico m?todo `execute`, que
recibe el `SimulationContext` compartido y el `SimulationClock`. Los diez engines del MVP comparten este contrato y el `SimulationOrchestrator`
los ejecuta en orden explicito para cada tick.

## Simulation Runtime

`ScenarioDefinition` describe la configuracion y `SimulationRunner` ensambla un
runtime nuevo para cada llamada a `run()`. El `BootstrapRunner` crea el universo
inicial, el `SimulationOrchestrator` ejecuta los diez engines por tick y el
`SimulationResult` conserva los summaries reales junto con el estado final.

```text
Scenario YAML
      |
ScenarioDefinition
      |
SimulationRunner
      +-- BootstrapRunner
      +-- SimulationOrchestrator
                  |
          SimulationResult
```

El pipeline es explicito y completamente en memoria. La CLI `dataforge simulate`
esta disponible, sin persistencia ni exportacion de resultados.
## Simulation State and Bootstrap

`SimulationState` representa el estado compartido que vive exclusivamente en
memoria durante una ejecuci?n. Organiza colecciones por nombre sin crear categor?as
de dominio por adelantado. Cada `StateCollection` almacena valores tipados mediante
claves ?nicas y conserva su orden de inserci?n.

Estado y eventos tienen responsabilidades diferentes: el estado describe lo que
existe actualmente, mientras un evento registra algo que ocurri?. El estado no es
una base de datos y no existe persistencia en esta versi?n.

Un `BootstrapGenerator` prepara una parte del estado antes del primer tick.
`BootstrapRunner` ejecuta esos generadores una vez cada uno y en el orden recibido,
compartiendo el mismo contexto. Durante los ticks, los engines podr?n consultar y
actualizar ese estado. Todav?a no existen generadores concretos.

```text
BootstrapRunner
    -> SimulationState inicial
    -> SimulationOrchestrator
    -> Estado actualizado durante los ticks
```

## Time Engine

`TimeEngine` es el primer simulation engine concreto. Se ejecuta una vez por tick,
interpreta el `SimulationClock` y crea un `TemporalContext` inmutable sin avanzar el
reloj. Conserva un contexto por tick en la colecci?n `temporal_context` de
`SimulationState` y publica un evento `TimeContextGenerated` despu?s de almacenarlo.

```text
SimulationClock
    -> TimeEngine
    -> TemporalContext
        -> SimulationState
        -> TimeContextGenerated
```

Los engines posteriores pueden consultar este contexto siempre que aparezcan
despu?s de `TimeEngine` en el orden expl?cito del orquestador. Actualmente se
interpretan ticks diarios y horarios, sin festivos ni reglas comerciales. Un
contexto temporal no representa una venta:

```text
1 tick
1 ejecuci?n de TimeEngine
1 TemporalContext

El mismo tick podr?a producir posteriormente:
40 ventas
95 detalles de venta
95 movimientos de inventario
```

## Geography Configuration

La geograf?a de referencia se carga desde YAML y el c?digo no depende de Colombia.
El esquema valida `Country`, `Region`, `AdministrativeArea` y `City`, incluyendo sus
relaciones. Actualmente existe un ejemplo peque?o en
`configs/geography/colombia.yaml`; todav?a no genera locations.

```python
from pathlib import Path

from dataforge.configuration.geography import load_geography

geography = load_geography(Path("configs/geography/colombia.yaml"))
```

## Geography Generator

`GeographyDefinition` describes reference geography. During bootstrap,
`GeographyGenerator` converts it into `countries`, `regions`,
`administrative_areas`, `cities`, and synthetic `locations`. It does not
know concrete countries; location characteristics are reproducible from the seed.

```text
colombia.yaml -> load_geography() -> GeographyDefinition
               -> GeographyGenerator -> SimulationState
```

This generator runs during bootstrap, never once per tick.
## Product Bootstrap

El catálogo proviene de YAML y `ProductGenerator` no conoce un negocio concreto.
`configs/products/taqueria.yaml` contiene categorías y productos con precios y
costos `Decimal`. El generator calcula `base_margin` como proporción redondeada a
cuatro decimales y genera un `activity_factor` reproducible desde la seed. Se
ejecuta durante bootstrap y no genera ventas ni inventario.

```text
taqueria.yaml -> load_product_catalog() -> ProductCatalogDefinition
               -> ProductGenerator -> categories / products -> SimulationState
```

## Customer Bootstrap

`CustomerGenerator` crea durante bootstrap una población inicial reproducible y no
genera compras. Cada cliente referencia ciudades, regiones y locations existentes,
y conserva segmento, frecuencia base mensual, canal preferido, sensibilidad a
promociones y factor de actividad para futuros engines.

```text
GeographyGenerator -> locations -> CustomerGenerator -> customers -> SimulationState
```

`CustomerGenerator` no es `CustomerBehaviorEngine`: no ejecuta comportamiento por
tick ni crea transacciones.
## Inventory Bootstrap

`InventoryBootstrapGenerator` crea el stock inicial antes de los ticks. Cada
`InventoryItem` representa una combinación Product x Location y no un movimiento
histórico. La disponibilidad y cantidades son reproducibles; el cálculo pondera la
variación aleatoria, la capacidad de `Location` y el `activity_factor` de Product.
El futuro `InventoryEngine` será responsable de modificar este estado.

```text
locations + products
        ↓
InventoryBootstrapGenerator
        ↓
inventory
        ↓
SimulationState
```
## Promotion Bootstrap

`PromotionBootstrapGenerator` crea un calendario inicial reproducible y no aplica
promociones. Cada `Promotion` tiene periodo, target, canal, descuento proporcional
y demand lift potencial dentro de `SimulationState`. El futuro `PromotionEngine`
decidirá cuáles están activas en cada tick.

```text
products + geography
        ↓
PromotionBootstrapGenerator
        ↓
promotions
        ↓
SimulationState
```
## Promotion Engine

`PromotionEngine` se ejecuta por tick después de `TimeEngine`. Consume el calendario
`promotions` y el `TemporalContext` actual, determina activación temporal inclusiva
y guarda un `PromotionContext` histórico. No aplica descuentos, demand lift ni
resuelve targets para transacciones concretas.

```text
TimeEngine
    ↓
TemporalContext
    ↓
PromotionEngine
    ↓
PromotionContext
```
## Demand Engine

`DemandEngine` se ejecuta después de `TimeEngine` y `PromotionEngine`, y genera
demanda potencial por cada combinación activa Location x Product definida por el
inventario. No genera ventas ni descuenta stock: incluso stock cero conserva la
intención de compra y `requested_units` puede superar las existencias. Las
promociones de canal `all` pueden aumentar demanda; las específicas de canal aún
no se aplican. Las unidades se materializan mediante stochastic rounding
reproducible.

```text
TimeEngine
   ↓
PromotionEngine
   ↓
DemandEngine
   ↓
DemandContext
```
## Demand temporal semantics

`base_demand_min` y `base_demand_max` representan demanda base esperada por
hora para cada Location x Product. Un tick horario conserva esa escala; un tick
diario suma el perfil intradiario de sus 24 horas en lugar de aplicar el factor
de medianoche a todo el dia. `max_requested_units_per_item` permanece como limite
de seguridad por DemandRecord y tick. Cambiar `TickUnit` modifica la granularidad,
no la tasa comercial subyacente.

## Customer Behavior Engine

`CustomerBehaviorEngine` se ejecuta después de `DemandEngine`. Consume el
`DemandContext` del tick y asigna sus unidades a clientes elegibles mediante pesos
reproducibles basados en segmento, frecuencia de compra, factor de actividad,
location preferida, canal preferido y sensibilidad a promociones. Produce
`PurchaseIntent` y conserva como demanda no asignada cualquier unidad que no pueda
asociarse a un cliente. Los intents del mismo tick que comparten customer, Location y canal reciben el mismo `basket_id` determinista.

El engine no crea ventas, no calcula precios y no comprueba ni descuenta stock. En
cada tick se conserva la igualdad `assigned + unassigned = demand`.
`PurchaseIntent.location_id` identifica la Location de fulfillment y, en este MVP,
solo puede pertenecer a la misma ciudad y región del cliente y estar abierta.

`InventoryItem` define el surtido comercial Location × Product: si no existe, el
producto no se ofrece en esa sede. Si existe activo con `current_stock = 0`, el
producto sí se ofrece pero está agotado; la intención de compra continúa siendo
válida para poder medir demanda perdida posteriormente.

```text
DemandEngine
    ↓
DemandContext
    ↓
CustomerBehaviorEngine
    ↓
PurchaseIntents
```
## Pricing Engine

`PricingEngine` consume cada `PurchaseIntent` y produce exactamente un `PriceQuote`
a partir de `Product.base_price` y las promociones activas que coinciden en target y
canal. Si varias promociones aplican, utiliza solo la de mayor descuento; los
empates conservan el orden del `PromotionContext`. Una promoción dirigida a una
Location nunca afecta cotizaciones de otra sede. Cada `PriceQuote` conserva el `basket_id` de su intent.

Todo valor monetario usa `Decimal`, precisión de centavos y `ROUND_HALF_UP`. El
engine no crea ventas, no decide fulfillment y no modifica productos, promociones
o inventario. Valida que Location × Product pertenezca al surtido activo, pero no
exige stock positivo:

```text
InventoryItem inexistente → no se puede cotizar
InventoryItem activo con stock=0 → sí se puede cotizar

PurchaseIntent
    ↓
PricingEngine
    ↓
PriceQuote
```

## Transaction Engine

`Transaction` representa un basket/check-out finalizado, no un producto. Agrupa
intents con el mismo `basket_id`, customer, Location, canal y tick. Cada producto
se conserva como `TransactionLine` con quantity, pricing y resultado line-level
all-or-nothing.

```text
Basket -> Transaction
Product inside Basket -> TransactionLine
```

Un basket puede quedar `completed`, `partially_completed` o `rejected`. El ledger
local Location x Product evita overselling; las l??neas rejected conservan valor
potencial como `lost_sales_amount`. `TransactionEngine` decide resultados pero no
muta inventario.

## Inventory Engine

`InventoryEngine` consume el `TransactionContext` y aplica exclusivamente las
`TransactionLine` completed, incluso dentro de un basket parcial. Cada venta
reemplaza el `InventoryItem` inmutable por
una nueva instancia con el stock descontado y produce un `InventoryMovement`.
El stock resultante permanece en `SimulationState` y es visible en ticks posteriores.

Al finalizar el tick genera senales para items modificados que quedan en o debajo
del reorder point y para los que llegan a stock cero. Las senales no reponen stock.
El engine valida todas las cantidades acumuladas antes de mutar y nunca decide si
una venta debe completarse:

```text
TransactionEngine decides
        |
completed Transactions
        |
InventoryEngine applies
        |
Inventory state updated
```

El contexto se guarda antes de publicar eventos. El estado en memoria no ofrece
rollback general si ocurre un fallo inesperado al guardar despues de los reemplazos.
## Replenishment Engine

`ReplenishmentEngine` consume los `ReorderSignal` del tick y programa recepciones
futuras con un lead time reproducible expresado en dias. El engine convierte esa
duracion a ticks usando la resolucion del reloj (1 dia son 24 ticks horarios o
1 tick diario). Conserva como maximo una
reposicion pending por InventoryItem y completa vencimientos antes de procesar
nuevas senales. Al recibir stock reemplaza el `InventoryItem` inmutable hasta
`max_stock` sin superarlo y publica un movimiento de tipo `replenishment`.

```text
InventoryEngine
    |
ReorderSignal
    |
ReplenishmentEngine
    |
PendingReplenishment
    |
future tick -> stock replenished
```

No existen proveedores, ordenes de compra ni reposicion instantanea: mientras se
espera el due tick, el producto puede permanecer agotado.
## Metrics Engine

`MetricsEngine` se ejecuta al final del flujo comercial y crea un snapshot read-only
por tick. Resume demanda, intents, cotizaciones, transacciones completadas y
rechazadas, movimientos de inventario y reposiciones sin recalcular ni modificar
el estado de negocio.

```text
Demand
  |
Intents
  |
Transactions
  |
Inventory
  |
Replenishment
  |
MetricsEngine
```

La demanda no asignada representa unidades que no llegaron a un intent; lost sales
representa el valor cotizado de transacciones rechazadas. Son metricas distintas.
Los snapshots se conservan en `metrics_context` y no incluyen agregados historicos.
## State Validation Engine

`StateValidationEngine` es el ultimo engine del tick. No genera negocio ni repara
estado: valida relaciones maestras y coherencia entre demand, intents, pricing,
transactions, inventory, replenishment y metrics. Cualquier inconsistencia produce
un `ValueError` antes de crear un contexto exitoso o publicar su evento.

```text
MetricsEngine
    |
StateValidationEngine
    |
tick valido
    |
clock.advance()
```

La validacion es read-only respecto al estado comercial y conserva un snapshot
`validation_context` por tick.
## Scenario Configuration

Un scenario describe mediante YAML externo el universo y los parametros de una
simulacion completa, pero no contiene logica de negocio ni ejecuta el motor. Puede
referenciar una geografia y un catalogo de productos externos; sus rutas relativas
se resuelven respecto al propio archivo del scenario, no al directorio de trabajo.

```text
Scenario YAML
      |
load_scenario()
      |
ScenarioDefinition
```

El ejemplo `configs/scenarios/taqueria-colombia.yaml` reutiliza las configuraciones
actuales de bootstrap y engines. `SimulationRunner` consume este contrato para
construir un runtime nuevo en cada ejecucion.

Los nombres de archivo no tienen semantica para DataForge. `taqueria-colombia.yaml`,
`colombia.yaml` y `taqueria.yaml` son ejemplos, no convenciones del runtime. Una
geografia o catalogo puede usar cualquier nombre y directorio: el contenido
validado, nunca el filename o sus fragmentos de ruta, determina su significado.
## Simulation CLI

El comando `simulate` ejecuta un scenario completo mediante `SimulationRunner` y
muestra ticks, ejecuciones y `Run totals` acumulados desde todos los snapshots
`MetricsContext`; nunca presenta el ultimo tick como total de la corrida.

```bash
dataforge simulate configs/scenarios/taqueria-colombia.yaml
dataforge simulate taqueria-colombia
```

## Runtime Verification API

`POST /simulation/verify` ejecuta sincronicamente el mismo `SimulationRunner` para
verificar el pipeline completo. `scenario_path` debe señalar un archivo local
accesible por el proceso de la aplicacion.

```json
{
  "scenario_path": "configs/scenarios/taqueria-colombia.yaml"
}
```

La respuesta es un resumen tipado; ninguna de estas superficies persiste estado,
exporta resultados, acepta uploads o ejecuta trabajos en background.
## Horizon invariance

DataForge preserva *horizon invariance*: con la misma seed, inicio y configuraci??n,
un run corto es el prefijo del run largo. Extender `end_datetime` no modifica
locations, products, customers, inventario inicial, patrones promocionales ni los
ticks ya simulados. Las Locations del bootstrap est??n abiertas al inicio; futuras
aperturas requieren una feature runtime dedicada.

Las m??tricas `Out-of-stock events/signals` cuentan eventos donde un item modificado
termina en cero; no representan productos ??nicos actualmente agotados.

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
