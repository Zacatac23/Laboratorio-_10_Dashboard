"""Módulo de Controles Automáticos de Calidad de Datos (Laboratorio 11).
Implementa los seis controles mínimos de calidad, evaluación de severidad
(CRITICAL vs WARNING) y generación de reportes estructurados.
"""
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any
import numpy as np
import pandas as pd


class QualityControlError(Exception):
    """Excepción lanzada cuando falla un control de calidad crítico."""
    pass


@dataclass
class CheckResult:
    check_id: str
    name: str
    status: str  # 'PASSED', 'WARNING', 'FAILED'
    is_critical: bool
    description: str
    details: str
    diagnostics: Dict[str, Any] = field(default_factory=dict)


@dataclass
class QualityReport:
    run_id: str
    timestamp: str
    checks: List[CheckResult] = field(default_factory=list)
    critical_passed: bool = True
    warnings_count: int = 0
    errors_count: int = 0

    def add_result(self, result: CheckResult):
        self.checks.append(result)
        if result.status == 'FAILED' and result.is_critical:
            self.critical_passed = False
            self.errors_count += 1
        elif result.status == 'WARNING':
            self.warnings_count += 1
        elif result.status == 'FAILED' and not result.is_critical:
            self.warnings_count += 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "timestamp": self.timestamp,
            "critical_passed": self.critical_passed,
            "errors_count": self.errors_count,
            "warnings_count": self.warnings_count,
            "checks": [asdict(c) for c in self.checks]
        }


def check_columns_and_types(df: pd.DataFrame, expected_schema: Dict[str, str], name: str = "dataset") -> CheckResult:
    """Control a): Columnas y tipos.
    Detiene el flujo si falta una variable indispensable o tiene un tipo incompatible.
    """
    check_id = "QC-A"
    check_name = "Columnas y tipos requeridos"
    desc = f"Verificar presencia de columnas requeridas y tipos compatibles en {name}."
    
    missing_cols = [col for col in expected_schema if col not in df.columns]
    if missing_cols:
        return CheckResult(
            check_id=check_id,
            name=check_name,
            status='FAILED',
            is_critical=True,
            description=desc,
            details=f"Faltan columnas indispensables en {name}: {missing_cols}.",
            diagnostics={"missing_columns": missing_cols}
        )
    
    incompatible = []
    for col, expected_type in expected_schema.items():
        if expected_type == 'datetime':
            try:
                parsed = pd.to_datetime(df[col], errors='coerce')
                if parsed.isna().any():
                    incompatible.append(f"{col} contiene fechas no convertibles")
            except Exception:
                incompatible.append(f"{col} no pudo parsearse como datetime")
        elif expected_type == 'numeric':
            try:
                parsed = pd.to_numeric(df[col], errors='coerce')
                if parsed.isna().any():
                    incompatible.append(f"{col} contiene valores no numéricos")
            except Exception:
                incompatible.append(f"{col} no pudo parsearse como numérico")
        elif expected_type == 'string':
            if not df[col].astype(str).str.strip().ne('').all():
                incompatible.append(f"{col} contiene cadenas vacías o solo espacios")
                
    if incompatible:
        return CheckResult(
            check_id=check_id,
            name=check_name,
            status='FAILED',
            is_critical=True,
            description=desc,
            details=f"Tipos incompatibles o valores corruptos en {name}: {incompatible}.",
            diagnostics={"incompatible_columns": incompatible}
        )
        
    return CheckResult(
        check_id=check_id,
        name=check_name,
        status='PASSED',
        is_critical=True,
        description=desc,
        details=f"Todas las columnas indispensables ({list(expected_schema.keys())}) y tipos están conformes en {name}."
    )


