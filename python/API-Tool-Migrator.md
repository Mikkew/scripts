# API-Tool-Migrator

> **Convertidor bidireccional entre Insomnia y Postman + Conversor de Versiones Insomnia**

[![Python](https://img.shields.io/badge/Python-3.7+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Status](https://img.shields.io/badge/Status-Stable-brightgreen.svg)]()

---

## Descripción

**API-Tool-Migrator** es una suite de herramientas desarrollada en Python que permite:

1. **Convertir colecciones entre Insomnia y Postman** (bidireccional)
2. **Transformar exportaciones de Insomnia v5 (YAML) a Insomnia v4 (JSON)**

Ideal para equipos que necesitan migrar entre herramientas, colaborar usando diferentes plataformas, o mantener compatibilidad entre versiones de Insomnia.

---

## Estructura del Proyecto

```API-Tool-Migrator/
├── README.md                   # Documentación principal (este archivo)
├── Pipfile                     # Para usuarios con pipenv
├── Pipfile.lock                # Versiones bloqueadas (autogenerado)
├── .gitignore                  # Archivos a ignorar en Git
│── insomnia_to_postman.py      # Convierte Insomnia → Postman
│── postman_to_insomnia.py      # Convierte Postman → Insomnia
│── converter_insomnia.py       # Convierte Insomnia v5 (YAML) → v4 (JSON)
├── in/
│ └── (archivos de entrada para transformar)
└── out/
└── (archivos de salida transformados)
```


---

## Descripción de Archivos Python

### Scripts Principales

| Archivo | Propósito | Entrada | Salida |
|---------|-----------|---------|--------|
| `insomnia_to_postman.py` | Convierte exportaciones de Insomnia v4/v5 (JSON) a Colección de Postman v2.1 | Insomnia JSON | Postman JSON |
| `postman_to_insomnia.py` | Convierte Colecciones de Postman v2.1 a Insomnia v4/v5 (JSON) | Postman JSON | Insomnia JSON |
| `converter_insomnia.py` | Convierte exportaciones de Insomnia v5 (YAML) a Insomnia v4 (JSON) | Insomnia v5 YAML | Insomnia v4 JSON |
---

### Detalle de Cada Script

| Script | Funcionalidades Principales | Casos de Uso |
|--------|---------------------------|----------------|
| `insomnia_to_postman.py` | • Requests (todos los métodos HTTP)<br>• Headers y Body (JSON, form-data, XML)<br>• Autenticación (Basic, Bearer, API Key, OAuth2)<br>• Carpetas (Request Groups → Folders)<br>• Variables de entorno | • Migrar de Insomnia a Postman<br>• Compartir colecciones con equipos que usan Postman<br>• Backup en formato universal |
| `postman_to_insomnia.py` | • Todos los métodos HTTP<br>• Headers y Body en todos los formatos<br>• Autenticación de Postman a Insomnia<br>• Carpetas (Folders → Request Groups)<br>• Variables a Environment | • Migrar de Postman a Insomnia<br>• Unificar equipos en Insomnia<br>• Aprovechar features de Insomnia |
| `converter_insomnia.py` | • Convierte formato YAML a JSON<br>• Mantiene estructura de Insomnia<br>• Preserva todos los campos<br>• Validación de archivo de entrada | • Downgrade de Insomnia v5 a v4<br>• Compatibilidad con versiones antiguas<br>• Convertir exportaciones YAML a JSON |

---

## Carpetas de Entrada y Salida

### `in/` - Archivos de Entrada

| Propósito | Contenido |
|-----------|-----------|
| Almacenar archivos originales para convertir | • Exportaciones de Insomnia (JSON/YAML)<br>• Colecciones de Postman (JSON) |

**Archivos soportados:**
- `<ARTIFACT_NAME>.insomnia_collection.json` (Insomnia v4/v5 JSON)
- `<ARTIFACT_NAME>.insomnia_collection.yaml` (Insomnia v5 YAML)
- `<ARTIFACT_NAME>.postman_collection.json` (Postman v2.1)

### `out/` - Archivos de Salida

| Propósito | Contenido |
|-----------|-----------|
| Almacenar archivos convertidos | • Colecciones convertidas listas para importar |

**Archivos generados:**
- `postman_collection.json` (desde Insomnia)
- `insomnia_export.json` (desde Postman)
- `insomnia_v4.json` (desde Insomnia v5 YAML)

---

## Conversión de Versiones de Insomnia

### `converter_insomnia.py`

Este script es esencial cuando necesitas **compatibilidad hacia atrás** entre versiones de Insomnia.

| Característica | Detalle |
|---------------|---------|
| **Propósito** | Convertir exportaciones de Insomnia v5 (YAML) a Insomnia v4 (JSON) |
| **Entrada** | Archivo `.yaml` exportado desde Insomnia v5 |
| **Salida** | Archivo `.json` compatible con Insomnia v4 |
| **Dependencias** | `pyyaml` (para leer YAML) |
| **Complejidad** | Baja (solo cambio de formato de serialización) |

### Consideraciones Importantes

| Aspecto | Descripción |
|---------|-------------|
| **Formato vs Esquema** | El script convierte YAML → JSON, pero campos nuevos de v5 pueden no ser compatibles con v4 |
| **Campos Nuevos** | Si usas features exclusivas de v5, v4 podría ignorarlos o fallar al importar |
| **Validación** | Siempre prueba la importación en Insomnia v4 después de convertir |
| **Backup** | Mantén una copia del archivo original YAML antes de convertir |

### Flujo de Conversión v5 → v4
```text
┌─────────────────┐      ┌──────────────────┐      ┌─────────────────┐
│  Insomnia v5    │      │  converter_      │      │  Insomnia v4    │
│  Export (YAML)  │ ───► │  insomnia.py     │ ───► │  Import (JSON)  │
│                 │      │                  │      │                 │
└─────────────────┘      └──────────────────┘      └─────────────────┘
```

### Uso del Script v5 → v4

```bash
python converter_insomnia.py
```

### Proceso interactivo:
    - Ingresa la ruta del archivo YAML de Insomnia v5 (desde in/)
    - Ingresa la ruta de salida para el JSON de Insomnia v4 (hacia out/)
    - El script valida, convierte y guarda el archivo
    - Importa el JSON resultante en Insomnia v4

---

## Instalación

### Requisitos Previos

- Python 3.7 o superior
- pip (gestor de paquetes de Python)

### Pasos de Instalación

```bash
# 1. Clonar el repositorio
git clone https://github.com/tu-usuario/API-Tool-Migrator.git
cd API-Tool-Migrator

# 2. Crear entorno virtual
python -m venv .venv

# 3. Activar entorno virtual

# En Windows (CMD)
.venv\Scripts\activate

# En Windows (PowerShell)
.venv\Scripts\Activate.ps1

# En Linux/Mac
source .venv/bin/activate

# 4. Verificar que el entorno está activado
# Deberías ver (.venv) al inicio de tu línea de comandos

# 5. Actualizar pip
pip install --upgrade pip

# 6. Verificar versión de pip
pip --version

# 7. Actualizar pip y setuptools
pip install --upgrade pip setuptools

# 9. Instalar dependencias con pipenv (usa el sistema activo)
pip install pipenv && pipenv install --system

# 10. Verificar instalación
python --version
pip --version
```

### Desactivar Entorno Virtual
```bash
# Cuando termines de usar el proyecto, desactiva el entorno
deactivate
```

### Verificar Instalación
```bash
# Ejecutar un script de prueba
python converter_insomnia.py --help

# O verificar que pyyaml está instalado
python -c "import yaml; print('YAML instalado correctamente')"
```

## Notas Importantes
|Aspecto|Detalle|
|---------------|---------|
|Entorno Aislado|Las dependencias se instalan en .venv/, no afectan tu sistema|
|Activación Requerida| Debes activar el venv antes de ejecutar los scripts|
|Indicador Visual| Verás (.venv) al inicio de tu terminal cuando esté activado|
|Pipenv --system| Instala las dependencias del Pipfile en el entorno virtual activo|
|Carpeta .venv|No se commitea a Git (está en .gitignore)|