# MODEL_NOTES — SPE-232499-MS
## OCTG Torque vs Tension: A Growing Concern for Well Integrity
### Ott, Del Castillo, Broussard — Fermata Connections, 2026

---

## 1. Contexto y Fenómeno Físico

El **screw-jack effect** ocurre en conexiones shouldered (BTC): el torque aplicado al hacer make-up y durante operación gira el pin axialmente a través del paso de rosca, generando un desplazamiento axial LOT. Ese desplazamiento, resistido por la cara del pin y el shoulder del box, tensiona el **Box Critical Cross Section (BCCS)** con una precarga axial F_TQ. Esa precarga se suma a la tensión operacional (hook load) y reduce la capacidad tensil disponible.

Las conexiones wedge (BSP6.05, BSL5.90) **no exhiben este efecto**: resisten el torque por fricción distribuida en los flancos, sin desplazamiento axial neto significativo.

---

## 2. Variables de Entrada

| Símbolo | Descripción | Unidades | Fuente |
|---------|-------------|----------|--------|
| `Tq` | Torque operacional aplicado | ft·lbf | Operación / Tabla 1 |
| `ΔMU` | Delta turns durante make-up (después del shoulder point) | rev | Medición experimental |
| `ΔOT` | Delta turns durante torque operacional | rev | Medición experimental |
| `LFL` | Thread lead (paso de rosca BTC) | in/rev | API 5B (ver §6) |
| `COD` | Coupling outer diameter | in | Especificación conexión |
| `BCR` | Box critical root diameter (último hilo engranado pin→box) | in | Especificación conexión (TODO/INPUT_REQUERIDO) |
| `STpin` | Outside diameter de la cara del pin (pin-face contact OD) | in | Especificación conexión (TODO/INPUT_REQUERIDO) |
| `ID` | Inside diameter en la zona del pin face | in | Especificación casing |
| `LB` | Longitud del coupling | in | Especificación conexión (TODO/INPUT_REQUERIDO) |
| `LFArea` | Helical load-flank area (área de contacto activo de flancos de carga) | in² | Geometría rosca + engagement (TODO/INPUT_REQUERIDO) |
| `E` | Young's modulus del acero | psi | Material (ver §3) |
| `fSMYS` | Specified Minimum Yield Strength (SMYS) | psi | Material (ver §3) |
| `P` | Carga tensil total (hook load + precarga) | lbf | Operación |
| `JBTC` | Polar moment of inertia del BCCS | in⁴ | Derivado de COD, BCR |
| `A_BCCS` | Área transversal del Box Critical Cross Section | in² | Eq. 2 |
| `FApin` | Área de contacto de la cara del pin | in² | Eq. 3 |
| `F_hook` | Hook load (peso de la sarta + fuerzas axiales operacionales) | lbf | Diseño de pozo |
| `DF` | Design factor (factor de diseño) | adimensional | 1.4 (citado para BTC6.30 en Fig. 12) |

---

## 3. Constantes y Propiedades de Material

| Símbolo | Descripción | Valor | Fuente |
|---------|-------------|-------|--------|
| `E` | Young's modulus del acero P110 | 30 × 10⁶ psi | Beer (2015); estándar acero |
| `fSMYS` (P110) | Specified Min. Yield Strength, grado P110 | 110,000 psi | API 5CT (2018) |
| `Ym` | Material minimum yield strength (= fSMYS para P110) | 110,000 psi | API 5CT (2018) |
| `ν` | Poisson's ratio (acero) | 0.30 | Estándar (no usado explícitamente en el modelo) |

**Tubería de referencia:** 5.5-in 20# P110 (producción, Permian Basin)
- OD = 5.500 in
- Pared t = 0.361 in → ID = 4.778 in
- A_pipe = π/4 × (5.5² − 4.778²) = **5.828 in²**
- T_yield_pipe = A_pipe × fSMYS = 5.828 × 110,000 = **641 kips** ✓ (coincide con Tabla 1)

---

## 4. Ecuaciones Gobernantes

### Eq. 1 — Desplazamiento Axial por Torque

$$L_{OT} = (\Delta_{MU} + \Delta_{OT}) \times L_{FL}$$