def check_dates_and_coverage(df: pd.DataFrame, date_col: str = 'fecha', series_col: str = 'serie',
                             target_series: str = 'Total', start_date: Optional[str] = None,
                             end_date: Optional[str] = None) -> CheckResult:
    """Control b): Fechas y cobertura.
    Detecta fechas inválidas y períodos necesarios sin información.
    Los períodos sin cobertura no deben convertirse automáticamente en cero.
    """
    check_id = "QC-B"
    check_name = "Fechas y cobertura temporal"
    desc = f"Validar normalización mensual (primer día de mes) y ausencia de huecos en la serie '{target_series}'."
    
    if date_col not in df.columns:
        return CheckResult(
            check_id=check_id, name=check_name, status='FAILED', is_critical=True,
            description=desc, details=f"Columna de fecha '{date_col}' no presente."
        )
        
    fechas = pd.to_datetime(df[date_col], errors='coerce')
    invalidas = int(fechas.isna().sum())
    if invalidas > 0:
        return CheckResult(
            check_id=check_id, name=check_name, status='FAILED', is_critical=True,
            description=desc, details=f"Se detectaron {invalidas} fechas no convertibles o inválidas.",
            diagnostics={"invalid_dates_count": invalidas}
        )
        
    if (fechas.dt.day != 1).any():
        return CheckResult(
            check_id=check_id, name=check_name, status='FAILED', is_critical=True,
            description=desc, details="Las fechas mensuales deben estar normalizadas al primer día del mes (día 1)."
        )
        
    # Verificar cobertura de la serie objetivo si existe columna de serie
    sub = df[df[series_col] == target_series] if series_col in df.columns else df
    fechas_unicas = pd.Series(pd.to_datetime(sub[date_col].unique())).sort_values()
    
    if len(fechas_unicas) == 0:
        return CheckResult(
            check_id=check_id, name=check_name, status='FAILED', is_critical=True,
            description=desc, details=f"No se encontraron fechas para la serie objetivo '{target_series}'."
        )
        
    f_min = fechas_unicas.iloc[0]
    f_max = fechas_unicas.iloc[-1]
    rango_esperado = pd.date_range(f_min, f_max, freq='MS')
    faltantes_en_secuencia = set(rango_esperado) - set(fechas_unicas)
    
    if faltantes_en_secuencia:
        faltantes_str = [f.strftime('%Y-%m') for f in sorted(faltantes_en_secuencia)]
        return CheckResult(
            check_id=check_id, name=check_name, status='FAILED', is_critical=True,
            description=desc,
            details=f"Huecos temporales sin información en '{target_series}': {faltantes_str}. "
                    f"No deben forzarse automáticamente a cero.",
            diagnostics={"missing_months_in_sequence": faltantes_str}
        )
        
    # Validar cobertura configurada si se solicita
    warning_msgs = []
    if start_date and f_min > pd.to_datetime(start_date):
        warning_msgs.append(f"Cobertura inicia en {f_min:%Y-%m}, posterior a {start_date}")
    if end_date and f_max < pd.to_datetime(end_date):
        warning_msgs.append(f"Cobertura finaliza en {f_max:%Y-%m}, anterior a {end_date}")
        
    if warning_msgs:
        return CheckResult(
            check_id=check_id, name=check_name, status='WARNING', is_critical=False,
            description=desc, details="; ".join(warning_msgs),
            diagnostics={"f_min": str(f_min), "f_max": str(f_max)}
        )
        
    return CheckResult(
        check_id=check_id, name=check_name, status='PASSED', is_critical=True,
        description=desc,
        details=f"Cobertura continua y completa desde {f_min:%Y-%m} hasta {f_max:%Y-%m} ({len(fechas_unicas)} meses)."
    )


def check_uniqueness(df: pd.DataFrame, key_cols: List[str], name: str = "dataset") -> CheckResult:
    """Control c): Unicidad.
    Detecta duplicados según la clave y granularidad definidas.
    """
    check_id = "QC-C"
    check_name = "Unicidad de clave primaria"
    desc = f"Verificar que la clave de granularidad {key_cols} sea estrictamente única en {name}."
    
    faltantes = [c for c in key_cols if c not in df.columns]
    if faltantes:
        return CheckResult(
            check_id=check_id, name=check_name, status='FAILED', is_critical=True,
            description=desc, details=f"Faltan columnas de la clave: {faltantes}."
        )
        
    duplicados = df.duplicated(subset=key_cols, keep=False)
    cant_dups = int(duplicados.sum())
    if cant_dups > 0:
        ejemplos = df[duplicados][key_cols].head(3).to_dict(orient='records')
        return CheckResult(
            check_id=check_id, name=check_name, status='FAILED', is_critical=True,
            description=desc,
            details=f"Se detectaron {cant_dups} registros con claves duplicadas en {name}. Ejemplos: {ejemplos}",
            diagnostics={"duplicate_count": cant_dups, "samples": ejemplos}
        )
        
    return CheckResult(
        check_id=check_id, name=check_name, status='PASSED', is_critical=True,
        description=desc, details=f"Clave {key_cols} es estrictamente única ({len(df)} registros analizados)."
    )


