# DPI — Registro de cambios

**Dendro Pixel Interface 2.3.0 · Suite MoiCedrus**
Desde la versión 2.0.0 hasta la 2.3.0

Cada cambio dice qué se hizo y, cuando corresponde, con qué evidencia se
decidió. Los que corrigen un error real de DPI van marcados con **[error]**;
los que acercan el programa a COFECHA, con **[fidelidad]**; los que agregan
capacidad, con **[nuevo]**.

---

# 1. Motor COFECHA — fidelidad

## 1.1 Las dos maestras **[fidelidad]**

COFECHA mantiene dos versiones de la serie maestra: la que **guarda** con su
opción 6 y muestra en las Partes 3 y 4 está construida **sin** el modelo
autorregresivo; la que usa para **correlacionar** sí lo lleva. Su
documentación no lo distingue.

Establecido con tres líneas de evidencia: dos corridas que solo difieren en la
opción 3 dan archivos de maestra idénticos byte a byte; sobre 274 series de
tres colecciones, correlacionar contra una maestra con AR baja el error de
0,041 a 0,018 y elimina un sesgo de −0,035; y una corrida con una serie
duplicada, donde la maestra *es* la serie, da autocorrelación +0,284 en el
archivo guardado y −0,030 en la serie filtrada.

**Es el cambio de mayor efecto de todo el trabajo.**

## 1.2 El orden de la cadena: AR antes del logaritmo **[fidelidad]**

El manual de la Dendrochronology Program Library describe spline → índice →
AR → logaritmo. DPI aplicaba el logaritmo antes del AR.

La prueba que lo zanja es el orden del modelo, que es un entero: sobre 36
series, el AR aplicado al índice acierta 25 órdenes y aplicado al logaritmo,
19.

## 1.3 Criterio BIC para el orden del AR **[fidelidad]**

Medido contra los órdenes que informa COFECHA:

| criterio | aciertos |
|---|---|
| **BIC** | **33/36 (92 %)** |
| PACF | 32/36 |
| AICc | 25/36 |
| AIC | 24/36 |
| FPE | 24/36 |

Se probó también el primer mínimo local del AIC, que usa dplR en `chron.ars`:
mejora el AIC de 67 % a 81 %, pero no alcanza al BIC.

## 1.4 Orden mínimo del AR en 1 **[fidelidad]**

COFECHA nunca informa orden 0 cuando el AR está activado. Afecta también al
panel de co-datación, donde es la práctica estándar para blanquear.

## 1.5 El AR devuelve la media de la serie, no 1,0 **[error]**

`ar.func` de dplR hace `y <- ar1$resid + ar1$x.mean`. DPI sumaba 1,0 fijo.
Para una correlación da igual —es un desplazamiento— pero **no** para el
logaritmo que viene después, que no es lineal.

Contra las 136 correlaciones por segmento de la Parte 5: el sesgo baja de
−0,0206 a −0,0176 y la desviación media de 0,0750 a 0,0734.

## 1.6 «Corr with Master» es la media de los segmentos **[fidelidad]**

DPI informaba una correlación global sobre todo el solape; COFECHA promedia
las correlaciones por segmento.

| forma | error medio | sesgo |
|---|---|---|
| r global | 0,0519 | +0,0136 |
| **media de segmentos** | **0,0386** | **+0,0009** |

Lo que confirma la hipótesis no es solo el error menor: es que **el sesgo
desaparece**, señal de que se está calculando la misma cantidad.

## 1.7 Spline en escala lineal con piso **[fidelidad]**

El spline de Cook se ajusta a la serie cruda. DPI lo ajustaba al logaritmo
para garantizar positividad, y eso ganaba **mientras el AR estaba mal
puesto**; corregido el AR, la escala lineal pasa a ser mejor en todo.

El piso del 10 % de la media evita que el índice se dispare cuando el spline
sobrepasa hacia abajo en los extremos. Barrido contra la corrida real:

| piso | maestra | error | DBC200B |
|---|---|---|---|
| 0,05 | 0,9549 | 0,0518 | 0,360 |
| **0,10** | **0,9709** | **0,0359** | **0,425** |
| 0,15 | 0,9690 | 0,0381 | 0,421 |

## 1.8 La rigidez del spline no llegaba al cálculo **[error]**

`estandarizar_serie` recibía el parámetro pero `_detrend_serie_indice` usaba
siempre la constante del módulo. **La opción 1 de la corrida no hacía nada.**

## 1.9 Media aritmética y leave-one-out cerrado **[fidelidad]**

El manual de COFECHA dice que promedia aritméticamente. Con media aritmética
el leave-one-out es exacto en tiempo constante; con biweight no lo es —el
umbral duro cambia qué observaciones pesan cero, con errores de hasta 1,09—,
así que la biweight quedó como opción con recálculo real.

## 1.10 La rejilla de segmentos **[fidelidad]**

COFECHA no ancla los segmentos al último año: los empieza en años divisibles
por el avance. Verificado en dos archivos independientes.

## 1.11 El solape mínimo es *avance + 1* **[fidelidad]**

Cruzando cada celda de la Parte 5 con su solape en dos archivos, la separación
es exacta y sin excepciones: **todo solape ≥ 26 aparece con valor y todo ≤ 25
queda en blanco**, con segmentos de 50 y avance 25. DPI usaba 0,6 del largo, o
sea 30, y descartaba los segmentos de 26 a 29 años —justamente los extremos de
las series cortas.

## 1.12 La codificación de la Parte 4 **[fidelidad]**

Extrayendo los valores de la Parte 3 y las barras de la Parte 4 del mismo
archivo: **cada letra vale 0,25 desviaciones típicas**, no 0,2. La disposición
también era otra: ocho columnas de 50 años, 400 años por página.

## 1.13 Ancho de página, formato numérico y recuentos **[fidelidad]**

El ancho es 132, no 131. Los valores menores que uno se escriben sin cero
inicial (`.751`). Y los anillos **comprobados** no son los totales: un anillo
solo puede comprobarse si otra serie cubre ese año.

## 1.14 Parte 2: el bloque derecho pegado al gráfico **[error]**

COFECHA usa un eje fijo que llena la línea; la escala de DPI se adapta al
período y el bloque quedaba en una columna fija, dejando un hueco enorme.

## 1.15 Parte 6: todas las series, numeración correlativa **[error]**

Verificado en un archivo real: COFECHA imprime las 40 series numeradas de 1 a
40 sin saltos. DPI se saltaba las que no tenían problemas y la numeración
quedaba con huecos.

## 1.16 Nota sobre las columnas filtradas **[nuevo]**

Tres líneas sobre el encabezado de la Parte 7 declaran cómo se calculan y que
COFECHA informa cerca del doble en esas dos columnas. Es la única discrepancia
que quedó sin explicar; no entra en ninguna correlación ni en el marcado de
segmentos.

## 1.17 Estado final

| conjunto | series | DPI | COFECHA |
|---|---|---|---|
| Ciprés QLH | 69 | 0,5795 | 0,5793 |
| Araucaria ACI10 | 169 | 0,5722 | 0,5674 |
| Lenga cos8 | 36 | 0,4565 | 0,4466 |

Error medio por serie: **0,018**, desde 0,065 al comienzo. Baja a 0,014 en
series de más de 250 años. Con umbrales de decisión de 0,30 y 0,40 **no hay
ninguna discrepancia** con COFECHA en las 238 series de las dos colecciones
grandes.

---

# 2. Rendimiento

## 2.1 Motor vectorizado **[nuevo]**

Con 96 series el programa se colgaba; extrapolando, 1600 habrían tardado unas
ocho horas.

El diagnóstico fue por perfilado, no por intuición: **el 83 % del tiempo se
iba en una sola función** que convertía cada serie con `to_numeric().dropna()`
dentro de un doble bucle.

Tres ideas: una matriz alineada de años por series; leave-one-out en forma
cerrada, restando el aporte de la serie en vez de recalcular; y sumas
acumuladas para que la correlación de cualquier ventana salga en tiempo
constante.