**Variables:** LOT [in], ΔMU [rev], ΔOT [rev], LFL [in/rev].

**Origen:** explícita en paper p.5. "The total turns past the shoulder point... multiplied by thread lead define the total axial movement LOT."

**Física:** cada revolución del pin más allá del shoulder point avanza axialmente un paso de rosca (LFL). La suma de delta turns de make-up y operacionales define el avance total.

---

### Eq. 2 — Área del Box Critical Cross Section (BCCS)

$$A_{BCCS} = \frac{\pi}{4}\,(COD^2 - BCR^2)$$

**Variables:** A_BCCS [in²], COD [in], BCR [in].

**Origen:** explícita en paper p.11. "BCCS area is calculated as... where COD is the coupling outer-diameter and BCR is box critical root diameter where the last engaged pin thread meets the box thread."

**Física:** área anular del coupling en su sección crítica más débil (mínima área de material disponible para resistir tensión).

---

### Eq. 3 — Área de Contacto de la Cara del Pin

$$FA_{pin} = \frac{\pi}{4}\,(ST_{pin}^2 - ID^2)$$

**Variables:** FApin [in²], STpin [in], ID [in].

**Origen:** explícita en paper p.11. "The engaged pin-face contact area (FApin) is defined as... where STpin is the outside diameter of the pin-face contact and ID is the inside diameter of the same region."

**Física:** área anular de contacto donde el pin apoya sobre el shoulder del box y transfiere carga axial.

---

### Eq. 4 — Fracción de Strain Relativa ✓ EXPLÍCITA

$$\varepsilon_R = \frac{A_{BCCS}}{A_{BCCS} + FA_{pin} + LF_{area}}$$

**Variables:** εR [adimensional], A_BCCS [in²], FApin [in²], LFarea [in²].

**Confirmada contra imágenes del PDF por el autor.**

**Física:** εR es la fracción del área total de interfaz (BCCS + cara de pin + flancos de carga) que corresponde al BCCS. Representa cómo se distribuye la deformación impuesta (LOT) entre las distintas superficies de contacto asumiendo strain uniforme.

**Propiedad garantizada:** Por construcción, 0 < εR < 1 siempre (A_BCCS positivo y positivos los demás términos en el denominador).

**Nota de implementación:** FA_pin viene de Eq. 3. LF_area debe ser un INPUT (ver §7, TODO). Agregar aserción `assert 0 < εR < 1`.

---

### Eq. 5 — Desplazamiento Elástico Efectivo del BCCS ✓ EXPLÍCITA

$$\delta = L_{OT} \cdot \varepsilon_R$$

**Variables:** δ [in], LOT [in], εR [adimensional].

**Confirmada contra imágenes del PDF por el autor.**

**Física:** El desplazamiento total LOT (avance helicoidal del pin) se reparte proporcionalmente entre las áreas en contacto. El BCCS absorbe la fracción εR de ese desplazamiento, siendo δ < LOT siempre que εR < 1.

**Propiedad garantizada:** δ < LOT siempre (consecuencia directa de 0 < εR < 1). Agregar aserción `assert delta < lot` en implementación.

**Sin circularidad:** Eq. 5 y Eq. 6 son independientes entre sí. δ se calcula directamente de LOT y εR; no requiere F_TQ previo.

---

### Eq. 6 — Carga Axial del Screw-Jack ✓ EXPLÍCITA

$$F_{TQ} = \delta \cdot E \cdot \frac{A_{BCCS}}{L_B}$$

**Variables:** F_TQ [lbf], δ [in] (de Eq. 5), E [psi], A_BCCS [in²], LB [in].

**Confirmada contra imágenes del PDF por el autor.**

**Física:** Ley de Hooke aplicada al BCCS como barra elástica de sección A_BCCS y longitud LB bajo la deformación efectiva δ:
$$F = \sigma \cdot A = E \cdot \varepsilon \cdot A = E \cdot \frac{\delta}{L_B} \cdot A_{BCCS}$$

**Referencia:** Beer, F.P. et al. (2015) *Mechanics of Materials*, 7th ed. (citado explícitamente en el paper junto a esta ecuación).