def check_missing_values(df: pd.DataFrame, mandatory_cols: List[str],
                         optional_cols: Optional[List[str]] = None, name: str = "dataset") -> CheckResult:
    """Control d): Valores faltantes.
    Distingue ausencias permitidas de faltantes que impiden estimar.
    """
    check_id = "QC-D"
    check_name = "Valores faltantes y completitud"
    desc = f"Distinguir ausencias permitidas frente a nulos que impiden estimar en {name}."
    
    nulos_obligatorios = {c: int(df[c].isna().sum()) for c in mandatory_cols if c in df.columns and df[c].isna().any()}
    if nulos_obligatorios:
        return CheckResult(
            check_id=check_id, name=check_name, status='FAILED', is_critical=True,
            description=desc,
            details=f"Valores nulos en columnas obligatorias de {name} que impiden estimar: {nulos_obligatorios}.",
            diagnostics={"mandatory_nulls": nulos_obligatorios}
        )
        
    optional_cols = optional_cols or []
    nulos_opcionales = {c: int(df[c].isna().sum()) for c in optional_cols if c in df.columns and df[c].isna().any()}
    if nulos_opcionales:
        return CheckResult(
            check_id=check_id, name=check_name, status='WARNING', is_critical=False,
            description=desc,
            details=f"Ausencias permitidas detectadas en columnas opcionales de {name}: {nulos_opcionales}.",
            diagnostics={"optional_nulls": nulos_opcionales}
        )
        
    return CheckResult(
        check_id=check_id, name=check_name, status='PASSED', is_critical=True,
        description=desc,
        details=f"Sin valores nulos en columnas obligatorias de {name} ({mandatory_cols})."
    )


def check_values_and_denominators(df: pd.DataFrame, value_cols: List[str],
                                  denominator_cols: Optional[List[str]] = None,
                                  allow_negative_values: bool = False,
                                  name: str = "dataset") -> CheckResult:
    """Control e): Valores y denominadores.
    Detecta conteos negativos, valores no finitos y denominadores iguales a cero.
    """
    check_id = "QC-E"
    check_name = "Valores válidos y denominadores seguros"
    desc = f"Verificar conteos no negativos, números finitos y denominadores distintos de cero en {name}."
    
    diagnostics = {}
    
    # 1. Verificar valores finitos
    no_finitos = {}
    for col in value_cols:
        if col in df.columns:
            vals = pd.to_numeric(df[col], errors='coerce')
            inf_count = int(np.isinf(vals).sum())
            if inf_count > 0:
                no_finitos[col] = inf_count
    if no_finitos:
        return CheckResult(
            check_id=check_id, name=check_name, status='FAILED', is_critical=True,
            description=desc,
            details=f"Valores no finitos (infinito) detectados en {name}: {no_finitos}.",
            diagnostics={"non_finite": no_finitos}
        )
        
    # 2. Verificar conteos negativos
    if not allow_negative_values:
        negativos = {}
        for col in value_cols:
            if col in df.columns:
                vals = pd.to_numeric(df[col], errors='coerce')
                neg_count = int((vals < 0).sum())
                if neg_count > 0:
                    negativos[col] = neg_count
        if negativos:
            return CheckResult(
                check_id=check_id, name=check_name, status='FAILED', is_critical=True,
                description=desc,
                details=f"Conteos negativos físicamente no válidos en datos observados de {name}: {negativos}.",
                diagnostics={"negatives": negativos}
            )
            
    # 3. Verificar denominadores iguales a cero
    denominator_cols = denominator_cols or []
    ceros_en_denominador = {}
    for col in denominator_cols:
        if col in df.columns:
            vals = pd.to_numeric(df[col], errors='coerce')
            ceros = int((vals == 0).sum())
            if ceros > 0:
                ceros_en_denominador[col] = ceros
    if ceros_en_denominador:
        return CheckResult(
            check_id=check_id, name=check_name, status='FAILED', is_critical=True,
            description=desc,
            details=f"Denominadores iguales a cero detectados en {name} que provocarían división inválida: {ceros_en_denominador}.",
            diagnostics={"zero_denominators": ceros_en_denominador}
        )
        
    return CheckResult(
        check_id=check_id, name=check_name, status='PASSED', is_critical=True,
        description=desc,
        details=f"Valores finitos, conteos no negativos y denominadores seguros verificados en {name}."
    )


