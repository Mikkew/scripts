#!/usr/bin/env python3
"""
Analizador de duplicados en variables de entorno Kubernetes.
Lee archivo local y extrae configPath para construir URLs correctamente.
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
import pathlib
from dotenv import load_dotenv

load_dotenv()  # Carga variables de entorno desde .env

# Deshabilitar warnings de SSL
requests.packages.urllib3.disable_warnings()

def parse_github_url(config_path_url):
    """
    Extrae server, owner y repo del configPath
    Ej: https://alm-github.systems.uk.hsbc/acs-mx-system-apis/digital-system-apis-operations-shp
    """
    config_path_url = config_path_url.rstrip('/')
    parsed = urlparse(config_path_url)
    
    server = f"{parsed.scheme}://{parsed.hostname}"  # https://alm-github.systems.uk.hsbc
    path_parts = parsed.path.strip('/').split('/')
    
    if len(path_parts) >= 2:
        owner = path_parts[0]  # acs-mx-system-apis
        repo = path_parts[1]   # digital-system-apis-operations-shp
    else:
        raise ValueError(f"URL inválida: {config_path_url}")
    
    return {
        "url": config_path_url,
        "server": server,
        "owner": owner,
        "repo": repo
    }

def get_raw_file_url(server, owner, repo, branch, file_path):
    """
    Construye URL raw para GitHub Enterprise
    Formato: {server}/raw/{owner}/{repo}/refs/heads/{branch}/{file_path}
    """
    # Asegurar que file_path no tenga backslashes
    file_path = file_path.replace('\\', '/')
    return f"{server}/raw/{owner}/{repo}/refs/heads/{branch}/{file_path}"

def download_file(url, token):
    """Descarga archivo desde URL raw"""
    headers = {
        "Authorization": f"token {token}",
        "User-Agent": "K8s-Analyzer"
    }
    resp = requests.get(url, headers=headers, verify=False)
    resp.raise_for_status()
    return resp.text

def read_local_file(file_path):
    """Lee un archivo local"""
    with open(file_path, 'r', encoding='utf-8') as f:
        return f.read()

def parse_config_content(content):
    """Extrae configPath y paths del YAML"""
    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError as e:
        raise ValueError(f"YAML inválido: {e}")

    config_path_url = None
    paths_templates = []

    if isinstance(data, dict):
        if "defaults" in 
            config_path_url = data["defaults"].get("configPath")
        elif "configPath" in 
            config_path_url = data["configPath"]

        if "configuration" in 
            paths_templates = data["configuration"].get("paths", [])
        elif "paths" in 
            paths_templates = data["paths"]

    if not config_path_url:
        raise ValueError("No se encontró 'configPath'")
    if not paths_templates:
        raise ValueError("No se encontraron 'paths'")

    return config_path_url, paths_templates

def extract_env_from_kubernetes_deployment(doc):
    """Extrae propiedades de kubernetes.deployment.env"""
    envs = {}
    
    def find_kubernetes_env(obj):
        if isinstance(obj, dict):
            if 'kubernetes' in obj and isinstance(obj['kubernetes'], dict):
                k8s = obj['kubernetes']
                if 'deployment' in k8s and isinstance(k8s['deployment'], dict):
                    deploy = k8s['deployment']
                    if 'env' in deploy and isinstance(deploy['env'], dict):
                        return deploy['env']
            
            for v in obj.values():
                res = find_kubernetes_env(v)
                if res: 
                    return res
        elif isinstance(obj, list):
            for item in obj:
                res = find_kubernetes_env(item)
                if res: 
                    return res
        return None

    found = find_kubernetes_env(doc)
    if found:
        return {str(k): str(v) for k, v in found.items()}
    return {}

def analyze_file(content):
    """Parsea YAML y extrae env de kubernetes.deployment"""
    all_envs = {}
    try:
        docs = yaml.safe_load_all(content)
        for doc in docs:
            if isinstance(doc, dict):
                all_envs.update(extract_env_from_kubernetes_deployment(doc))
    except yaml.YAMLError:
        pass
    return all_envs

def select_logical_environments():
    """Selección de ambientes lógicos"""
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
            cust = input("   Ambientes (separados por coma, ej: sct,cert0): ").strip()
            envs = [e.strip().lower() for e in cust.split(",") if e.strip()]
            if envs: 
                return envs
            print("   ⚠️  Ingresa al menos un ambiente válido")
        elif ch in "123":
            return [available[int(ch)-1]]
        print("   ❌ Opción inválida")

def main():
    print("\n" + "="*80)
    print(" ANALIZADOR DE DUPLICADOS - KUBERNETES DEPLOYMENT ENV")
    print("="*80)

    try:
        # ========== PASO 1: Archivo de configuración LOCAL ==========
        print("\n📂 PASO 1: Archivo DeployConfigStructure.yaml")
        print("-" * 80)
        config_path_input = input("Ruta del archivo local [DeployConfigStructure.yaml]: ").strip()
        
        if not config_path_input:
            config_path_input = "DeployConfigStructure.yaml"
        
        # Verificar si es un archivo local
        if os.path.exists(config_path_input):
            print(f"✅ Archivo local encontrado: {config_path_input}")
            config_content = read_local_file(config_path_input)
        else:
            raise FileNotFoundError(f"No se encontró el archivo: {config_path_input}")
        
        # ========== PASO 2: Rama ==========
        branch = input("Rama del repositorio: ").strip()
        if not branch:
            raise ValueError("La rama es obligatoria")
        
        # ========== PASO 3: Token ==========
        print("\n🔑 PASO 2: Autenticación")
        print("-" * 80)
        token = os.getenv("GITHUB_TOKEN")
        if not token:
            print("⚠️  GITHUB_TOKEN no encontrado en variables de entorno")
            token = getpass.getpass("Ingresa tu Personal Access Token: ").strip()
        else:
            print("✅ Token detectado desde variable de entorno")
        
        if not token:
            raise ValueError("Se requiere un token válido")

        # ========== Parsear configPath y paths del archivo LOCAL ==========
        config_url, paths_templates = parse_config_content(config_content)
        repo_info = parse_github_url(config_url)
        
        print(f"\n📊 Información del Repositorio (extraída de configPath):")
        print(f"   Server : {repo_info['server']}")
        print(f"   Owner  : {repo_info['owner']}")
        print(f"   Repo   : {repo_info['repo']}")
        
        print(f"\n📜 Paths templates encontrados ({len(paths_templates)}):")
        for p in paths_templates:
            print(f"   • {p}")

        # ========== PASO 4: Parámetros ==========
        print("\n⚙️  PASO 3: Parámetros de Construcción")
        print("-" * 80)
        physical_env = input("physicalEnvironment: ").strip()
        ops_folder = input("opsrepo_folder: ").strip()
        
        if not physical_env or not ops_folder:
            raise ValueError("Ambos parámetros son obligatorios")

        # ========== Selección de ambientes ==========
        print("\n🌍 Ambientes Lógicos")
        print("-" * 80)
        logical_envs = select_logical_environments()
        print(f"\n✅ Ambientes seleccionados: {', '.join(logical_envs)}")

        # ========== PASO 5: Construcción de paths ==========
        print("\n🔨 PASO 4: Construyendo Paths Finales")
        print("-" * 80)
        
        final_paths_by_env = {}
        
        for env in logical_envs:
            resolved = []
            for template in paths_templates:
                path = template.replace("${physicalEnvironment}", physical_env)
                path = path.replace("${opsrepo_folder}", ops_folder)
                path = path.replace("${logicalEnvironment}", env)
                path = re.sub(r'/+', '/', path).lstrip('/')
                resolved.append(path)
            final_paths_by_env[env] = resolved

        # ========== Mostrar estructura de paths ==========
        print("\n📋 ESTRUCTURA DE PATHS GENERADA:")
        print("-" * 80)
        for env in logical_envs:
            print(f"  {env}:")
            for path in final_paths_by_env[env]:
                print(f"    - {path}")

        # ========== Mostrar URLs raw ==========
        print("\n🔗 URLS RAW PARA CONSULTA:")
        print("-" * 80)
        for env in logical_envs:
            print(f"  {env}:")
            for path in final_paths_by_env[env]:
                raw_url = get_raw_file_url(
                    repo_info['server'],
                    repo_info['owner'],
                    repo_info['repo'],
                    branch,
                    path
                )
                print(f"    - {raw_url}")

        # ========== PASO 6: Análisis ==========
        print("\n🔍 PASO 5: Descargando y Analizando Archivos")
        print("="*80)
        
        all_results = {}
        total_files = sum(len(paths) for paths in final_paths_by_env.values())
        current_file = 0
        
        for env in logical_envs:
            print(f"\n{'='*80}")
            print(f"Analizando ambiente: {env.upper()}")
            print(f"{'='*80}")
            
            paths = final_paths_by_env[env]
            keys_found = defaultdict(list)
            success = 0
            failed = 0
            
            for path in paths:
                current_file += 1
                raw_url = get_raw_file_url(
                    repo_info['server'],
                    repo_info['owner'],
                    repo_info['repo'],
                    branch,
                    path
                )
                
                try:
                    print(f"\n   [{current_file}/{total_files}] {os.path.basename(path)}")
                    print(f"       URL: {raw_url}")
                    
                    content = download_file(raw_url, token)
                    props = analyze_file(content)
                    
                    if props:
                        print(f"       ✅ {len(props)} variables encontradas en kubernetes.deployment.env")
                        for k, v in props.items():
                            keys_found[k].append({
                                "file": path,
                                "value": v,
                                "url": raw_url
                            })
                        success += 1
                    else:
                        print(f"       ⚠️  No se encontró kubernetes.deployment.env")
                        success += 1
                    
                    time.sleep(0.2)
                    
                except requests.exceptions.HTTPError as e:
                    print(f"       ❌ Error HTTP {e.response.status_code}")
                    failed += 1
                except Exception as e:
                    print(f"       ❌ Error: {type(e).__name__}: {str(e)[:50]}")
                    failed += 1
            
            print(f"\n   📊 Resumen {env.upper()}: {success} exitosos, {failed} fallidos")
            
            # Detectar duplicados
            duplicates = {}
            for key, occurrences in keys_found.items():
                if len(occurrences) > 1:
                    values = set(o['value'] for o in occurrences)
                    duplicates[key] = {
                        "key": key,
                        "total": len(occurrences),
                        "identical": len(values) == 1,
                        "occurrences": occurrences
                    }
            
            all_results[env] = duplicates
            print(f"   🔍 Variables duplicadas encontradas: {len(duplicates)}")

        # ========== PASO 7: Generar Reporte ==========
        print("\n" + "="*80)
        print("📊 PASO 6: Generando Reporte")
        print("="*80)
        
        generate_report(all_results, repo_info, branch, physical_env, ops_folder, logical_envs)

    except KeyboardInterrupt:
        print("\n\n⚠️  Proceso cancelado por el usuario")
    except FileNotFoundError as e:
        print(f"\n❌ ERROR: {e}")
        print("   → Verifica que la ruta del archivo sea correcta")
    except Exception as e:
        print(f"\n❌ ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

def generate_report(results, repo_info, branch, phys, ops, envs):
    """Genera archivo de reporte TXT"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    filename = f"reporte_duplicados_{repo_info['repo']}_{datetime.now().strftime('%Y%m%d_%H%M')}.txt"
    
    with open(filename, "w", encoding="utf-8") as f:
        f.write("="*90 + "\n")
        f.write("REPORTE DE DUPLICADOS - KUBERNETES.DEPLOYMENT.ENV\n")
        f.write("="*90 + "\n")
        f.write(f"Generado        : {timestamp}\n")
        f.write(f"Server          : {repo_info['server']}\n")
        f.write(f"Owner           : {repo_info['owner']}\n")
        f.write(f"Repo            : {repo_info['repo']}\n")
        f.write(f"Branch          : {branch}\n")
        f.write(f"Physical Env    : {phys}\n")
        f.write(f"Ops Folder      : {ops}\n")
        f.write(f"Ambientes       : {', '.join(envs)}\n")
        f.write("Sección analizada: kubernetes.deployment.env\n")
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
                
                sorted_dups = sorted(dups.items(), key=lambda x: x[1]["total"], reverse=True)
                
                for idx, (key, info) in enumerate(sorted_dups, 1):
                    status_icon = "🟢" if info["identical"] else "🔴"
                    status_text = "VALORES IDÉNTICOS" if info["identical"] else "VALORES DIFERENTES"
                    
                    f.write(f"  {idx}. {key}\n")
                    f.write(f"     {status_icon} {status_text}\n")
                    f.write(f"     📈 Repetida en {info['total']} archivos\n\n")
                    f.write(f"     UBICACIÓN Y VALORES:\n")
                    
                    for occ in info["occurrences"]:
                        val = str(occ["value"])
                        if len(val) > 70:
                            display_val = val[:67] + "..."
                        else:
                            display_val = val
                        
                        f.write(f"       • Archivo: {os.path.basename(occ['file'])}\n")
                        f.write(f"         Path   : {occ['file']}\n")
                        f.write(f"         Valor  : {display_val}\n")
                        f.write(f"         URL    : {occ['url']}\n")
                        f.write("\n")
                    
                    f.write("  " + "-"*86 + "\n\n")
            
            f.write("="*90 + "\n\n")

        f.write("╔" + "═"*88 + "╗\n")
        f.write(f"║  RESUMEN GENERAL{' '*71} ║\n")
        f.write("╚" + "═"*88 + "╝\n\n")
        f.write(f"  Total de variables duplicadas encontradas: {total_dups}\n")
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
    print(f"\n✅ ANÁLISIS COMPLETADO")
    print(f"   • Total de variables duplicadas: {total_dups}")
    print(f"   • Ambientes analizados: {len(envs)}")
    print(f"   • Reporte: {filename}")

if __name__ == "__main__":
    main()