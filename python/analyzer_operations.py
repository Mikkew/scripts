#!/usr/bin/env python3
"""
Analizador de duplicados en 'env' de Kubernetes.
Extrae automáticamente server/org/repo del configPath
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

# Deshabilitar warnings de SSL
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

def parse_github_url(config_path_url):
    """
    Extrae información completa de la URL del configPath
    Formato: https://server/organization/repo
    Ejemplo: https://alm-github.systems.uk.hsbc/acs-mx-system-apis/digital-system-apis-operations-shp
    """
    config_path_url = config_path_url.rstrip('/')
    parsed = urlparse(config_path_url)
    
    # Extraer servidor
    server = parsed.hostname  # ej: alm-github.systems.uk.hsbc
    
    # Extraer organización y repo del path
    path_parts = parsed.path.strip('/').split('/')
    
    if len(path_parts) >= 2:
        org = path_parts[0]  # ej: acs-mx-system-apis
        repo = path_parts[1]  # ej: digital-system-apis-operations-shp
    else:
        raise ValueError(f"URL inválida. Se espera: https://server/org/repo. Recibido: {config_path_url}")
    
    # Determinar API base
    if server == "github.com":
        api_base = "https://api.github.com"
    else:
        # GitHub Enterprise
        api_base = f"https://{server}"
    
    return {
        "url": config_path_url,
        "server": server,
        "org": org,
        "repo": repo,
        "api_base": api_base
    }

def parse_config_content(content):
    """Extrae configPath y paths del YAML"""
    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError as e:
        raise ValueError(f"YAML inválido: {e}")

    config_path_url = None
    paths_templates = []

    if isinstance(data, dict):
        # Extraer configPath
        if "defaults" in data:
            config_path_url = data["defaults"].get("configPath")
        elif "configPath" in data:
            config_path_url = data["configPath"]

        # Extraer paths
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
    """Busca recursivamente la sección 'env'"""
    envs = {}
    
    def find_env(obj):
        if isinstance(obj, dict):
            if 'env' in obj and isinstance(obj['env'], dict):
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
    """Parsea YAML y extrae props de env"""
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
    """Selección de ambientes"""
    available = ["sct", "cert0", "cert"]
    print("\n Ambientes lógicos disponibles:")
    for i, e in enumerate(available, 1): 
        print(f"   {i}. {e}")
    print("   4. TODOS")
    print("   5. Selección personalizada")
    
    while True:
        ch = input("\n👉 Opción [1-5, default:4]: ").strip() or "4"
        if ch == "4": 
            return available
        if ch == "5":
            cust = input("   Ambientes (separados por coma): ").strip()
            envs = [e.strip().lower() for e in cust.split(",") if e.strip()]
            if envs: 
                return envs
        elif ch in "123":
            return [available[int(ch)-1]]
        print("   ❌ Opción inválida")

def main():
    print("\n" + "="*70)
    print(" ANALIZADOR DE DUPLICADOS K8s - EXTRACCIÓN AUTOMÁTICA DE REPO")
    print("="*70)

    try:
        # --- PASO 1: Ubicación del archivo de configuración ---
        print("\n📂 PASO 1: Archivo de Configuración")
        config_path = input("Ruta del archivo [DeployConfigStructure.yaml]: ").strip() or "DeployConfigStructure.yaml"
        branch = input("Rama [main]: ").strip() or "main"
        
        # --- PASO 2: Token ---
        print("\n🔑 Autenticación")
        token = os.getenv("GITHUB_TOKEN")
        if not token:
            print("⚠️  GITHUB_TOKEN no encontrado en variables de entorno")
            token = getpass.getpass("Ingresa tu Personal Access Token: ").strip()
        else:
            print("✅ Token detectado desde variable de entorno")
        
        if not token:
            raise ValueError("Se requiere un token válido")

        # --- PASO 3: Descargar y parsear configuración ---
        print("\n📥 PASO 2: Leyendo configuración...")
        print("   Nota: Para descargar el archivo config, necesitamos saber dónde está.")
        print("   Si el archivo está en GitHub.com, deja vacío el servidor.")
        
        temp_server = input("   Servidor temporal para descargar config [github.com]: ").strip() or "github.com"
        temp_owner = input("   Owner temporal: ").strip()
        temp_repo = input("   Repo temporal: ").strip()
        
        if temp_server == "github.com":
            temp_api_base = "https://api.github.com"
        else:
            temp_api_base = f"https://{temp_server}"
        
        # Descargar archivo de configuración
        config_content = get_raw_file(config_path, branch, temp_owner, temp_repo, token, temp_api_base)
        
        # Parsear para obtener configPath y paths
        config_url, paths_templates = parse_config_content(config_content)
        
        # Extraer información completa del repositorio DESTINO desde configPath
        repo_info = parse_github_url(config_url)
        
        print(f"\n✅ Configuración cargada exitosamente")
        print(f"\n📊 Información del Repositorio (extraída de configPath):")
        print(f"   🌐 Servidor   : {repo_info['server']}")
        print(f"   📁 Organización: {repo_info['org']}")
        print(f"   📦 Repositorio : {repo_info['repo']}")
        print(f"   🔗 API Base   : {repo_info['api_base']}")
        
        print(f"\n📜 Paths encontrados ({len(paths_templates)}):")
        for i, p in enumerate(paths_templates, 1):
            print(f"   {i}. {p}")

        # --- PASO 4: Parámetros de resolución ---
        print("\n⚙️  PASO 3: Parámetros para Construir Paths")
        print("-" * 70)
        physical_env = input("physicalEnvironment: ").strip()
        ops_folder = input("opsrepo_folder: ").strip()
        
        if not physical_env or not ops_folder:
            raise ValueError("Ambos parámetros son obligatorios")

        # --- PASO 5: Selección de ambientes ---
        print("\n🌍 PASO 4: Ambientes Lógicos")
        print("-" * 70)
        logical_envs = select_logical_environments()
        print(f"\n✅ Ambientes seleccionados: {', '.join(logical_envs)}")

        # --- PASO 6: Construcción de paths ---
        print("\n🔨 PASO 5: Construyendo Paths Finales...")
        print("-" * 70)
        
        final_paths_by_env = {}
        total_files = 0
        
        for env in logical_envs:
            resolved = []
            for template in paths_templates:
                path = template.replace("${physicalEnvironment}", physical_env)
                path = path.replace("${opsrepo_folder}", ops_folder)
                path = path.replace("${logicalEnvironment}", env)
                path = re.sub(r'/+', '/', path).lstrip('/')
                resolved.append(path)
            
            final_paths_by_env[env] = resolved
            total_files += len(resolved)
            print(f"   📦 {env.upper()}: {len(resolved)} archivos")
        
        print(f"\n📊 Total de archivos a descargar: {total_files}")

        # --- PASO 7: Análisis ---
        print("\n🔍 PASO 6: Analizando archivos...")
        print("="*70)
        
        all_results = {}
        
        for env in logical_envs:
            print(f"\n{'='*70}")
            print(f"Analizando ambiente: {env.upper()}")
            print(f"{'='*70}")
            
            paths = final_paths_by_env[env]
            keys_found = defaultdict(list)
            success = 0
            failed = 0
            
            for i, path in enumerate(paths, 1):
                try:
                    print(f"   [{i}/{len(paths)}] {path}")
                    content = get_raw_file(path, branch, repo_info['org'], repo_info['repo'], token, repo_info['api_base'])
                    props = analyze_file(content)
                    
                    for k, v in props.items():
                        keys_found[k].append({
                            "file": path,
                            "value": v
                        })
                    success += 1
                    time.sleep(0.15)
                    
                except requests.exceptions.HTTPError as e:
                    if e.response.status_code == 404:
                        print(f"         ⚠️  No encontrado (404)")
                    else:
                        print(f"         ❌ Error HTTP {e.response.status_code}")
                    failed += 1
                except Exception as e:
                    print(f"         ❌ Error: {type(e).__name__}")
                    failed += 1
            
            print(f"\n   📊 Resumen: {success} exitosos, {failed} fallidos")
            
            # Detectar duplicados
            duplicates = {}
            for key, occurrences in keys_found.items():
                if len(occurrences) > 1:
                    values = set(o['value'] for o in occurrences)
                    duplicates[key] = {
                        "total": len(occurrences),
                        "identical": len(values) == 1,
                        "occurrences": occurrences
                    }
            
            all_results[env] = duplicates
            print(f"   🔍 Variables duplicadas encontradas: {len(duplicates)}")

        # --- PASO 8: Generar Reporte ---
        print("\n" + "="*70)
        print("📊 PASO 7: Generando Reporte...")
        print("="*70)
        
        generate_report(all_results, repo_info, branch, physical_env, ops_folder, logical_envs)

    except KeyboardInterrupt:
        print("\n\n⚠️  Proceso cancelado por el usuario")
    except Exception as e:
        print(f"\n❌ ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

def generate_report(results, repo_info, branch, phys, ops, envs):
    """Genera archivo de reporte"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    filename = f"reporte_duplicados_{repo_info['repo']}_{datetime.now().strftime('%Y%m%d_%H%M')}.txt"
    
    with open(filename, "w", encoding="utf-8") as f:
        f.write("="*90 + "\n")
        f.write("REPORTE DE VARIABLES DUPLICADAS EN SECCIÓN 'env' - KUBERNETES\n")
        f.write("="*90 + "\n")
        f.write(f"Generado        : {timestamp}\n")
        f.write(f"Servidor        : {repo_info['server']}\n")
        f.write(f"Organización    : {repo_info['org']}\n")
        f.write(f"Repositorio     : {repo_info['repo']}\n")
        f.write(f"Rama            : {branch}\n")
        f.write(f"Physical Env    : {phys}\n")
        f.write(f"Ops Folder      : {ops}\n")
        f.write(f"Ambientes       : {', '.join(envs)}\n")
        f.write("="*90 + "\n\n")

        total_dups = 0
        
        for env in envs:
            dups = results.get(env, {})
            total_dups += len(dups)
            
            f.write("╔" + "═"*88 + "╗\n")
            f.write(f"║  AMBIENTE: {env.upper():<76} ║\n")
            f.write("╚" + "═"*88 + "╝\n\n")
            
            if not dups:
                f.write("  ✅ NO SE ENCONTRARON VARIABLES DUPLICADAS\n\n")
            else:
                f.write(f"  📊 Total de variables duplicadas: {len(dups)}\n\n")
                f.write("  📋 LISTA DE VARIABLES:\n")
                f.write("  " + "-"*86 + "\n")
                
                sorted_dups = sorted(dups.items(), key=lambda x: x[1]["total"], reverse=True)
                
                for idx, (key, info) in enumerate(sorted_dups, 1):
                    status = "🟢 IDÉNTICOS" if info["identical"] else "🔴 DIFERENTES"
                    f.write(f"\n  {idx}. {key}\n")
                    f.write(f"     Estado: {status}\n")
                    f.write(f"     Repetida en {info['total']} archivos\n")
                    f.write(f"     Valores:\n")
                    
                    for occ in info["occurrences"]:
                        val = str(occ["value"])
                        if len(val) > 70:
                            val = val[:67] + "..."
                        f.write(f"       • {os.path.basename(occ['file'])}: {val}\n")
                    
                    f.write("\n  " + "-"*86)
            
            f.write("\n\n" + "="*90 + "\n")

        # Resumen final
        f.write("\n╔" + "═"*88 + "╗\n")
        f.write(f"║  RESUMEN GENERAL{' '*71} ║\n")
        f.write("╚" + "═"*88 + "╝\n\n")
        f.write(f"  Total de variables duplicadas: {total_dups}\n")
        f.write(f"  Ambientes analizados: {len(envs)}\n\n")
        
        f.write("  DESGLOSE POR AMBIENTE:\n")
        f.write("  " + "-"*86 + "\n")
        f.write(f"  {'Ambiente':<15} {'Variables Duplicadas':<25} {'Estado'}\n")
        f.write("  " + "-"*86 + "\n")
        
        for env in envs:
            count = len(results.get(env, {}))
            status = "⚠️  Con duplicados" if count > 0 else "✅ Sin duplicados"
            f.write(f"  {env.upper():<15} {count:<25} {status}\n")
        
        f.write("  " + "-"*86 + "\n\n")
        f.write("FIN DEL REPORTE\n")
        f.write("="*90 + "\n")
    
    print(f"\n💾 Reporte guardado: {filename}")
    print(f"\n✅ Análisis completado. Se encontraron {total_dups} variables duplicadas en total.")

if __name__ == "__main__":
    main()