| series | antes | ahora |
|---|---|---|
| 48 | 41 s | 0,23 s |
| 96 | ~2,5 min | 0,46 s |
| 1600 | ~8 h | 8,8 s |

**Verificado que no cambian los números:** con el mismo maestro, el motor
nuevo reproduce el viejo con error máximo de 1×10⁻¹⁴.

## 2.2 Hilo de fondo y caché **[nuevo]**

El análisis corre fuera del hilo de la interfaz, con barra de progreso y botón
de cancelar. El resultado se cachea por firma: cambiar qué partes imprimir solo
reformatea; cambiar un parámetro real dispara el recálculo automáticamente.

---

# 3. Localizador de quiebres

Es la parte original de DPI: responde *en qué año* está el error, con
resolución de un año, donde COFECHA trabaja con segmentos de 50.

## 3.1 El módulo **[nuevo]**

`modulo_quiebres.py`. Formula el año del quiebre como el parámetro a estimar:
para cada año candidato y cada desfase, evalúa la partición completa y elige
la que maximiza la correlación conjunta. Con sumas acumuladas cada partición
se evalúa en tiempo constante, así que probar miles de hipótesis toma
milisegundos.

## 3.2 La partición tiene que ser global **[error]**

Evaluar solo una ventana alrededor del quiebre daba error de 40 años, contra
2 de la versión global: con pocos datos aparecen óptimos espurios en cualquier
parte de la serie.

## 3.3 Corrección de un sesgo de +1 año **[error]**

El óptimo cae en el primer año del tramo bien fechado y el anillo faltante
está un año antes.

## 3.4 La zona compatible **[nuevo]**

Un año entra si su correlación no se distingue de la del óptimo, comparando en
escala z de Fisher a menos de un error estándar. No es un umbral inventado: es
la precisión con que se puede medir una correlación con esos datos.

## 3.5 Orden por estrechez del anillo **[nuevo]**

Dentro de la zona, los años se ordenan por lo estrecho que es cada uno en la
cronología: un anillo ausente aparece donde el árbol casi no formó leño.

## 3.6 Tramo mínimo adaptativo **[error]**

Un valor fijo de 15 años dejaba sin material a las series cortas, y era la
causa de que el roble rindiera mal. Pero las series largas prefieren tramos
grandes, que estabilizan la correlación.

La regla es una décima parte de la serie, entre 10 y 30 años, y iguala o supera
al mejor valor fijo en las cuatro especies. El roble pasó de 91 % a **100 %**
de cobertura de la zona.

## 3.7 El nulo de colección **[nuevo]**

La búsqueda prueba miles de configuraciones, así que siempre encuentra algo.
Decidir si el hallazgo es real exige un contraste, y costó tres intentos.

**Rotar la cronología** eliminaba los falsos positivos pero rechazaba los casos
verdaderos: rotar destruye la señal, la base cae a cero y cualquier partición
gana mucho.

**Series sustitutas sintéticas** con la misma correlación y el mismo espectro
detectaban todo, pero dejaban pasar hasta un 39 % de falsos positivos: ninguna
sustituta reproduce la complejidad de una serie real, y la búsqueda explota
justamente eso.

**La salida fue no inventar el nulo sino medirlo:** correr la misma búsqueda
sobre las otras series de la colección, que están fechadas, y quedarse con el
percentil 95 de sus ganancias.

| especie | falsos positivos | detección |
|---|---|---|
| Roble | 6 % | 100 % |
| Ciprés | 6 % | 100 % |
| Araucaria | 0 % | 100 % |
| Lenga | 11 % | 78 % |

## 3.8 Tres fuentes de series para el nulo **[nuevo]**

Se acumulan: las cargadas en el panel, **las que se usaron para construir la
cronología en su pestaña** —el caso más común y el que antes se perdía— y las
cargadas expresamente con el botón «📊 Referencia», para cuando solo se tiene
una cronología ya hecha y una serie por cofechar. Estas últimas no entran a la
lista ni se cofechan.

