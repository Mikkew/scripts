#!/usr/bin/env python3
"""
Analizador de duplicados en propiedades de entorno Kubernetes.
Procesa TODOS los paths del archivo DeployConfigStructure.yaml
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

def get_raw_file(repo_path, branch, owner, repo, token, api_base_url="https://api.github.com"):
    """
    Descarga el contenido de UN archivo desde GitHub.
    repo_path: ruta relativa dentro del repositorio
    """
    url = f"{api_base_url}/repos/{owner}/{repo}/contents/{repo_path}"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3.raw",
        "User-Agent": "K8s-Env-Analyzer"
    }
    
    try:
        # Deshabilitar verificación SSL para GitHub Enterprise
        resp = requests.get(url, headers=headers, params={"ref": branch}, verify=False)
        resp.raise_for_status()
        return resp.text
    except requests.exceptions.SSLError:
        # Reintentar sin verificación SSL
        resp = requests.get(url, headers=headers, params={"ref": branch}, verify=False)
        resp.raise_for_status()
        return resp.text

def extract_repo_info_from_url(config_path_url):
    """Extrae owner y repo de una URL de GitHub"""
    config_path_url = config_path_url.rstrip('/')
    parsed = urlparse(config_path_url)
    path_parts = parsed.path.strip('/').split('/')
    
    if len(path_parts) >= 2:
        return path_parts[-2], path_parts[-1]
    raise ValueError(f"No se pudo extraer owner/repo de: {config_path_url}")

def get_github_api_base_url(config_path_url):
    """Determina la URL base de la API"""
    parsed = urlparse(config_path_url)
    hostname = parsed.hostname
    
    if hostname == "github.com":
        return "https://api.github.com"
    else:
        return f"https://{hostname}"

def parse_config_yaml(content):
    """
    Parsea el YAML de configuración y extrae:
    - configPath (URL del repo)
    - paths (TODOS los paths a procesar)
    """
    try:
        config_data = yaml.safe_load(content)
    except yaml.YAMLError as e:
        raise ValueError(f"Error al parsear YAML: {e}")
    
    # Extraer configPath
    config_path_url = None
    if isinstance(config_data, dict):
        if "defaults" in config_data and isinstance(config_data["defaults"], dict):
            config_path_url = config_data["defaults"].get("configPath")
        elif "configPath" in config_data:
            config_path_url = config_data["configPath"]
    
    if not config_path_url:
        raise ValueError("No se encontró 'configPath' en el YAML")
    
    # Extraer TODOS los paths de la sección configuration.paths
    all_paths = []
    if isinstance(config_data, dict):
        if "configuration" in config_data and isinstance(config_data["configuration"], dict):
            paths_list = config_data["configuration"].get("paths", [])
            if isinstance(paths_list, list):
                all_paths.extend(paths_list)
        elif "paths" in config_data:
            paths_list = config_data["paths"]
            if isinstance(paths_list, list):
                all_paths.extend(paths_list)
    
    if not all_paths:
        raise ValueError("No se encontraron 'paths' en el YAML de configuración")
    
    print(f"   📋 Total de paths encontrados en el YAML: {len(all_paths)}")
    for i, p in enumerate(all_paths[:5], 1):  # Mostrar primeros 5
        print(f"      {i}. {p}")
    if len(all_paths) > 5:
        print(f"      ... y {len(all_paths) - 5} más")
    
    return config_path_url, all_paths

def resolve_all_paths(paths, physical_env, ops_folder, logical_envs):
    """
    Resuelve TODOS los paths para TODOS los ambientes lógicos.
    Retorna un diccionario: {ambiente: [lista_de_paths_resueltos]}
    """
    paths_by_env = {}
    
    for env in logical_envs:
        resolved = []
        for tpl in paths:
            if not isinstance(tpl, str):
                continue
            
            # Reemplazar placeholders
            p = tpl.replace("${physicalEnvironment}", physical_env)
            p = p.replace("${opsrepo_folder}", ops_folder)
            p = p.replace("${logicalEnvironment}", env)
            
            # Limpiar path
            p = re.sub(r'/+', '/', p).lstrip('/')
            resolved.append(p)
        
        paths_by_env[env] = resolved
        print(f"   ✅ Ambiente '{env.upper()}': {len(resolved)} paths resueltos")
    
    return paths_by_env

def extract_env_properties(doc):
    """Extrae ÚNICAMENTE las propiedades dentro de sección 'env'"""
    envs = {}

    def find_env_section(obj):
        if isinstance(obj, dict):
            if 'env' in obj and isinstance(obj['env'], dict):
                vals = list(obj['env'].values())
                if vals and not any(isinstance(v, (dict, list)) for v in vals[:5]):
                    return obj['env']
            for v in obj.values():
                found = find_env_section(v)
                if found:
                    return found
        elif isinstance(obj, list):
            for item in obj:
                found = find_env_section(item)
                if found:
                    return found
        return None

    env_dict = find_env_section(doc)
    if env_dict:
        for k, v in env_dict.items():
            envs[str(k)] = str(v)
    return envs

def parse_env_yaml(content, file_path):
    """Parsea YAML y extrae SOLO propiedades de 'env'"""
    all_envs = {}
    try:
        docs = list(yaml.safe_load_all(content))
    except yaml.YAMLError as e:
        print(f"   ⚠️  YAML inválido en {os.path.basename(file_path)}: {e}")
        return all_envs

    for doc in docs:
        if isinstance(doc, dict):
            all_envs.update(extract_env_properties(doc))
    return all_envs

def find_duplicates(envs_by_file):
    """Detecta claves repetidas entre archivos del mismo ambiente"""
    key_map = defaultdict(list)
    
    for file_path, envs in envs_by_file.items():
        for key, value in envs.items():
            key_map[key].append({
                "file": file_path,
                "value": str(value),
                "filename": os.path.basename(file_path)
            })

    duplicates = {}
    for key, occurrences in key_map.items():
        if len(occurrences) > 1:
            unique_values = set(o["value"] for o in occurrences)
            duplicates[key] = {
                "key": key,
                "total_occurrences": len(occurrences),
                "files_count": len(set(o["file"] for o in occurrences)),
                "unique_values_count": len(unique_values),
                "identical_values": len(unique_values) == 1,
                "occurrences": occurrences,
                "values": list(unique_values)
            }
    
    return duplicates

def analyze_environment(env_name, resolved_paths, branch, owner, repo, token, api_base_url):
    """
    Analiza TODOS los paths de un ambiente:
    - Descarga cada archivo con get_raw_file
    - Extrae propiedades env
    - Detecta duplicados
    """
    print(f"\n🌍 Analizando ambiente: {env_name.upper()}")
    print(f"   📁 Total de archivos a procesar: {len(resolved_paths)}")
    
    envs_by_file = {}
    success = 0
    failed = 0
    not_found = 0
    
    for idx, repo_path in enumerate(resolved_paths, 1):
        try:
            print(f"   [{idx}/{len(resolved_paths)}] Descargando: {repo_path}")
            
            # AQUÍ SE LLAMA get_raw_file para CADA path del archivo Deploy
            content = get_raw_file(repo_path, branch, owner, repo, token, api_base_url)
            
            # Extraer propiedades env del contenido descargado
            envs_by_file[repo_path] = parse_env_yaml(content, repo_path)
            success += 1
            time.sleep(0.15)  # Rate limiting
            
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                print(f"   ⚠️  No encontrado (404): {repo_path}")
                not_found += 1
            else:
                print(f"   ❌ Error HTTP {e.response.status_code}: {repo_path}")
                failed += 1
        except Exception as e:
            print(f"   ⚠️  Error en {os.path.basename(repo_path)}: {type(e).__name__}")
            failed += 1
    
    print(f"\n   📊 Resumen {env_name.upper()}:")
    print(f"      ✅ Exitosos: {success}")
    print(f"      ⚠️  No encontrados: {not_found}")
    print(f"      ❌ Errores: {failed}")
    
    # Encontrar duplicados en este ambiente
    duplicates = find_duplicates(envs_by_file)
    print(f"      🔍 Variables duplicadas encontradas: {len(duplicates)}")
    
    return duplicates

def generate_txt_report(all_results, repo_url, branch, physical_env, ops_folder):
    """Genera reporte TXT detallado"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    output_file = f"reporte_env_duplicados_{datetime.now().strftime('%Y%m%d_%H%M')}.txt"
    lines = []
    
    lines.append("=" * 90)
    lines.append("REPORTE DE VARIABLES DUPLICADAS EN SECCIÓN 'env' - KUBERNETES")
    lines.append("=" * 90)
    lines.append(f"Generado        : {timestamp}")
    lines.append(f"Repositorio     : {repo_url}")
    lines.append(f"Rama            : {branch}")
    lines.append(f"Physical Env    : {physical_env}")
    lines.append(f"Ops Folder      : {ops_folder}")
    lines.append(f"Ambientes       : {', '.join(all_results.keys())}")
    lines.append("Análisis        : Propiedades dentro de secciones 'env'")
    lines.append("=" * 90)
    lines.append("")

    total_duplicated_keys = 0
    total_files_affected = 0
    
    for env in sorted(all_results.keys()):
        dups = all_results[env]
        total_duplicated_keys += len(dups)
        
        lines.append("")
        lines.append("╔" + "═" * 88 + "╗")
        lines.append(f"║  AMBIENTE: {env.upper():<76} ║")
        lines.append("╚" + "═" * 88 + "╝")
        lines.append("")
        
        if not dups:
            lines.append("  ✅ NO SE ENCONTRARON VARIABLES DUPLICADAS en este ambiente")
            lines.append("")
        else:
            files_with_dups = set()
            for key, info in dups.items():
                for occ in info["occurrences"]:
                    files_with_dups.add(occ["filename"])
            total_files_affected += len(files_with_dups)
            
            lines.append(f"  📊 RESUMEN:")
            lines.append(f"     • Total de variables duplicadas: {len(dups)}")
            lines.append(f"     • Archivos con duplicados: {len(files_with_dups)}")
            lines.append("")
            
            lines.append(f"  📋 LISTA DE VARIABLES DUPLICADAS ({len(dups)} variables):")
            lines.append("  " + "-" * 86)
            
            sorted_dups = sorted(dups.items(), key=lambda x: x[1]["total_occurrences"], reverse=True)
            
            for idx, (key, info) in enumerate(sorted_dups, 1):
                status_icon = "🟢" if info["identical_values"] else "🔴"
                status_text = "VALORES IDÉNTICOS" if info["identical_values"] else "VALORES DIFERENTES"
                
                lines.append("")
                lines.append(f"  {idx}. {key}")
                lines.append(f"     {status_icon} Estado: {status_text}")
                lines.append(f"     📈 Repetida en {info['total_occurrences']} archivos")
                lines.append(f"     🔢 Valores únicos: {info['unique_values_count']}")
                lines.append("")
                lines.append(f"     UBICACIÓN Y VALORES:")
                
                for occ in info["occurrences"]:
                    val = occ["value"]
                    if len(val) > 70:
                        display_val = val[:67] + "..."
                    else:
                        display_val = val
                    
                    lines.append(f"       • {occ['filename']}")
                    lines.append(f"         └─ {display_val}")
                
                lines.append("")
                lines.append("  " + "-" * 86)
        
        lines.append("")
        lines.append("=" * 90)

    lines.append("")
    lines.append("╔" + "═" * 88 + "╗")
    lines.append(f"║  RESUMEN GENERAL DEL REPORTE{' ' * 57} ║")
    lines.append("╚" + "═" * 88 + "╝")
    lines.append("")
    lines.append(f"  Total de variables duplicadas encontradas: {total_duplicated_keys}")
    lines.append(f"  Total de archivos afectados: {total_files_affected}")
    lines.append(f"  Ambientes analizados: {len(all_results)}")
    lines.append("")
    
    lines.append("  DESGLOSE POR AMBIENTE:")
    lines.append("  " + "-" * 86)
    lines.append(f"  {'Ambiente':<15} {'Variables Duplicadas':<25} {'Estado'}")
    lines.append("  " + "-" * 86)
    for env in sorted(all_results.keys()):
        count = len(all_results[env])
        status = "⚠️  Con duplicados" if count > 0 else "✅ Sin duplicados"
        lines.append(f"  {env.upper():<15} {count:<25} {status}")
    lines.append("  " + "-" * 86)
    lines.append("")
    
    lines.append("FIN DEL REPORTE")
    lines.append("=" * 90)
    
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
        
    print(f"\n💾 Reporte guardado: {output_file}")
    return output_file