**Flag has_screwjack:** Para conexiones wedge (BSP6.05, BSL5.90), F_TQ se fuerza a 0 independientemente de Eq. 6. El mecanismo de distribución flank-locking no genera desplazamiento axial neto. El flag `has_screwjack = False` gobierna este comportamiento en la implementación.

---

### Eq. 7 — Resistencia Torsional bajo Tensión (API RP 7G) ✓ CORREGIDA

$$Q_T = 0.096167 \cdot \frac{J_{BTC}}{COD} \cdot \sqrt{Y_m^2 - \frac{P^2}{A_{BCCS}^2}}$$

**Variables:** QT [**ft·lbf**], JBTC [in⁴], COD [in], Ym [psi], P [lbf], A_BCCS [in²].

**Origen:** API RP 7G (2018); Lubinski (1962). Confirmada contra imágenes del PDF.

**Análisis del coeficiente 0.096167:**
La forma Von Mises en unidades puramente SI-consistentes (in·lbf) da:
$$Q_T^{in \cdot lbf} = \frac{2}{\sqrt{3}} \cdot \frac{J}{D} \cdot \sqrt{Y_m^2 - P^2/A^2}$$

Convirtiendo de in·lbf a **ft·lbf**: dividir por 12:
$$Q_T^{ft \cdot lbf} = \frac{2}{12\sqrt{3}} \cdot \frac{J}{D} \cdot \sqrt{Y_m^2 - P^2/A^2} = 0.09622 \cdot \frac{J}{D} \cdot \sqrt{Y_m^2 - P^2/A^2}$$

El valor 0.096167 del paper es el coeficiente API RP 7G estándar; la diferencia con 0.09622 refleja el redondeo de la norma. **No simplificar ni reescribir esta constante.** Q_T queda en **ft·lbf** con J en in⁴, D en in, Ym en psi.

**Física (Von Mises):** En la fibra exterior del BCCS:
- σ_axial = P / A_BCCS [psi]
- τ_torsional = Q_T × (1/0.096167) × D / (2J × 12) [psi] (torsional shear en la fibra exterior)
- Criterio: σ_axial² + 3 τ_torsional² = Ym²

**Momento polar del BCCS:**
$$J_{BTC} = \frac{\pi}{32}(COD^4 - BCR^4)$$

**Uso:** Eq. 7 da la capacidad torsional disponible a una tensión P dada. Se usa para verificar que el torque operacional no excede Q_T.

---

### Eq. 8 — Reducción de Capacidad Tensil por Torque (P_BTC) ✓ CORREGIDA

$$P_{BTC} = A_{BCCS} \cdot \left( f_{SMYS} - \sqrt{f_{SMYS}^2 - \left(\frac{T_q \cdot COD}{0.096167 \cdot J_{BTC}}\right)^2} \right)$$

**Variables:** P_BTC [lbf], A_BCCS [in²], fSMYS [psi], Tq [**ft·lbf**], COD [in], JBTC [in⁴].

**Origen:** rearreglo algebraico de Eq. 7, confirmado contra imágenes del PDF.
Nombre en el paper: **P_BTC** (no "F_tension_max" como se usó anteriormente — corregido).

**Física — qué es P_BTC:**
P_BTC NO es la capacidad tensil remanente. Es la **reducción** de capacidad tensil debida al torque, expresada como fuerza:

$$P_{BTC} = \underbrace{A_{BCCS} \cdot f_{SMYS}}_{\text{capacidad axial total}} - \underbrace{A_{BCCS} \cdot \sqrt{f_{SMYS}^2 - \left(\frac{T_q \cdot COD}{0.096167 \cdot J_{BTC}}\right)^2}}_{\text{capacidad axial remanente bajo torsión Tq}}$$

- A Tq = 0: P_BTC = 0 (sin penalización torsional)
- A Tq = Q_T puro (fluencia torsional sin tensión): P_BTC = A_BCCS × fSMYS (consumo total)
- P_BTC crece monótonamente con Tq

**Unidades del término interno:** El cociente Tq·COD/(0.096167·JBTC) tiene unidades de psi cuando Tq está en ft·lbf. Equivale a √3·τ donde τ es el esfuerzo cortante en la fibra exterior. Verificación: (Tq·COD/(0.096167·J))² = 3τ². **No convertir Tq a in·lbf en esta ecuación.**

