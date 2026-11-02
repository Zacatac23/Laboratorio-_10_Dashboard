"""Controles automáticos de calidad QC-A … QC-F (Laboratorio 11).

Cada control distingue PASSED, WARNING, FAILED y, cuando aplica, NO_VERIFICABLE.
Un FAILED crítico bloquea modelado y publicación.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd


class QualityControlError(Exception):
    """Fallo crítico de calidad que detiene el pipeline."""


VALID_STATUSES = {"PASSED", "WARNING", "FAILED", "NO_VERIFICABLE"}


@dataclass
class CheckResult:
    check_id: str
    name: str
    status: str
    is_critical: bool
    description: str
    details: str
    diagnostics: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.status not in VALID_STATUSES:
            raise ValueError(f"Estado de control no reconocido: {self.status}")


@dataclass
class QualityReport:
    run_id: str
    timestamp: str
    checks: List[CheckResult] = field(default_factory=list)
    critical_passed: bool = True
    warnings_count: int = 0
    errors_count: int = 0
    sources_used_in_modeling: List[str] = field(default_factory=list)
    sources_context_only: List[str] = field(default_factory=list)

    def add_result(self, result: CheckResult):
        self.checks.append(result)
        if result.status in ("FAILED", "NO_VERIFICABLE") and result.is_critical:
            self.critical_passed = False
            self.errors_count += 1
        elif result.status == "WARNING":
            self.warnings_count += 1
        elif result.status == "FAILED" and not result.is_critical:
            self.warnings_count += 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "timestamp": self.timestamp,
            "critical_passed": self.critical_passed,
            "errors_count": self.errors_count,
            "warnings_count": self.warnings_count,
            "sources_used_in_modeling": self.sources_used_in_modeling,
            "sources_context_only": self.sources_context_only,
            "checks": [asdict(c) for c in self.checks],
        }


def _is_blank_label(value: Any) -> bool:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return True
    text = str(value).strip()
    return text == "" or text.lower() in {"nan", "none", "null", "<na>"}


def check_columns_and_types(
    df: pd.DataFrame,
    expected_schema: Dict[str, str],
    name: str = "dataset",
) -> CheckResult:
    """QC-A: columnas requeridas y tipos. No trata nulos convertidos a 'nan' como válidos."""
    check_id, check_name = "QC-A", "Columnas y tipos requeridos"
    desc = f"Verificar presencia de columnas requeridas y tipos compatibles en {name}."

    missing_cols = [col for col in expected_schema if col not in df.columns]
    if missing_cols:
        return CheckResult(
            check_id=check_id, name=check_name, status="FAILED", is_critical=True,
            description=desc,
            details=f"Faltan columnas indispensables en {name}: {missing_cols}.",
            diagnostics={"missing_columns": missing_cols},
        )

    incompatible: List[str] = []
    for col, expected_type in expected_schema.items():
        series = df[col]
        if expected_type == "datetime":
            parsed = pd.to_datetime(series, errors="coerce")
            bad = int(parsed.isna().sum())
            if bad:
                incompatible.append(f"{col}: {bad} valores no convertibles a fecha")
        elif expected_type == "numeric":
            parsed = pd.to_numeric(series, errors="coerce")
            # Nulos ya existentes vs no numéricos: ambos impiden tipo numérico válido aquí
            non_numeric = int(parsed.isna().sum())
            if non_numeric:
                incompatible.append(f"{col}: {non_numeric} valores no numéricos o nulos")
        elif expected_type == "string":
            # Evitar astype(str) sobre NaN → 'nan' como si fuera etiqueta válida
            nulls = int(series.isna().sum())
            if nulls:
                incompatible.append(f"{col}: {nulls} nulos (no convertidos a texto válido)")
            blanks = int(series.map(_is_blank_label).sum()) - nulls
            if blanks > 0:
                incompatible.append(f"{col}: {blanks} etiquetas vacías o 'nan'/'null'")
        else:
            incompatible.append(f"{col}: tipo esperado desconocido '{expected_type}'")

    if incompatible:
        return CheckResult(
            check_id=check_id, name=check_name, status="FAILED", is_critical=True,
            description=desc,
            details=f"Tipos incompatibles o valores corruptos en {name}: {incompatible}.",
            diagnostics={"incompatible_columns": incompatible},
        )

    return CheckResult(
        check_id=check_id, name=check_name, status="PASSED", is_critical=True,
        description=desc,
        details=f"Columnas y tipos conformes en {name}: {list(expected_schema.keys())}.",
    )


def check_dates_and_coverage(
    df: pd.DataFrame,
    date_col: str = "fecha",
    series_col: str = "serie",
    target_series: str = "Total",
    required_start: Optional[str] = None,
    required_end: Optional[str] = None,
    require_full_required_window: bool = True,
) -> CheckResult:
    """QC-B: fechas mensuales y cobertura. No imputa ceros. Usa ventana requerida del YAML."""
    check_id, check_name = "QC-B", "Fechas y cobertura temporal"
    desc = (
        f"Validar normalización mensual y cobertura indispensable de '{target_series}'. "
        "Los huecos no se rellenan con cero."
    )

    if date_col not in df.columns:
        return CheckResult(
            check_id=check_id, name=check_name, status="FAILED", is_critical=True,
            description=desc, details=f"Columna de fecha '{date_col}' no presente.",
        )

    fechas = pd.to_datetime(df[date_col], errors="coerce")
    invalidas = int(fechas.isna().sum())
    if invalidas:
        return CheckResult(
            check_id=check_id, name=check_name, status="FAILED", is_critical=True,
            description=desc,
            details=f"Se detectaron {invalidas} fechas no convertibles o inválidas.",
            diagnostics={"invalid_dates_count": invalidas},
        )

    if (fechas.dt.day != 1).any() or (fechas != fechas.dt.normalize()).any():
        return CheckResult(
            check_id=check_id, name=check_name, status="FAILED", is_critical=True,
            description=desc,
            details="Las fechas mensuales deben estar normalizadas al primer día del mes (día 1).",
        )

    sub = df[df[series_col] == target_series] if series_col in df.columns else df
    fechas_unicas = pd.Series(pd.to_datetime(sub[date_col].unique())).sort_values()
    if fechas_unicas.empty:
        return CheckResult(
            check_id=check_id, name=check_name, status="FAILED", is_critical=True,
            description=desc,
            details=f"No hay fechas para la serie objetivo '{target_series}'.",
        )

    f_min, f_max = fechas_unicas.iloc[0], fechas_unicas.iloc[-1]
    # Huecos internos en el rango realmente presente: no imputar
    internos = set(pd.date_range(f_min, f_max, freq="MS")) - set(fechas_unicas)
    if internos:
        faltantes = [f.strftime("%Y-%m") for f in sorted(internos)]
        return CheckResult(
            check_id=check_id, name=check_name, status="FAILED", is_critical=True,
            description=desc,
            details=(
                f"Huecos temporales internos sin información en '{target_series}': {faltantes}. "
                "No deben forzarse a cero."
            ),
            diagnostics={"missing_months_in_sequence": faltantes},
        )

    diagnostics = {
        "f_min": str(f_min.date()),
        "f_max": str(f_max.date()),
        "n_months": int(len(fechas_unicas)),
    }

    if required_start and required_end and require_full_required_window:
        req_start = pd.Timestamp(required_start)
        req_end = pd.Timestamp(required_end)
        esperado = pd.date_range(req_start, req_end, freq="MS")
        faltan_ventana = sorted(set(esperado) - set(fechas_unicas))
        if faltan_ventana:
            faltantes = [f.strftime("%Y-%m") for f in faltan_ventana]
            return CheckResult(
                check_id=check_id, name=check_name, status="FAILED", is_critical=True,
                description=desc,
                details=(
                    f"Faltan {len(faltantes)} meses indispensables en la ventana "
                    f"{req_start:%Y-%m}–{req_end:%Y-%m} para modelar '{target_series}'. "
                    f"Ejemplos: {faltantes[:8]}. Restaure los CSV o ajuste el YAML."
                ),
                diagnostics={**diagnostics, "missing_required_months": faltantes},
            )

    return CheckResult(
        check_id=check_id, name=check_name, status="PASSED", is_critical=True,
        description=desc,
        details=f"Cobertura continua de '{target_series}' desde {f_min:%Y-%m} hasta {f_max:%Y-%m} "
                f"({len(fechas_unicas)} meses). Sin imputación de ceros.",
        diagnostics=diagnostics,
    )


def check_uniqueness(
    df: pd.DataFrame,
    key_cols: List[str],
    name: str = "dataset",
    sample_limit: int = 5,
) -> CheckResult:
    """QC-C: unicidad por clave granular. Muestras limitadas (solo claves, sin microdatos extra)."""
    check_id, check_name = "QC-C", "Unicidad de clave primaria"
    desc = f"Verificar unicidad de la clave {key_cols} en {name}."

    faltantes = [c for c in key_cols if c not in df.columns]
    if faltantes:
        return CheckResult(
            check_id=check_id, name=check_name, status="FAILED", is_critical=True,
            description=desc, details=f"Faltan columnas de la clave: {faltantes}.",
        )

    duplicados = df.duplicated(subset=key_cols, keep=False)
    cant = int(duplicados.sum())
    if cant:
        muestras = (
            df.loc[duplicados, key_cols]
            .drop_duplicates()
            .head(sample_limit)
            .astype(str)
            .to_dict(orient="records")
        )
        return CheckResult(
            check_id=check_id, name=check_name, status="FAILED", is_critical=True,
            description=desc,
            details=f"Se detectaron {cant} filas con clave duplicada en {name}.",
            diagnostics={"duplicate_row_count": cant, "key_samples": muestras},
        )

    return CheckResult(
        check_id=check_id, name=check_name, status="PASSED", is_critical=True,
        description=desc,
        details=f"Clave {key_cols} única ({len(df)} registros).",
    )


def check_missing_values(
    df: pd.DataFrame,
    mandatory_cols: List[str],
    optional_cols: Optional[List[str]] = None,
    name: str = "dataset",
) -> CheckResult:
    """QC-D: distingue faltantes obligatorios de opcionales. No completa ausencias."""
    check_id, check_name = "QC-D", "Valores faltantes y completitud"
    desc = f"Distinguir ausencias permitidas frente a nulos que impiden estimar en {name}."

    nulos_obl = {
        c: int(df[c].isna().sum())
        for c in mandatory_cols
        if c in df.columns and df[c].isna().any()
    }
    if nulos_obl:
        return CheckResult(
            check_id=check_id, name=check_name, status="FAILED", is_critical=True,
            description=desc,
            details=f"Nulos en columnas obligatorias de {name}: {nulos_obl}.",
            diagnostics={"mandatory_nulls": nulos_obl},
        )

    optional_cols = optional_cols or []
    nulos_opc = {
        c: int(df[c].isna().sum())
        for c in optional_cols
        if c in df.columns and df[c].isna().any()
    }
    if nulos_opc:
        return CheckResult(
            check_id=check_id, name=check_name, status="WARNING", is_critical=False,
            description=desc,
            details=f"Ausencias permitidas en opcionales de {name}: {nulos_opc}.",
            diagnostics={"optional_nulls": nulos_opc},
        )

    return CheckResult(
        check_id=check_id, name=check_name, status="PASSED", is_critical=True,
        description=desc,
        details=f"Sin nulos en obligatorias de {name} ({mandatory_cols}).",
    )


def check_values_and_denominators(
    df: pd.DataFrame,
    value_cols: List[str],
    denominator_cols: Optional[List[str]] = None,
    allow_negative_values: bool = False,
    name: str = "dataset",
) -> CheckResult:
    """QC-E: NaN/inf/negativos en conteos y denominadores cero. Cero de viajeros es válido."""
    check_id, check_name = "QC-E", "Valores válidos y denominadores seguros"
    desc = (
        f"Verificar finitos, no negativos (si aplica) y denominadores ≠ 0 en {name}. "
        "Un cero legítimo de viajeros no es error."
    )

    nan_counts: Dict[str, int] = {}
    inf_counts: Dict[str, int] = {}
    for col in value_cols:
        if col not in df.columns:
            continue
        vals = pd.to_numeric(df[col], errors="coerce")
        nan_counts[col] = int(vals.isna().sum())
        inf_counts[col] = int(np.isinf(vals.to_numpy(dtype=float, na_value=np.nan)).sum())

    nans = {k: v for k, v in nan_counts.items() if v}
    if nans:
        return CheckResult(
            check_id=check_id, name=check_name, status="FAILED", is_critical=True,
            description=desc,
            details=f"NaN en columnas de valor de {name}: {nans}.",
            diagnostics={"nan_counts": nans},
        )
    infs = {k: v for k, v in inf_counts.items() if v}
    if infs:
        return CheckResult(
            check_id=check_id, name=check_name, status="FAILED", is_critical=True,
            description=desc,
            details=f"Infinitos en {name}: {infs}.",
            diagnostics={"inf_counts": infs},
        )

    if not allow_negative_values:
        negativos = {}
        for col in value_cols:
            if col not in df.columns:
                continue
            vals = pd.to_numeric(df[col], errors="coerce")
            neg = int((vals < 0).sum())
            if neg:
                negativos[col] = neg
        if negativos:
            return CheckResult(
                check_id=check_id, name=check_name, status="FAILED", is_critical=True,
                description=desc,
                details=f"Conteos negativos no válidos en {name}: {negativos}.",
                diagnostics={"negatives": negativos},
            )

    zero_den = {}
    for col in denominator_cols or []:
        if col not in df.columns:
            continue
        vals = pd.to_numeric(df[col], errors="coerce")
        ceros = int((vals == 0).sum())
        if ceros:
            zero_den[col] = ceros
    if zero_den:
        return CheckResult(
            check_id=check_id, name=check_name, status="FAILED", is_critical=True,
            description=desc,
            details=f"Denominadores iguales a cero en {name}: {zero_den}.",
            diagnostics={"zero_denominators": zero_den},
        )

    return CheckResult(
        check_id=check_id, name=check_name, status="PASSED", is_critical=True,
        description=desc,
        details=f"Valores finitos y seguros en {name}; ceros de viajeros permitidos.",
    )


def check_methodological_rule(
    series_df: pd.DataFrame,
    tolerance_pct: float = 0.02,
    fail_on_material_discrepancy: bool = True,
) -> CheckResult:
    """QC-F: conciliación Total vs vías excluyentes. Sin insumos → NO_VERIFICABLE."""
    check_id, check_name = "QC-F", "Regla metodológica del observatorio"
    desc = (
        "Verificar coherencia mensual entre Total y la suma de vías excluyentes "
        "(aérea+terrestre+marítima). No suma tipos migratorios con vías."
    )

    if "serie" not in series_df.columns or "fecha" not in series_df.columns or "viajeros" not in series_df.columns:
        return CheckResult(
            check_id=check_id, name=check_name, status="NO_VERIFICABLE", is_critical=True,
            description=desc,
            details="Faltan columnas indispensables (serie/fecha/viajeros) para verificar la regla.",
        )

    piv = series_df.copy()
    piv["serie_norm"] = (
        piv["serie"]
        .astype(str)
        .str.replace(r"Via_A.*rea", "Via_Aérea", regex=True)
        .str.replace(r"Via_Mar.*tima", "Via_Marítima", regex=True)
    )
    vias = ["Via_Aérea", "Via_Terrestre", "Via_Marítima"]
    disponibles = set(piv["serie_norm"].unique())
    if "Total" not in disponibles or not set(vias).issubset(disponibles):
        return CheckResult(
            check_id=check_id, name=check_name, status="NO_VERIFICABLE", is_critical=True,
            description=desc,
            details=(
                "No se puede verificar la regla: faltan Total o alguna vía excluyente. "
                f"Disponibles: {sorted(disponibles)}. No se declara PASSED ficticio."
            ),
            diagnostics={"series_disponibles": sorted(disponibles)},
        )

    tabla = piv.pivot_table(index="fecha", columns="serie_norm", values="viajeros", aggfunc="sum")
    suma_vias = tabla[vias].sum(axis=1)
    total = tabla["Total"]
    # Solo meses con Total y vías presentes (comparables)
    mask = total.notna() & suma_vias.notna()
    if not mask.any():
        return CheckResult(
            check_id=check_id, name=check_name, status="NO_VERIFICABLE", is_critical=True,
            description=desc,
            details="No hay meses comparables Total vs suma de vías.",
        )

    dif_abs = (suma_vias[mask] - total[mask]).abs()
    umbral = (total[mask].abs() * tolerance_pct).clip(lower=1.0)
    material = dif_abs > umbral
    n_disc = int(material.sum())
    if n_disc:
        ejemplos = pd.to_datetime(dif_abs.index[material]).strftime("%Y-%m").tolist()[:5]
        status = "FAILED" if fail_on_material_discrepancy else "WARNING"
        return CheckResult(
            check_id=check_id, name=check_name, status=status,
            is_critical=fail_on_material_discrepancy,
            description=desc,
            details=(
                f"{n_disc} meses con discrepancia > {tolerance_pct * 100:.1f}% entre Total y "
                f"suma de vías (ej. {ejemplos}). Invalidaría estimaciones que asumen esa "
                "identidad mensual."
            ),
            diagnostics={"discrepancies_count": n_disc, "examples": ejemplos},
        )

    return CheckResult(
        check_id=check_id, name=check_name, status="PASSED", is_critical=True,
        description=desc,
        details="Conciliación mensual Total ≈ suma de vías dentro de la tolerancia.",
    )


def _check_values_and_repartition_denominator(
    series_df: pd.DataFrame,
    target: str,
    t_cfg: Dict[str, Any],
) -> CheckResult:
    """QC-E del pipeline: valores válidos y denominador del factor de reparto.

    f_i = suma(serie_i en ajuste) / suma(target en ajuste)
    (``model_engine.calculate_repartition_factors``). Si ese denominador es cero,
    el flujo se detiene en QC, antes del modelado.
    """
    valores = check_values_and_denominators(
        series_df, value_cols=["viajeros"], allow_negative_values=False, name="series_mensuales.csv"
    )
    if valores.status != "PASSED" or not {"serie", "fecha", "viajeros"} <= set(series_df.columns):
        return valores

    fechas = pd.to_datetime(series_df["fecha"], errors="coerce")
    en_ajuste = series_df["serie"] == target
    if t_cfg.get("train_start"):
        en_ajuste &= fechas >= pd.Timestamp(t_cfg["train_start"])
    if t_cfg.get("train_end"):
        en_ajuste &= fechas <= pd.Timestamp(t_cfg["train_end"])
    denominador = float(pd.to_numeric(series_df.loc[en_ajuste, "viajeros"], errors="coerce").sum())
    columna = f"suma_{target}_ajuste"
    resultado = check_values_and_denominators(
        pd.DataFrame({columna: [denominador]}),
        value_cols=[],
        denominator_cols=[columna],
        name="denominador del factor de reparto",
    )
    if resultado.status == "FAILED":
        return CheckResult(
            check_id=valores.check_id, name=valores.name, status="FAILED", is_critical=True,
            description=valores.description,
            details=(
                f"Denominador del factor de reparto igual a cero: suma de {target} en el "
                f"periodo de ajuste = {denominador:g}."
            ),
            diagnostics={"zero_denominators": {columna: 1}, columna: denominador},
        )
    return CheckResult(
        check_id=valores.check_id, name=valores.name, status=valores.status,
        is_critical=valores.is_critical, description=valores.description,
        details=(
            f"{valores.details} Denominador del factor de reparto "
            f"(suma de {target} en ajuste) = {denominador:,.0f} ≠ 0."
        ),
        diagnostics={columna: denominador},
    )


def execute_all_quality_checks(
    series_df: pd.DataFrame,
    run_id: str,
    timestamp: str,
    config: Dict[str, Any],
    pais_df: Optional[pd.DataFrame] = None,
    via_df: Optional[pd.DataFrame] = None,
) -> QualityReport:
    """Ejecuta QC-A…F sobre la fuente de modelado y, si se pasan, QC de contexto."""
    report = QualityReport(
        run_id=run_id,
        timestamp=timestamp,
        sources_used_in_modeling=["series_mensuales.csv"],
        sources_context_only=["pais_mensual.csv", "via_frontera.csv"],
    )

    t_cfg = config.get("temporal_split", {})
    scope = config.get("scope", {})
    target = scope.get("target_series", "Total")
    qcfg = config.get("quality_thresholds", {})
    tol = float(qcfg.get("methodological_tolerance_pct", 0.02))

    schema = {"serie": "string", "fecha": "datetime", "viajeros": "numeric"}
    report.add_result(check_columns_and_types(series_df, schema, name="series_mensuales.csv"))
    report.add_result(
        check_dates_and_coverage(
            series_df,
            target_series=target,
            required_start=t_cfg.get("train_start"),
            required_end=t_cfg.get("eval_end"),
            require_full_required_window=True,
        )
    )
    report.add_result(check_uniqueness(series_df, ["serie", "fecha"], name="series_mensuales.csv"))
    report.add_result(
        check_missing_values(series_df, ["serie", "fecha", "viajeros"], name="series_mensuales.csv")
    )
    report.add_result(_check_values_and_repartition_denominator(series_df, target, t_cfg))
    report.add_result(
        check_methodological_rule(
            series_df,
            tolerance_pct=tol,
            fail_on_material_discrepancy=bool(qcfg.get("methodological_fail_on_discrepancy", True)),
        )
    )

    # Controles de contexto (no bloquean modelado salvo que se marquen críticos en config)
    context_critical = bool(qcfg.get("context_sources_critical", False))
    if pais_df is not None:
        r = check_uniqueness(pais_df, ["fecha", "pais"], name="pais_mensual.csv")
        if not context_critical and r.status == "FAILED":
            r = CheckResult(
                check_id=r.check_id, name=r.name, status="WARNING", is_critical=False,
                description=r.description + " (fuente de contexto; no usada en modelado).",
                details=r.details, diagnostics=r.diagnostics,
            )
        report.add_result(r)
        r2 = check_values_and_denominators(
            pais_df, value_cols=["viajeros"], name="pais_mensual.csv"
        )
        if not context_critical and r2.status == "FAILED":
            r2 = CheckResult(
                check_id=r2.check_id, name=r2.name + " (contexto)", status="WARNING",
                is_critical=False, description=r2.description, details=r2.details,
                diagnostics=r2.diagnostics,
            )
        report.add_result(r2)

    if via_df is not None:
        r = check_uniqueness(via_df, ["fecha", "via", "frontera"], name="via_frontera.csv")
        if not context_critical and r.status == "FAILED":
            r = CheckResult(
                check_id=r.check_id, name=r.name, status="WARNING", is_critical=False,
                description=r.description + " (fuente de contexto; no usada en modelado).",
                details=r.details, diagnostics=r.diagnostics,
            )
        report.add_result(r)

    return report
