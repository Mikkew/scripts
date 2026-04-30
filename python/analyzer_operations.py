#!/usr/bin/env python3
"""
Analizador de duplicados en 'env' de Kubernetes.
Flujo: Extraer Paths -> Solicitar Variables -> Construir Rutas Finales -> Analizar.
"""

import os
import re
import getpass
import time
import requests
import yaml
from collections import defaultdict
from datetime import datetime
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv()  # Carga variables de entorno desde .env

# Deshabilitar warnings de SSL para entornos internos (GitHub Enterprise)
requests.packages.urllib3.disable_warnings()

def get_raw_file(repo_path, branch, owner, repo, token, api_base_url):
    """Descarga un archivo desde GitHub"""
    url = f"{api_base_url}/repos/{owner}/{repo}/contents/{repo_path}"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3.raw",
        "User-Agent": "K8s-Analyzer"
    }
    resp = requests.get(url, headers=headers, params={"ref": branch}, verify=False)
    resp.raise_for_status()
    return resp.text

def extract_repo_info_from_url(url):
    """Extrae owner y repo de la URL del configPath"""
    # Ejemplo URL: https://alm-github.systems.uk.hsbc/acs-mx-system-apis/digital-system-apis-operations-shp
    parsed = urlparse(url.rstrip('/'))
    path_parts = parsed.path.strip('/').split('/')
    
    # Determinar base API (Enterprise vs Public)
    hostname = parsed.hostname
    if hostname == "github.com":
        api_base = "https://api.github.com"
    else:
        api_base = f"https://{hostname}" # Asume GitHub Enterprise standard path
        
    if len(path_parts) >= 2:
        owner, repo = path_parts[-2], path_parts[-1]
        return owner, repo, api_base
    raise ValueError("No se pudo extraer owner/repo de la URL del config")

def parse_config_content(content):
    """
    1. Extrae la URL del repo (configPath)
    2. Extrae la lista de paths (plantillas con ${...})
    """
    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError as e:
        raise ValueError(f"YAML inválido: {e}")

    config_path_url = None
    paths_templates = []

    if isinstance(data, dict):
        # Extraer URL
        if "defaults" in data:
            config_path_url = data["defaults"].get("configPath")
        elif "configPath" in data:
            config_path_url = data["configPath"]

        # Extraer Paths
        if "configuration" in data:
            paths_templates = data["configuration"].get("paths", [])
        elif "paths" in data:
            paths_templates = data["paths"]

    if not config_path_url:
        raise ValueError("No se encontró 'configPath' en el archivo.")
    if not paths_templates:
        raise ValueError("No se encontraron 'paths' en el archivo.")

    return config_path_url, paths_templates

def extract_env_properties(doc):
    """Busca recursivamente la sección 'env' y extrae sus propiedades"""
    envs = {}
    
    def find_env(obj):
        if isinstance(obj, dict):
            if 'env' in obj and isinstance(obj['env'], dict):
                # Validar que sea un mapa plano
                if all(isinstance(v, str) for v in obj['env'].values()):
                    return obj['env']
            for v in obj.values():
                res = find_env(v)
                if res: return res
        elif isinstance(obj, list):
            for item in obj:
                res = find_env(item)
                if res: return res
        return None

    found = find_env(doc)
    if found:
        return {k: str(v) for k, v in found.items()}
    return {}

def analyze_file(content):
    """Parsea el contenido YAML y devuelve las props de env"""
    all_envs = {}
    try:
        docs = yaml.safe_load_all(content)
        for doc in docs:
            if isinstance(doc, dict):
                all_envs.update(extract_env_properties(doc))
    except yaml.YAMLError:
        pass
    return all_envs

def select_logical_environments():
    """Interfaz para elegir ambientes"""
    available = ["sct", "cert0", "cert"]
    print("\n Ambientes lógicos disponibles:")
    for i, e in enumerate(available, 1): print(f"   {i}. {e}")
    print("   4. TODOS")
    print("   5. Selección personalizada")
    
    while True:
        ch = input("\n👉 Opción [1-5, default:4]: ").strip() or "4"
        if ch == "4": return available
        if ch == "5":
            cust = input("   Ambientes (separados por coma): ").strip()
            envs = [e.strip().lower() for e in cust.split(",") if e.strip()]
            if envs: return envs
        elif ch in "123":
            return [available[int(ch)-1]]
        print("   ❌ Opción inválida")