## 3.9 El informe en prosa **[nuevo]**

Dice qué tramo correlaciona bien y con qué r, dónde baja, cuántos anillos
sobran o faltan y entre qué años, y qué años conviene revisar primero.

**La acción va con todas las letras** —"hay que INSERTAR 1 anillo"— porque
COFECHA escribe "+1" y esa deducción se equivoca seguido.

Los tramos se califican al 90, 95 o 99 %, no solo al 99 % de COFECHA: aquel
sirve para sospechar de series ya fechadas, este orienta una revisión que
todavía no ocurrió.

## 3.10 El perfil del quiebre **[nuevo]**

Cada punto es un experimento: se supone que el error está en ese año, se aplica
la corrección y se mide cómo queda la serie **completa**. Un pico angosto
significa que el año está determinado; una meseta, que elegir uno sería falsa
precisión.

Al lado va un panel explicativo con divisor movible.

## 3.11 Filtro de sugerencias **[nuevo]**

Las candidatas que bajan la correlación ya no se muestran.

## 3.12 Validación completa

Sobre las cuatro especies, con cinco escenarios de error:

| escenario | zona | top 8 | signo |
|---|---|---|---|
| 1 anillo ausente | 100 % | 42–94 % | 83–100 % |
| 1 anillo falso | 92–100 % | 42–100 % | 83–100 % |
| 2–3 ausentes | 100 % | 50–79 % | 67–100 % |
| 2–3 falsos | 92–100 % | 25–79 % | 75–100 % |
| **ausente + falso** | **42–45 %** | **27–33 %** | — |

**El caso difícil está identificado y es del método, no de la
implementación.** Cuando un ausente y un falso se cancelan, el desplazamiento
neto es cero y ninguna partición revela el problema por correlación.

Pero el programa **se calla** en esos casos: se pronuncia solo el 14–45 % de
las veces, y cuando lo hace acierta el 80–100 %. Ahí la herramienta que
corresponde sigue siendo el skeleton sobre la madera.

---

# 4. Lectura de datos

## 4.1 La precisión del formato Tucson es POR SERIE **[error]**

El formato no declara su precisión: se deduce del marcador de fin de cada
serie, como hace dplR en `readloop.c`.

| terminador | precisión | divisor |
|---|---|---|
| `999` | 0,01 mm | 100 |
| `-9999` | 0,001 mm | 1000 |
| sin terminador | sin escalar | 1 |

**DPI dividía siempre por 1000.** Con un archivo en centésimas —habitual en
material antiguo y en buena parte de la ITRDB— dejaba todos los anchos **diez
veces más chicos**. No afecta el cofechado, porque es un factor constante,
pero arruina cualquier cifra en milímetros: crecimiento medio, incremento en
área basal, comparación entre sitios.

## 4.2 El 999 no siempre es fin de serie **[error]**

Solo lo es en archivos de centésimas. En milésimas es un ancho válido de
0,999 mm, y tomarlo como terminador **truncaba la serie ahí**.

---

# 5. Estandarización y cronología

## 5.1 Curvas de ajuste negativas **[error]**

Con series de caída fuerte, la exponencial negativa o la recta pueden cruzar
cero y el índice se dispara: sobre 69 series de ciprés con ajuste lineal, una
producía un índice de **13.509**.

Tres cambios:

**El umbral no es cero sino el 10 % de la media.** dplR solo comprueba ≤ 0, y
eso deja pasar el caso peor: una tendencia positiva pero diminuta hace el
mismo daño. En una serie el ajuste nunca cruzaba cero y aun así daba 43,5.

**Se descarta la curva entera**, no solo los años malos, como ARSTAN y dplR.
Parchar por año deja una serie cuyo índice significa una cosa en un tramo y
otra en el resto.

**Se avisa y se deja elegir.** Un diálogo muestra la serie cruda con las cinco
curvas superpuestas y una tabla comparativa; se puede aplicar un método a todo
el grupo o uno por serie, y el informe registra cuáles fueron y con qué método
se resolvieron.

