# Seguridad del repositorio y materiales institucionales

Auditoría hecha el 2026-11-01 sobre el clon local (`main` en `299ec7c`, una sola rama) y su historial completo (`git log --all`). Solo se hicieron consultas de lectura: **no se cambió la visibilidad, no se reescribió el historial y no se eliminaron archivos del remoto.**

## Hallazgos

| # | Hallazgo | Evidencia | Severidad |
| --- | --- | --- | --- |
| 1 | Los repositorios `Zacatac23/Laboratorio-_10_Dashboard` (remoto `origin`) y `luispedrolira/lab10-data` siguen **públicos**. La guía exige un repositorio privado con acceso solo para docentes y auxiliares. | `GET https://api.github.com/repos/<repo>` **sin autenticar** responde HTTP 200 en ambos. Un repositorio privado responde 404. | Alta |
| 2 | Los CSV de datos institucionales se versionan desde el 2026-10-25 y están en el historial: `data/series_mensuales.csv`, `pais_mensual.csv`, `via_frontera.csv`, `pronosticos.csv`, `catch22_pca.csv` y `estimaciones_aprobadas.csv`. | `git log --all --name-only` | Alta mientras el repositorio sea público |
| 3 | El PDF `reporte_final_lab10/Laboratorio_10_Documento_Diseno_Final.pdf` se versiona. | `git ls-files` | Media (revisar si contiene datos o información institucional) |
| 4 | `evidencias/unittest.log` contiene una ruta personal (`/home/<usuario>`). | `grep` sobre `evidencias/` | Baja |
| 5 | No se encontraron credenciales, tokens, llaves privadas, `.env`, `mlflow.db` ni `mlruns/` en ningún commit. | `git log --all -p` filtrado por patrones de llaves, tokens, contraseñas y cabeceras `BEGIN … PRIVATE` | — |
| 6 | El README contenía un enlace `file:///c:/Users/...` de una computadora particular. | Corregido a un enlace relativo. | Baja (corregido) |

## Registro de exclusiones

| Debe quedar fuera de git y de la imagen Docker | Mecanismo |
| --- | --- |
| `.env`, `.env.*` (excepto `.env.example`), `.streamlit/secrets.toml`, `*.pem`, `*.key`, `*.p12`, `credentials*.json` | `.gitignore`; `.dockerignore` (lista blanca y reexclusión defensiva) |
| Almacén MLflow: `mlflow_store/`, `mlruns/`, `mlflow.db`, `*.db` | `.gitignore`; en Compose vive en el volumen `mlflow_store` |
| Salidas operativas: `logs/`, `reports/`, `data/backup_aprobadas/`, temporales `data/*.tmp` | `.gitignore` |
| Toda la carpeta `data/` (CSV institucionales, versión aprobada, manifiesto y respaldos), `evidencias/`, PDF | `.dockerignore` (la imagen solo copia código); los datos se montan como volúmenes |

**Pendiente de decisión del equipo:** los CSV de `data/` y `data/estimaciones_aprobadas.csv` (con su manifiesto) siguen versionados porque el tablero y las pruebas los necesitan, y quitarlos del índice borraría las copias locales de cada clon en su siguiente `git pull`. Si se decide dejar de versionarlos, hay que coordinar primero cómo se distribuirán (carpeta compartida institucional) y después ejecutar `git rm --cached data/*.csv` y agregarlos a `.gitignore`.

Archivos sintéticos para reproducibilidad: las pruebas generan sus propios datos sintéticos en carpetas temporales (`tests/test_mlops_integracion.py`) y no necesitan CSV reales adicionales.

## Acciones manuales (requieren autorización de quien administra cada repositorio)

1. **Hacer privado el repositorio.** En GitHub: *Settings → General → Danger Zone → Change repository visibility → Private*. Hay que hacerlo en `Zacatac23/Laboratorio-_10_Dashboard` y en `luispedrolira/lab10-data`. Con la CLI, quien sea dueño puede usar `gh repo edit <dueño>/<repo> --visibility private --accept-visibility-change-consequences`.
2. **Dar acceso solo a docentes y auxiliares.** En *Settings → Collaborators and teams*, agregar sus cuentas con rol *Read*, y retirar a quien no corresponda.
3. **Revisar forks y clones.** En *Insights → Forks*, revisar si hay copias públicas. Cambiar la visibilidad no retira forks ni copias ya descargadas.
4. **Tener en cuenta lo que no cubre `.gitignore`.** Solo evita futuros commits: los CSV y el PDF siguen en todos los commits anteriores. Si la institución exige eliminarlos del historial, se puede reescribir con `git filter-repo --path data/ --path reporte_final_lab10/ --invert-paths`. Esto cambia todos los hashes, obliga a volver a clonar en cada equipo de trabajo y requiere un `push --force`. Hay que acordarlo con el equipo y los docentes antes de hacerlo. GitHub puede conservar vistas en caché: se pide la purga a soporte.
5. **Rotar secretos.** Por ahora no aplica, porque no se encontraron. Si alguna vez se publicó una credencial, revocarla y generar una nueva antes de limpiar el historial.
6. **No publicar el tablero ni los datos** en servicios de hosting. El despliegue de esta entrega es local (puertos en `127.0.0.1`).

## Comandos usados (solo lectura)

```bash
git log --all --name-only --format= | sort -u
git log --all -p | grep -inE "(api[_-]?key|secret|password|token|bearer|aws_|ghp_|github_pat_|BEGIN (RSA|OPENSSH|PRIVATE))"
curl -s -o /dev/null -w "%{http_code}" https://api.github.com/repos/Zacatac23/Laboratorio-_10_Dashboard
curl -s -o /dev/null -w "%{http_code}" https://api.github.com/repos/luispedrolira/lab10-data
```
