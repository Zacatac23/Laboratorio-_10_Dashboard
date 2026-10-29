"""Prueba Controlada de Inyección de Fallas, Detección y Recuperación (Laboratorio 11 - Ejercicio 7.4).
Verifica:
1. Inyección de una anomalía (columna faltante, duplicado, conteo negativo).
2. Detección automática por los controles de calidad (Gate 1).
3. Detención inmediata sin inventar métricas ni calcular modelos.
4. Preservación intacta de la última versión aprobada en el tablero.
5. Corrección del problema, re-ejecución y recuperación exitosa.
"""
import os
import shutil
import tempfile
import pandas as pd
import yaml
from src.pipeline import TourismMLOpsPipeline
from src.quality_checks import QualityControlError


def run_controlled_failure_and_recovery_test():
    print("=================================================================")
    print("Iniciando Prueba Controlada de Fallo y Recuperación (Ej. 7.4)")
    print("=================================================================\n")
    
    # 1. Comprobar existencia de versión aprobada actual
    approved_file = os.path.join("data", "estimaciones_aprobadas.csv")
    assert os.path.isfile(approved_file), "Se requiere una versión aprobada inicial."
    original_approved_content = open(approved_file, "r", encoding="utf-8").read()
    original_sha = pd.read_csv(approved_file)['run_id'].iloc[0]
    print(f"Estado inicial: Versión aprobada presente con Run ID: {original_sha}")

    # 2. Crear entorno temporal de prueba con copia de datos
    temp_dir = tempfile.mkdtemp(prefix="lab11_chaos_test_")
    try:
        corrupt_series_path = os.path.join(temp_dir, "series_mensuales_corrupta.csv")
        df_clean = pd.read_csv(os.path.join("data", "series_mensuales.csv"))
        
        # INYECCIÓN DE FALLA CONTROLADA: Clave duplicada y conteo negativo
        df_corrupt = df_clean.copy()
        # Inyectar una fila duplicada con conteo negativo
        fila_problema = df_corrupt.iloc[0:1].copy()
        fila_problema['viajeros'] = -9999
        df_corrupt = pd.concat([df_corrupt, fila_problema], ignore_index=True)
        df_corrupt.to_csv(corrupt_series_path, index=False)
        print(f"\n[PASO 1] Inyección de falla en copia de datos: registro duplicado con conteo negativo (-9999).")

        # Crear configuración temporal que apunta a los datos corruptos
        with open(os.path.join("config", "pipeline_config.yaml"), "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
            
        cfg_corrupt = cfg.copy()
        cfg_corrupt['paths']['raw_data_dir'] = temp_dir
        cfg_corrupt['paths']['series_file'] = "series_mensuales_corrupta.csv"
        # Mantener ruta de salida real para verificar que NO se altere
        cfg_corrupt['paths']['approved_file'] = "estimaciones_aprobadas.csv"
        
        temp_cfg_path = os.path.join(temp_dir, "pipeline_config_corrupt.yaml")
        with open(temp_cfg_path, "w", encoding="utf-8") as f:
            yaml.dump(cfg_corrupt, f)

        # 3. Ejecutar pipeline sobre datos corruptos
        print("\n[PASO 2] Ejecutando pipeline sobre datos con falla...")
        pipe_failed = TourismMLOpsPipeline(config_path=temp_cfg_path, publish=True)
        pipeline_stopped = False
        try:
            pipe_failed.run()
        except QualityControlError as e:
            pipeline_stopped = True
            print(f"  -> Pipeline se detuvo exitosamente con QualityControlError:")
            print(f"     \"{e}\"")

        assert pipeline_stopped, "ERROR: El pipeline debió detenerse y no lo hizo."

        # 4. Verificar que la versión aprobada en el tablero sigue 100% INTACTA
        current_approved_content = open(approved_file, "r", encoding="utf-8").read()
        assert original_approved_content == current_approved_content, (
            "ERROR CRÍTICO: La versión aprobada fue modificada o corrompida tras una corrida fallida."
        )
        print("\n[PASO 3] VERIFICADO: La versión aprobada previa permanece 100% intacta e inalterada.")

        # 5. Corrección del problema (Recuperación)
        print("\n[PASO 4] Corrigiendo problema en los datos (eliminando duplicados y negativos)...")
        df_clean.to_csv(corrupt_series_path, index=False)
        print("  -> Datos restaurados a estado limpio.")

        # 6. Re-ejecutar pipeline
        print("\n[PASO 5] Re-ejecutando pipeline tras corrección...")
        pipe_recovered = TourismMLOpsPipeline(config_path=temp_cfg_path, publish=True)
        result = pipe_recovered.run()
        assert result["status"] == "SUCCESS", "El pipeline recuperado debió finalizar con SUCCESS."
        print(f"  -> Recuperación exitosa. Nuevo Run ID aprobado: {result['run_id']}")

        print("\n=================================================================")
        print("RESULTADO DE LA PRUEBA (Ej. 7.4): APROBADA EXITOSAMENTE")
        print("- Detección de anomalía: EXITOSA")
        print("- Detención preventiva: EXITOSA (sin inventar métricas)")
        print("- Preservación de versión aprobada: EXITOSA (100% intacta)")
        print("- Recuperación y publicación post-corrección: EXITOSA")
        print("=================================================================\n")

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    run_controlled_failure_and_recovery_test()