def main():
    print("\n" + "="*60)
    print(" ANALIZADOR DE DUPLICADOS K8s - FLUJO CONSTRUCCIÓN DE PATHS")
    print("="*60)

    try:
        # --- PASO 1: Configuración Inicial ---
        print("\n📂 PASO 1: Ubicar Archivo de Configuración")
        config_path = input("Ruta del archivo [DeployConfigStructure.yaml]: ").strip() or "DeployConfigStructure.yaml"
        branch = input("Rama [main]: ").strip() or "main"
        
        print("\n Token (se usará para leer el config y los archivos)")
        token = os.getenv("GITHUB_TOKEN")
        if not token:
            token = getpass.getpass("Ingresa Token: ").strip()
        if not token: raise ValueError("Token requerido")

        # --- PASO 2: Leer y Extraer Paths ---
        print("\n📥 PASO 2: Leyendo archivo de configuración...")
        # Descargamos temporalmente el config para obtener la URL del repo
        # Nota: Aquí necesitamos owner/repo temporalmente solo para leer el config
        # Si el usuario no los da, intentamos deducir o pedirlos solo para este paso.
        temp_owner = input("Owner del repo (para leer config): ").strip()
        temp_repo = input("Repo Name (para leer config): ").strip()
        
        # Asumimos github.com por defecto para la descarga inicial del config
        # Si es enterprise, el usuario debería indicarlo o el script fallaría aquí si no se ajusta.
        # Para simplificar, asumimos que el config está en el mismo repo enterprise.
        # Pedimos la URL base si es necesario, o asumimos estándar.
        # Vamos a usar una lógica simple: si el config_path no empieza con http, usamos la API de github standard
        # Pero dado que el config tiene una URL completa, lo mejor es pedir la URL base del API si es Enterprise.
        
        api_base_temp = "https://api.github.com"
        if "systems.uk.hsbc" in config_path: # Detección básica de Enterprise de la imagen
            print("⚠️ Detectado entorno Enterprise. Asegúrate de que el token sea válido para él.")
            # El usuario debe tener el token válido. 
            # Para descargar el config necesitamos saber dónde está.
            # Asumiremos que el owner/repo temporal es correcto para la API base por defecto 
            # O pedimos la URL base del API Enterprise.
            api_base_temp = "https://alm-github.systems.uk.hsbc" 
        
        config_content = get_raw_file(config_path, branch, temp_owner, temp_repo, token, api_base_temp)
        
        config_url, paths_templates = parse_config_content(config_content)
        owner, repo, api_base_final = extract_repo_info_from_url(config_url)
        
        print(f"✅ Config leído correctamente.")
        print(f"✅ Repositorio destino: {config_url}")
        
        print("\n📜 Paths extraídos (Plantillas):")
        for p in paths_templates:
            print(f"   • {p}")

        # --- PASO 3: Solicitar Variables ---
        print("\n⚙️ PASO 3: Ingresar Valores para Construir Paths")
        print("-" * 40)
        physical_env = input("physicalEnvironment: ").strip()
        ops_folder = input("opsrepo_folder: ").strip()
        
        if not physical_env or not ops_folder:
            raise ValueError("Ambos valores son obligatorios.")

        logical_envs = select_logical_environments()

        # --- PASO 4: Construcción de Paths Finales ---
        print("\n PASO 4: Construyendo Paths Finales...")
        final_paths_by_env = {} # { 'sct': [path1, path2...], 'cert': [...] }
        
        total_paths_to_download = 0

        for env in logical_envs:
            resolved_paths = []
            for template in paths_templates:
                # Sustitución
                path = template.replace("${physicalEnvironment}", physical_env)
                path = path.replace("${opsrepo_folder}", ops_folder)
                path = path.replace("${logicalEnvironment}", env)
                
                # Limpieza
                path = re.sub(r'/+', '/', path).lstrip('/')
                resolved_paths.append(path)
            
            final_paths_by_env[env] = resolved_paths
            total_paths_to_download += len(resolved_paths)
            print(f"   📦 Ambiente '{env}': {len(resolved_paths)} paths generados.")

        print(f"\n🚀 Total de archivos a descargar: {total_paths_to_download}")

        # --- PASO 5: Análisis y Reporte ---
        print("\n🔍 PASO 5: Descargando y Analizando duplicados...")
        all_results = {}
        
        for env, paths in final_paths_by_env.items():
            print(f"\n--- Analizando Ambiente: {env.upper()} ---")
            env_dups = {}
            
            # Mapa global para este ambiente: clave -> [valores]
            keys_found = defaultdict(list)

            for i, path in enumerate(paths):
                try:
                    print(f"   [{i+1}/{len(paths)}] Descargando: {path}")
                    content = get_raw_file(path, branch, owner, repo, token, api_base_final)
                    props = analyze_file(content)
                    
                    # Guardar para buscar duplicados
                    for k, v in props.items():
                        keys_found[k].append({
                            "file": path,
                            "value": v
                        })
                    time.sleep(0.1)
                except Exception as e:
                    print(f"   ⚠️ Error en {path}: {e}")

            # Detectar duplicados en este ambiente
            for k, occurrences in keys_found.items():
                if len(occurrences) > 1:
                    values = set(o['value'] for o in occurrences)
                    env_dups[k] = {
                        "total": len(occurrences),
                        "identical": len(values) == 1,
                        "occurrences": occurrences
                    }
            
            all_results[env] = env_dups

        # --- Generar Reporte ---
        generate_report(all_results, config_url, branch, physical_env, ops_folder, logical_envs)

    except Exception as e:
        print(f"\n❌ ERROR: {e}")

def generate_report(results, repo_url, branch, phys, ops, envs):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    filename = f"reporte_duplicados_{datetime.now().strftime('%Y%m%d')}.txt"
    
    with open(filename, "w", encoding="utf-8") as f:
        f.write("="*80 + "\n")
        f.write("REPORTE DE DUPLICADOS EN PROPIEDADES 'env'\n")
        f.write(f"Generado: {timestamp}\n")
        f.write(f"Repo: {repo_url}\n")
        f.write("="*80 + "\n\n")

        for env in envs:
            dups = results.get(env, {})
            f.write(f"[AMBIENTE: {env.upper()}]\n")
            if not dups:
                f.write("   ✅ No se encontraron duplicados.\n\n")
            else:
                f.write(f"   🔍 Se encontraron {len(dups)} claves duplicadas:\n")
                for key, info in dups.items():
                    status = "IDÉNTICO" if info["identical"] else "DISTINTO"
                    f.write(f"\n   🔑 {key} [{status}]\n")
                    for occ in info["occurrences"]:
                        # Truncar valor largo
                        val = str(occ["value"])
                        if len(val) > 50: val = val[:47] + "..."
                        f.write(f"      📄 {occ['file']} -> {val}\n")
            f.write("-"*40 + "\n")

    print(f"\n✅ Reporte guardado en: {filename}")

if __name__ == "__main__":
    main()