El criterio automático es en dos etapas: se descarta todo método que cruce
cero y, entre los que sobreviven, se elige el de mayor correlación mediana con
la maestra de las series sanas. **No** se usa el índice máximo, porque un
máximo cercano a 1 se consigue de dos maneras opuestas —buen ajuste, o ajuste
que se come toda la variabilidad—.

## 5.2 Rbar entre árboles **[nuevo]**

Dos radios del mismo árbol comparten el individuo, no solo el sitio. Contarlos
como réplica independiente **infla el Rbar**, la EPS y la SSS.

DPI separa por árbol reutilizando el lector de códigos:

| | mismo árbol | entre árboles | efectivo |
|---|---|---|---|
| Ciprés QLH (69 series / 46 árboles) | 0,815 | 0,430 | 0,450 |
| Araucaria ACI10 (169 / 99) | 0,693 | 0,250 | 0,280 |
| Roble QUI2 (31 / 16) | 0,910 | 0,632 | 0,660 |
| Lenga cos8 (36 / 27) | 0,445 | 0,227 | 0,250 |

**El caso que lo justifica:** en una colección de araucaria los radios del
mismo árbol correlacionaban 0,597 y los árboles entre sí solo 0,087. El Rbar
simple daba 0,291, casi el triple, y el período utilizable se acortaba **72
años** al corregirlo.

El efectivo a veces **sube**, como en ciprés y lenga: no es una corrección
conservadora por sistema.

## 5.3 SSS **[nuevo]**

Qué fracción de la señal de tu propia cronología conserva cada año. A
diferencia de la EPS, que compara contra una población infinita, la SSS compara
contra la colección que realmente tienes, y es la pregunta correcta para
decidir desde qué año usar la cronología.

## 5.4 Rbar sobre series detrendadas **[error]**

Se calculaba sobre las crudas, y eso lo inflaba: las tendencias decadales hacen
que las series brutas covaríen a largo plazo aunque no compartan señal
climática.

## 5.5 Gleichläufigkeit **[error]**

La fórmula de dplR da crédito **completo** cuando ambas series están planas en
el mismo par de años. DPI le daba medio punto. Con mediciones a 0,01 mm los
valores repetidos no son raros.

## 5.6 Media biponderada alineada con dplR **[fidelidad]**

`tbrm` suma 1e-6 a la escala —lo que evita la división por cero sin tratar el
caso aparte— y su corte del peso es inclusivo. Es la agregación por omisión de
la pestaña de cronología.

## 5.7 El spline, verificado contra la fuente

El Fortran original de Ed Cook modificado por Holmes está en `src/capsf.f95`
de dplR. Traducido literalmente y comparado con el de DPI: **r = 1,000000,
diferencia máxima 0,00000**. No es una hipótesis descartada: es una
verificación.

---

# 6. Interfaz y flujo de trabajo

## 6.1 Ícono y versión centralizados **[error]**

`run_dpi.py` buscaba `dpi_icon.ico` pero el archivo es `dpi.ico`. En Windows
se veía igual porque PyInstaller lo incrusta en el ejecutable; en Linux fallaba
en silencio.

## 6.2 Casillas del modo COFECHA **[error]**

Se creaban pero quedaban fuera de todo layout: invisibles y congeladas.

## 6.3 El zoom del gráfico de medición **[error]**

Se reiniciaba en cada anillo medido. Ahora el encuadre se recalcula solo
cuando cambia el conjunto de series dibujadas.

## 6.4 Métodos de correlación unificados **[error]**

Medición y Skeleton usaban diferencias-log; Co-Datación usaba el método
COFECHA. El mismo par de series daba **0,7679 y 0,8104** según dónde se mirara,
sin que nada lo explicara. Hoy hay un solo módulo, `modulo_transformacion.py`,
y un selector idéntico en las tres pestañas.

## 6.5 Ordenamiento de códigos al unir **[nuevo]**