**Capacidad tensil remanente** (cantidad derivada, NO ecuación del paper):
$$F_{axial,remaining} = A_{BCCS} \cdot f_{SMYS} - P_{BTC} = A_{BCCS} \cdot \sqrt{f_{SMYS}^2 - \left(\frac{T_q \cdot COD}{0.096167 \cdot J_{BTC}}\right)^2}$$

---

### Eq. 9 — Carga Total Consumida en el BCCS (P_total) ✓ CORREGIDA

$$P_{total} = F_{TQ} + P_{BTC}$$

**Variables:** P_total [lbf], F_TQ [lbf] (de Eq. 6), P_BTC [lbf] (de Eq. 8).

**Origen:** explícita en paper p.12. Confirmada contra imágenes del PDF.

**Física — qué es P_total:**
P_total es la suma de **dos mecanismos de consumo de capacidad tensil** en el BCCS:
1. **F_TQ** (Eq. 6): precarga axial directa generada por el screw-jack. Aplica tensión mecánica adicional al BCCS.
2. **P_BTC** (Eq. 8): capacidad tensil "consumida" por la interacción Von Mises torsión–tensión. No es una fuerza aplicada al BCCS; es la reducción del espacio tensil disponible por efecto del torque.

**IMPORTANTE — P_total ≠ "carga total aplicada":**
P_total acumula cargas de naturaleza diferente (preload mecánico + reducción de capacidad). No debe confundirse con la suma de hook load + F_TQ, que sería la carga axial neta aplicada.

---

## 5. Métricas del Modelo: Ecuaciones del Paper vs. Derivadas

**Esta tabla es la referencia de trazabilidad para la app y el código.**

| Cantidad | Expresión | Fuente | Tipo |
|----------|-----------|--------|------|
| L_OT | (ΔMU + ΔOT) × LFL | Eq. 1 — paper | **Ecuación paper** |
| A_BCCS | π/4 × (COD² − BCR²) | Eq. 2 — paper | **Ecuación paper** |
| FA_pin | π/4 × (STpin² − ID²) | Eq. 3 — paper | **Ecuación paper** |
| εR | A_BCCS / (A_BCCS + FA_pin + LFArea) | Eq. 4 — paper | **Ecuación paper** |
| δ | LOT × εR | Eq. 5 — paper | **Ecuación paper** |
| F_TQ | δ × E × A_BCCS / LB | Eq. 6 — paper | **Ecuación paper** |
| Q_T | 0.096167 × J_BTC/COD × √(Ym² − P²/A²) | Eq. 7 — paper | **Ecuación paper** |
| P_BTC | A_BCCS × (fSMYS − √(fSMYS² − (Tq·COD/(0.096167·J))²)) | Eq. 8 — paper | **Ecuación paper** |
| P_total | F_TQ + P_BTC | Eq. 9 — paper | **Ecuación paper** |
| F_axial_remaining | A_BCCS × fSMYS − P_BTC | Rearreglo de Eq. 8 | Métrica derivada |
| available_tension_margin | (A_BCCS × fSMYS − P_total) / DF | Crit. de diseño | **Métrica derivada** |
| utilization | F_hook / available_tension_margin | Crit. de diseño | **Métrica derivada** |

---

## 6. Interpretación del Eje Y de Fig. 12–13 ⚠️ HIPÓTESIS DERIVADA

> El paper **no da una ecuación explícita** para el eje Y. Esta sección es la reconstrucción
> más consistente con P_total = Eq. 9 y el título "Applied Tension (kips)".
> Debe verificarse contra los datos numéricos de Fig. 12–13 cuando estén disponibles.

### Eje Y = "Applied Tension" = límite de tensión aplicable en función del torque

El gráfico muestra **dos curvas**, no una. Cada curva es un **límite de tensión** en función
del torque, impuesto por un componente diferente de la sarta:

---

#### CURVA BCCS (coupling)

$$\text{Applied\_Tension\_BCCS}(T_q) = A_{BCCS} \cdot f_{SMYS} - P_{total}(T_q)$$

Expandiendo con Eq. 9 → Eq. 6 → Eq. 8:

$$= A_{BCCS} \cdot f_{SMYS} \;-\; \underbrace{F_{TQ}(T_q)}_{\text{Eq. 6, screw-jack}} \;-\; \underbrace{P_{BTC}(T_q)}_{\text{Eq. 8, torsión}}$$

- F_TQ = 0 si `has_screwjack = False` (conexiones wedge).
- P_total recupera su sentido físico directo: es la fracción de capacidad del BCCS ya consumida
  por el torque (preload mecánico + interacción Von Mises). La curva es capacidad − consumo.
- Decreciente y cóncava (ambos términos crecen con Tq).

#### CURVA PIPE BODY (cuerpo de caño)

$$\text{Applied\_Tension\_Pipe}(T_q) = A_{pipe} \cdot f_{SMYS} - P_{BTC,pipe}(T_q)$$

donde P_BTC,pipe se obtiene de **Eq. 8 aplicada a la geometría del cuerpo**:

$$P_{BTC,pipe} = A_{pipe} \cdot \left( f_{SMYS} - \sqrt{f_{SMYS}^2 - \left(\frac{T_q \cdot OD_{pipe}}{0.096167 \cdot J_{pipe}}\right)^2} \right)$$

- Sin término F_TQ: el cuerpo de caño no tiene screw-jack.
- Geometría: OD=5.5 in, ID=4.778 in, J_pipe = π/32×(OD⁴−ID⁴).
- Casi idéntica entre las 4 conexiones (misma caño 5.5-in 20# P110).
- Muy lentamente decreciente (J_pipe/OD_pipe >> J_BTC/COD → menor τ para mismo Tq).

#### ENVELOPE = mínimo de ambas curvas

$$\text{Envelope}(T_q) = \min\bigl(\text{Applied\_Tension\_BCCS}(T_q),\; \text{Applied\_Tension\_Pipe}(T_q)\bigr)$$

---

### Design Factor DF = 1.4

⚠️ **HIPÓTESIS:** El paper cita DF=1.4 (Liu 2021) en el contexto de BTC6.30. No se confirma
explícitamente a qué curva(s) aplica ni si es uniforme para las 4 conexiones.

**Hipótesis de trabajo adoptada:** DF se aplica al envelope (min de ambas curvas) para el
criterio de aceptación: hook load ≤ Envelope(Tq) / DF. Las curvas del gráfico muestran los
límites brutos (sin DF); el DF es un factor de verificación en el check operacional.

---

### Criterios de Validación ("test de fuego" contra Fig. 12–13)

| Criterio | Condición esperada | Fig. de referencia |
|----------|-------------------|-------------------|
| **BTC6.30** | Curva BCCS **por encima** de curva Pipe en todo Tq → pipe-limited | Fig. 12a |
| **BTC6.05** | Curva BCCS **cruza por debajo** de curva Pipe cerca de Tq≈20 kft·lbf | Fig. 12b — **TEST CLAVE** |
| **BSP/BSL** | F_TQ=0 → curva BCCS casi plana, **por encima** de Pipe → envelope gobernado por Pipe | Fig. 13 |

El cruce de BTC6.05 es el diagnóstico principal: **si la curva BCCS no cruza por debajo de Pipe
en el rango operacional, el modelo no reproduce el comportamiento documentado en el paper.**

---

### ⚠️ SUPOSICIÓN OCULTA — ΔOT(Tq): escalado lineal

Eq. 1 define LOT = (ΔMU + ΔOT) × LFL donde **ΔOT es un dato experimental**,
no una función del torque. Para barrer la curva de 0 a Tq_op se necesita ΔOT(Tq).

**Suposición adoptada (no está en el paper):**

$$\Delta OT(T_q) = \Delta OT_{rated} \cdot \frac{T_q}{T_{q,op}}$$

Es decir, ΔOT escala linealmente con el torque instantáneo. Consecuencias:
- A Tq=0: ΔOT=0, LOT=ΔMU×LFL (precarga de makeup únicamente).
- A Tq=Tq_op: ΔOT=ΔOT_rated, LOT=(ΔMU+ΔOT_rated)×LFL.
- La curva F_TQ(Tq) resulta LINEAL en Tq.

**Cuándo esta suposición falla:** si la relación torque-turns de Fig. 11 es no-lineal
(hystéresis, cambio de rigidez en la zona shoulder-contact), el escalado real de ΔOT
puede ser cuadrático o con knee-point. Implementar como función reemplazable
`delta_ot_fn(tq) -> float` cuando haya datos de Fig. 11.

**Impacto sobre los tests:** `test_bccs_curve_monotonically_decreasing` es válido
ÚNICAMENTE bajo esta suposición lineal. Si ΔOT(Tq) es no-monótona, la curva
BCCS puede no ser monótona.

---

### Verificación Numérica con Parámetros Placeholder

> ⚠️ **CIRCULAR — NO ES VALIDACIÓN DEL PAPER.**
> Los parámetros fueron elegidos **para que el cruce exista**. El resultado prueba
> que el modelo *puede* generar el cruce topológico, NO que el cruce ocurra
> a ~20 kft·lbf como muestra Fig. 12b. La validación cuantitativa queda
> **PENDIENTE** hasta obtener:
>   - BCR, STpin, LB (CDS de Fermata Connections)
>   - ΔMU, ΔOT_rated reales (datos de Fig. 11, torque-turn tests)

Parámetros placeholder usados (`tests/test_fig12b_crossover.py`):

| Parámetro | Valor | Fuente | Estado |
|-----------|-------|--------|--------|
| BCR (BTC6.05, 6.30) | 5.385 in | Estimado de "44% area advantage" | ⚠️ PLACEHOLDER |
| STpin | 5.5 in | = OD caño (cota superior) | ⚠️ PLACEHOLDER |
| LB | 13.0 in | Estimado API 5CT Gr. B | ⚠️ PLACEHOLDER |
| LFL | 0.200 in/rev | API 5B 5 TPI — pendiente confirmar | ⚠️ PLACEHOLDER |
| LFArea | 60.0 in² | Estimado geometría API 5B | ⚠️ PLACEHOLDER |
| ΔMU | 0.03 rev | **Elegido para que BCCS(0) > Pipe(0)** | ⚠️ PLACEHOLDER |
| ΔOT_rated | 0.15 rev | **Elegido para que BCCS(Tq_op) < Pipe(Tq_op)** | ⚠️ PLACEHOLDER |

Resultados numéricos con estos placeholders (sólo topológicos — NO cuantitativos):

| Conexión | BCCS @ Tq=0 | Pipe @ Tq=0 | BCCS @ Tq_op | Pipe @ Tq_op | Cruce |
|----------|------------|------------|-------------|-------------|-------|
| BTC6.05 | ~650 kips | ~641 kips | ~572 kips | ~584 kips | **Sí (placeholder)** |
| BTC6.30 | ~917 kips | ~641 kips | ~814 kips | ~584 kips | No (pipe governs) |

→ El cruce de BTC6.05 **existe topológicamente** con estos parámetros.
→ La ubicación del cruce (~20 kft·lbf en Fig. 12b) NO está validada.

---

### Síntomas de Calibración Pendiente (dos indicadores simultáneos)

Con los placeholders actuales, el modelo produce dos desviaciones observables respecto a Fig. 12:

**Síntoma 1 — Cruce a 8.9 vs ~20 kft·lbf (Fig. 12b):**
El cruce BCCS/Pipe de BTC6.05 ocurre demasiado temprano. Indica que F_TQ crece
demasiado rápido respecto a P_BTC en el barrido de torque.

**Síntoma 2 — BTC6.30 BCCS plana 230 kips sobre Pipe (Fig. 12a):**
Con placeholder, BCCS_630 ≈ 815 kips vs Pipe ≈ 584 kips (diff = 231 kips constante).
Fig. 12a muestra la curva roja **convergiendo hacia** la negra a torque alto — el screw-jack
progresa y la brecha se cierra. Una curva plana a 230 kips sobre Pipe indica que F_TQ es
subdimensionado o que A_BCCS_630 está sobreestimado (BCR demasiado bajo).

**CRITERIO DE VALIDACIÓN CRUZADA (para cuando haya datos reales):**
Ambos síntomas deben corregirse **simultáneamente** con el mismo conjunto de parámetros.
- Si solo se arregla el cruce de BTC6.05 (ajustando ΔOT), puede persistir la curva plana de BTC6.30.
- Si solo se arregla la convergencia de BTC6.30 (ajustando F_TQ), el cruce puede correrse
  en la dirección equivocada.
- **Si al usar datos reales (BCR, LB, ΔMU, ΔOT de Fig. 11) un síntoma se corrige pero
  el otro no → revisar el ensamble Eq. 6/8/9 y la estimación de BCR.**

---

### Implementación: nombres en código

| Cantidad | Nombre en código | Tipo |
|----------|-----------------|------|
| A_BCCS·fSMYS − F_TQ − P_BTC | `applied_tension_bccs` | Ecuación paper (reconstruida) |
| A_pipe·fSMYS − P_BTC_pipe | `applied_tension_pipe` | Ecuación paper (reconstruida) |
| min(BCCS, Pipe) | `envelope` | Derived |
| F_TQ + P_BTC | `p_total` | **Eq. 9** |
| F_hook ≤ envelope / DF | check operacional | Criterio de diseño |

---

## 7. Cadena de Cálculo (Resumen — corregida)

```
INPUT: Tq [ft·lbf], F_hook [kips], ΔMU [rev], ΔOT [rev], geometría conexión

--- Geometría ---
A_BCCS = π/4 × (COD² − BCR²)              [Eq. 2, in²]
FA_pin = π/4 × (STpin² − ID²)             [Eq. 3, in²]
J_BTC  = π/32 × (COD⁴ − BCR⁴)            [in⁴]

--- Screw-jack (sólo si has_screwjack=True) ---
LOT = (ΔMU + ΔOT) × LFL                   [Eq. 1, in]
εR  = A_BCCS / (A_BCCS + FA_pin + LFArea)  [Eq. 4, adim]
δ   = LOT × εR                             [Eq. 5, in]  → δ < LOT siempre
F_TQ = δ × E × A_BCCS / LB                [Eq. 6, lbf]

Si has_screwjack=False: F_TQ = 0

--- Interacción torsión–tensión ---
P_BTC   = A_BCCS × (fSMYS − √(fSMYS² − (Tq·COD/(0.096167·J_BTC))²))
                                            [Eq. 8, lbf; Tq en ft·lbf]
P_total = F_TQ + P_BTC                    [Eq. 9, lbf]

--- Métrica de diseño (DERIVADA, no Eq. 9) ---
available_tension_margin = (A_BCCS·fSMYS − P_total) / DF   [lbf]

--- Check operacional ---
CHECK: F_hook [lbf] ≤ available_tension_margin  → operación segura
```

---

## 6. Tabla de Conexiones (Tabla 1 del Paper)

| Parámetro | BTC6.30 | BTC6.05 | BSP6.05 | BSL5.90 |
|-----------|---------|---------|---------|---------|
| COD [in] | 6.30 | 6.05 | 6.05 | 5.90 |
| Operating Torque [ft·lbf] | 30,600 | 30,600 | 39,800 | 38,750 |
| Tension Capacity [kips] | 641 | 641 | 641 | 641 |
| Connection Clearance [in] | 0.225 | 0.350 | 0.350 | 0.425 |
| has_screwjack | True | True | **False** | **False** |
| Thread type | BTC / buttress | BTC / buttress | Wedge (BSP) | Wedge (BSL) |

**Nota:** Las conexiones BSP6.05 y BSL5.90 son wedge (Bushmaster® SP y SL). No exhiben screw-jack: F_TQ = 0 para estas conexiones. Sus envelopes son determinados únicamente por Eq. 8 (reducción torsional de Von Mises), produciendo curvas casi planas (Fig. 13 del paper).

---

## 7. Parámetros Faltantes (TODO/INPUT_REQUERIDO)

Los siguientes parámetros geométricos **no están dados en el paper** y deben obtenerse de:
- API 5B (2023): thread geometry para BTC
- Connection Data Sheet (CDS) del fabricante: Fermata Connections

| Parámetro | Descripción | Dónde obtener |
|-----------|-------------|---------------|
| `BCR` [in] | Box critical root diameter para cada conexión | CDS o API 5B §7.2 |
| `STpin` [in] | Pin face contact OD | CDS del fabricante |
| `LB` [in] | Coupling length | API 5CT Tabla E.5 / CDS |
| `LFL` [in/rev] | Thread lead (paso de rosca BTC para 5.5") | API 5B §5.2 (nominalmente 5 TPI → LFL = 0.200 in/rev) |
| `LFArea` [in²] | Helical load-flank area activa | Requiere geometría completa de rosca + engagement length |
| `ΔMU`, `ΔOT` [rev] | Delta turns experimental para cada conexión | Datos de torque-turn tests (Fig. 11 del paper) |

**Estimación de LFL para BTC:** Las roscas BTC (API 5B) para 5.5-in tienen paso de **5 TPI** (threads per inch), lo que da LFL = 1/5 = **0.200 in/rev**. ⚠️ Confirmar con API 5B Tabla B.4.

---

## 8. Hipótesis del Modelo y Rango de Validez

1. **Comportamiento elástico:** Las ecuaciones de Eq. 4–6 son válidas únicamente mientras el BCCS permanece en rango elástico (σ < fSMYS). El paper nota que BTC6.05 excede este límite a torque máximo operacional (plasticidad total a través del muro).

2. **Strain uniforme (Eq. 4):** Se asume distribución de esfuerzo uniforme en A_BCCS. Esto subestima concentraciones de esfuerzo reales validadas por FEA (Fig. 14).

3. **Rigidez relativa:** Se asume que el pin body y el string son mucho más rígidos que el BCCS (todo el desplazamiento LOT se absorbe como deformación del BCCS). Sin evidencia explícita en el paper.

4. **Criterio Von Mises (Eq. 7, 8):** Se usa para la interacción torsión-tensión. El paper también menciona el criterio de Tresca (Lubinski, 1962) pero el rearreglo dado corresponde a Von Mises.

5. **Carga estática:** El modelo es estático. El paper menciona que cargas cíclicas y stick-slip amplifican el riesgo, pero no están incluidas en las ecuaciones analíticas.

6. **Sistema imperial:** Todas las ecuaciones usan unidades imperiales. Conversiones requeridas:
   - ft·lbf → in·lbf: multiplicar × 12
   - kips → lbf: multiplicar × 1,000

7. **Rango de validez:** 5.5-in 20# P110 casing en los 4 tipos de conexión de la Tabla 1. No extrapolado explícitamente a otros tamaños, aunque el modelo es en principio aplicable si se tienen los parámetros geométricos.

8. **Wedge connections:** F_TQ = 0 (sin screw-jack). El único mecanismo de interacción es la reducción Von Mises (Eq. 8).

---

## 9. Figuras de Referencia

- **Fig. 5:** Diagrama conceptual del mecanismo screw-jack.
- **Fig. 6:** Paths de carga internos en BTC6.30 y BTC6.05.
- **Fig. 11:** Torque-turn plots experimentales (make-up y operacional) — fuente de ΔMU y ΔOT.
- **Fig. 12a:** Envelope torque-tensión BTC6.30 (1.4 DF; transición a "coupling torque-limited" cerca de 25,000 ft·lbf).
- **Fig. 12b:** Envelope BTC6.05 — caída marcada sobre ~20,000 ft·lbf, BCCS se plastifica al torque máximo.
- **Fig. 13:** Envelopes BSP6.05 y BSL5.90 — curvas casi planas (no screw-jack).
- **Fig. 14:** FEA — esfuerzos axiales en BTC6.30 y BTC6.05 a torque operacional (30,600 ft·lbf) + 641 kips.
- **Fig. 15:** FEA — esfuerzos axiales en BSP6.05 y BSL5.90.

---

## 10. Referencias del Paper

- API RP 7G (2018) — fórmula torsional Eq. 7
- Beer et al. (2015) *Mechanics of Materials*, 7th ed. — Eq. 5, 6 (δ = PL/AE)
- Bickford (2007) *Introduction to Bolted Joints* — concepto de preload roscado (citado en Fig. 5)
- Lubinski (1962) — criterio Von Mises para torsión + tensión combinados (Eq. 7)
- Roark (Young & Budynas, 2002) — fórmulas de esfuerzo en secciones anulares
- API 5B (2023) — especificaciones de rosca BTC
- API 5CT (2018) — propiedades de material P110