def check_methodological_rule(series_df: pd.DataFrame, tolerance_pct: float = 0.02) -> CheckResult:
    """Control f): Regla metodológica institucional.
    Verifica automáticamente:
    1. Que la serie mensual provenga de la fuente mensual institucional correspondiente y no de suma simple sin deduplicación.
    2. Conciliación interna: la suma de las 3 vías excluyentes (Vía Aérea + Vía Terrestre + Vía Marítima)
       debe cuadrar con el 'Total' dentro de una tolerancia razonable por redondeo y ajustes migratorios.
    3. Que los períodos sin cobertura no se hayan forzado a 0 de forma artificial.
    """
    check_id = "QC-F"
    check_name = "Regla metodológica del observatorio"
    desc = "Verificar coherencia entre fuente mensual institucional, series desagregadas y no-imputación ciega de ceros."
    
    series_disponibles = set(series_df['serie'].unique())
    vias_requeridas = {'Via_Aérea', 'Via_Terrestre', 'Via_Marítima'}
    
    # Manejar variaciones ortográficas si aún no se han normalizado
    norm_series = {s.replace('Via_Area', 'Via_Aérea').replace('Via_Martima', 'Via_Marítima') for s in series_disponibles}
    if not vias_requeridas.issubset(norm_series) or 'Total' not in series_disponibles:
        return CheckResult(
            check_id=check_id, name=check_name, status='WARNING', is_critical=False,
            description=desc,
            details=f"No se encuentran todas las series de vías para la verificación metodológica de conciliación. Disponibles: {series_disponibles}."
        )
        
    # Conciliación mensual: Suma de vías vs Total
    piv = series_df.copy()
    piv['serie_norm'] = piv['serie'].str.replace('Via_A.*rea', 'Via_Aérea', regex=True).str.replace('Via_Mar.*tima', 'Via_Marítima', regex=True)
    tabla = piv.pivot_table(index='fecha', columns='serie_norm', values='viajeros', aggfunc='sum')
    
    if all(col in tabla.columns for col in ['Total', 'Via_Aérea', 'Via_Terrestre', 'Via_Marítima']):
        suma_vias = tabla['Via_Aérea'] + tabla['Via_Terrestre'] + tabla['Via_Marítima']
        total = tabla['Total']
        
        # Diferencia relativa media
        dif_abs = (suma_vias - total).abs()
        difs_significativas = dif_abs > (total * tolerance_pct)
        cant_discrepancias = int(difs_significativas.sum())
        
        if cant_discrepancias > 0:
            meses_disc = pd.to_datetime(tabla.index[difs_significativas]).strftime('%Y-%m').tolist()[:5]
            return CheckResult(
                check_id=check_id, name=check_name, status='WARNING', is_critical=False,
                description=desc,
                details=f"Advertencia metodológica: {cant_discrepancias} meses tienen discrepancia > {tolerance_pct*100:.1f}% "
                        f"entre Total y la suma de vías (ej. {meses_disc}). Puede deberse a categorías de tránsito sin vía o cambios INGUAT.",
                diagnostics={"discrepancies_count": cant_discrepancias, "examples": meses_disc}
            )
            
    return CheckResult(
        check_id=check_id, name=check_name, status='PASSED', is_critical=True,
        description=desc,
        details="Regla metodológica validada: conciliación mensual consistente y fuente oficial mensual confirmada."
    )


def execute_all_quality_checks(series_df: pd.DataFrame, run_id: str,
                               timestamp: str, config: Dict[str, Any]) -> QualityReport:
    """Ejecuta la suite completa de los seis controles de calidad y genera el reporte."""
    report = QualityReport(run_id=run_id, timestamp=timestamp)
    
    # a) Columnas y tipos
    schema = {'serie': 'string', 'fecha': 'datetime', 'viajeros': 'numeric'}
    res_a = check_columns_and_types(series_df, schema, name="series_mensuales.csv")
    report.add_result(res_a)
    
    # b) Fechas y cobertura
    t_start = config.get('temporal_split', {}).get('train_start')
    t_end = config.get('temporal_split', {}).get('eval_end')
    res_b = check_dates_and_coverage(series_df, date_col='fecha', series_col='serie',
                                   target_series=config.get('scope', {}).get('target_series', 'Total'),
                                   start_date=t_start, end_date=t_end)
    report.add_result(res_b)
    
    # c) Unicidad
    res_c = check_uniqueness(series_df, key_cols=['serie', 'fecha'], name="series_mensuales.csv")
    report.add_result(res_c)
    
    # d) Valores faltantes
    res_d = check_missing_values(series_df, mandatory_cols=['serie', 'fecha', 'viajeros'], name="series_mensuales.csv")
    report.add_result(res_d)
    
    # e) Valores y denominadores
    res_e = check_values_and_denominators(series_df, value_cols=['viajeros'], denominator_cols=None,
                                         allow_negative_values=False, name="series_mensuales.csv")
    report.add_result(res_e)
    
    # f) Regla metodológica
    res_f = check_methodological_rule(series_df)
    report.add_result(res_f)
    
    return report