def select_logical_environments():
    available = ["sct", "cert0", "cert"]
    print("\n Ambientes lógicos disponibles:")
    for i, e in enumerate(available, 1): 
        print(f"   {i}. {e}")
    print("   4. TODOS")
    print("   5. selección personalizada")
    
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
        else:
            print("   ❌ Opción inválida. Intenta de nuevo")

def main():
    print("\n" + "="*70)
    print(" ANALIZADOR DE VARIABLES DUPLICADAS EN 'env' - KUBERNETES")
    print("="*70)
    
    try:
        # 1. Ruta del archivo DeployConfigStructure.yaml
        print("\n📄 ARCHIVO DE CONFIGURACIÓN")
        print("-" * 70)
        cfg_path = input("Ruta del YAML de configuración [DeployConfigStructure.yaml]: ").strip()
        if not cfg_path: 
            cfg_path = "DeployConfigStructure.yaml"
        
        # 2. Rama
        branch = input("Rama del repositorio [main]: ").strip() or "main"
        
        # 3. Token
        print("\n🔑 AUTENTICACIÓN")
        print("-" * 70)
        token = os.getenv("GITHUB_TOKEN")
        if not token:
            print("⚠️  GITHUB_TOKEN no encontrado en variables de entorno")
            token = getpass.getpass("Ingresa tu Personal Access Token: ").strip()
        else:
            print("✅ Token detectado desde variable de entorno")
        
        if not token: 
            raise ValueError("Se requiere un token válido")
        
        # 4. Parámetros
        print("\n⚙️  PARÁMETROS DE RESOLUCIÓN")
        print("-" * 70)
        phys = input("physicalEnvironment: ").strip()
        if not phys: 
            raise ValueError("physicalEnvironment es requerido")
        
        ops = input("opsrepo_folder: ").strip()
        if not ops: 
            raise ValueError("opsrepo_folder es requerido")
        
        # 5. Ambientes
        print("\n🌍 AMBIENTES LÓGICOS")
        print("-" * 70)
        logical_envs = select_logical_environments()
        print(f"\n✅ Ambientes seleccionados: {', '.join(logical_envs)}")
        
        # 6. Descargar y parsear configuración
        print("\n" + "="*70)
        print("🚀 INICIANDO ANÁLISIS")
        print("="*70)
        
        print(f"\n📥 Paso 1: Descargando archivo de configuración...")
        print(f"   Owner/Repo temporal (solo para descargar config):")
        temp_owner = input("   Owner: ").strip()
        temp_repo = input("   Repo: ").strip()
        
        # Descargar YAML de configuración
        api_base_temp = "https://api.github.com"
        cfg_content = get_raw_file(cfg_path, branch, temp_owner, temp_repo, token, api_base_temp)
        
        # Parsear para obtener configPath y TODOS los paths
        print(f"\n📋 Paso 2: Parseando configuración...")
        config_path_url, all_paths = parse_config_yaml(cfg_content)
        
        # Extraer owner/repo reales de configPath
        owner, repo = extract_repo_info_from_url(config_path_url)
        api_base_url = get_github_api_base_url(config_path_url)
        
        print(f"\n✅ Repositorio objetivo: {config_path_url}")
        print(f"   Owner: {owner}")
        print(f"   Repo: {repo}")
        print(f"   API Base: {api_base_url}")
        
        # 7. Resolver TODOS los paths para cada ambiente
        print(f"\n🔄 Paso 3: Resolviendo paths para cada ambiente...")
        paths_by_env = resolve_all_paths(all_paths, phys, ops, logical_envs)
        
        # 8. Analizar CADA ambiente (get_raw_file se llama para CADA path)
        print(f"\n🔍 Paso 4: Analizando archivos (get_raw_file por cada path)...")
        print("="*70)
        
        all_results = {}
        for env_name in logical_envs:
            resolved_paths = paths_by_env[env_name]
            all_results[env_name] = analyze_environment(
                env_name, resolved_paths, branch, owner, repo, token, api_base_url
            )
        
        # 9. Generar reporte
        print("\n" + "="*70)
        print("📊 Paso 5: Generando reporte...")
        print("="*70)
        output_file = generate_txt_report(
            all_results, config_path_url, branch, phys, ops
        )
        
        print("\n" + "="*70)
        print("✅ ANÁLISIS COMPLETADO")
        print("="*70)
        print(f"\n📁 Reporte: {output_file}")
        print("\n💡 El script procesó:")
        print(f"   • {len(all_paths)} paths del archivo DeployConfigStructure.yaml")
        print(f"   • {len(logical_envs)} ambientes ({', '.join(logical_envs)})")
        print(f"   • Total: {len(all_paths) * len(logical_envs)} archivos descargados con get_raw_file")
        print("")
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Cancelado por el usuario")
    except Exception as e:
        print(f"\n❌ ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()