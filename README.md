
# Sistema Inteligente de Aforo Vehicular — Panel del Vigilante

Proyecto en Python preparado para el prototipo de control de aforo vehicular
mediante visión por computadora.

## Qué está preparado

1. Panel para el vigilante.
2. Configuración de espacios del estacionamiento.
3. Carga de una fotografía de referencia.
4. Marcado de cada espacio con 4 clics:
   A1, A2, A3, ...
5. Guardado de la configuración.
6. Carga de fotografías individuales.
7. Análisis de una carpeta completa.
8. Detección de vehículos con YOLO.
9. Determinación de espacio ocupado/libre mediante los polígonos configurados.
10. Estimación básica del color predominante del vehículo.
11. Mapa visual de espacios.
12. Recomendación del primer espacio disponible para el vigilante.
13. Historial de análisis.
14. Guardado de fotografías procesadas.

## Primera ejecución

Instalar:

```bash
pip install -r requirements.txt
```

Ejecutar:

```bash
python app.py
```

### Paso 1 — Configurar espacios

En la pestaña `ESPACIOS`:

1. Cargar una fotografía real del estacionamiento.
2. Hacer clic en las cuatro esquinas de cada espacio.
3. El sistema asignará A1, A2, A3...
4. Guardar configuración.

Esta configuración se hace una sola vez siempre que la cámara mantenga
aproximadamente la misma vista.

### Paso 2 — Analizar fotografías

En `ANALIZAR FOTOS` se pueden seleccionar varias fotografías o una carpeta.

El sistema utilizará YOLO para detectar:
- automóvil
- motocicleta
- autobús
- camión

Luego comprueba si el centro de un vehículo cae dentro de alguno de los
espacios configurados.

### Paso 3 — Panel del vigilante

El dashboard muestra:
- espacios disponibles
- espacios ocupados
- porcentaje de ocupación
- vehículos detectados
- lista de espacios disponibles
- recomendación de espacio para el conductor

## Importante sobre el color

La detección de color incluida es una primera aproximación basada en HSV.
Debe validarse con las fotografías reales de la universidad porque iluminación,
sombras, reflejos y color de la carrocería pueden afectar el resultado.

## Importante sobre las fotografías

Para obtener resultados comparables, conviene tomar las fotografías desde
un punto de vista fijo o lo más estable posible.

El proyecto está pensado para evolucionar después a video en tiempo real,
seguimiento de vehículos y línea virtual de entrada/salida, tal como se
plantea en la metodología del proyecto.

## Estructura

```text
Sistema_Aforo_Vigilante/
├── app.py
├── requirements.txt
├── README.md
├── data/
│   ├── parking_config.json
│   └── photos/
├── models/
└── results/
```