Un código como QLH107A son tres cosas: sitio, número de árbol y radio.
Ordenar alfabéticamente daba COS1, COS10, COS2. Cubre radios compuestos,
códigos sin radio, renombrados por duplicado y prefijos con símbolos. Sirve
también para ordenar un archivo ya unido.

## 6.6 Panel inferior con tres pestañas **[nuevo]**

Correlación móvil, Informe y Perfil del quiebre, cada una con su barra de zoom
independiente.

## 6.7 Detalles de la interfaz

- El botón de barras se movió junto a «Ver todo», donde se esperan los
  controles de ese gráfico **[error]**
- Selección de fila completa en la tabla de sugerencias, con color que se
  impone sobre el fondo de origen **[error]**
- Tipo y tamaño de letra del informe, con Garamond, persistentes entre
  sesiones **[nuevo]**
- Botón «🗑 Nuevo análisis» en la pestaña COFECHA **[nuevo]**
- Hover con el año y leyenda nombrada en el perfil **[error]**

## 6.8 Instalador de escritorio para Linux **[nuevo]**

`instalar_lanzador_linux.py` detecta la carpeta del proyecto y el intérprete,
extrae siete tamaños de ícono e instala el `.desktop`. En Wayland el compositor
no puede leer el ícono desde la ventana: necesita ese archivo y el
identificador `setDesktopFileName`, ahora declarado en los dos puntos de
entrada.

---

# 7. Documentación **[nuevo]**

Cinco documentos: la guía de defensa y los manuales de Medición, COFECHA,
Cronología y Skeleton, y Co-Datación.

---

# 8. Lo que se probó y se descartó

Vale la pena tenerlo escrito: si alguien propone una de estas ideas, ya está
medida.

| idea | resultado |
|---|---|
| Verificación por consistencia para ordenar candidatas | Peor: 62→58 % con señal fuerte |
| Ventana local en vez de partición global | Error de 40 años contra 2 |
| Detrending por diferencia en vez de cociente | Espejismo de una serie; sobre 14 cae de 0,96 a 0,82 |
| Nulo por rotación de la cronología | Rechaza los casos verdaderos |
| Nulo por sustitutas sintéticas | Hasta 39 % de falsos positivos |
| Quitar la constante del logaritmo | Mejora aislada, empeora de punta a punta |
| Descartar los primeros residuos del AR | Peor en las dos métricas que importan |
| Respaldo a la media al estilo dplR en el spline | Error 0,0495 contra 0,0359 |
| Maestra biponderada para la fidelidad | Error 0,0423 contra 0,0379 |
| Primer mínimo del AIC para el orden | 81 %, contra 92 % del BIC |
| Rigidez o forma del filtro distintas | Cresta plana; el spline de Cook es el mejor |
| Relleno de extremos del spline | Sin efecto medible |
| Métodos alternativos de estimación del AR | Burg y mínimos cuadrados dan lo mismo |

---

# 9. Lo que queda abierto

1. **Las columnas filtradas de la Parte 7.** COFECHA informa el doble de
   varianza y ninguna de siete transformaciones lo reproduce. Documentado en el
   informe; no afecta ningún cálculo.
2. **El 3 % de la estandarización.** La transformación de una serie individual
   correlaciona 0,970 con la de COFECHA. Todas las hipótesis estructurales
   fueron descartadas por medición, incluido el spline. Cerrarlo exigiría el
   Fortran de COFECHA, que no está distribuido.
3. **Errores que se cancelan.** Un ausente y un falso en la misma serie se
   detectan menos de la mitad de las veces. Es una limitación del método.

---

# 10. Decisiones tomadas a conciencia

- El `+0` del encabezado de la sección [A] no calca el original
- `_spline_cook`, `_fit_trend` y `_detrend_serie_indice` siguen en
  `modulo_codatacion.py`, aunque los use la pestaña COFECHA
- El respaldo de curva completa aplica a las tres pestañas, no solo a
  cronología: se activa en 1 de 168 series con la cadena de COFECHA

---

*Registro de cambios · DPI 2.3.0 · Suite MoiCedrus*
