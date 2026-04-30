#!/usr/bin/env python3
"""
Analizador de duplicados en propiedades de entorno Kubernetes.
EXTRAE ÚNICAMENTE lo ubicado dentro de secciones 'env'
Genera reporte detallado de variables repetidas
"""

import os
import re
import getpass
import time
import requests
import yaml
from collections import defaultdict
from datetime import datetime

def get_raw_file(repo_path, branch, owner, repo, token):
    """Descarga contenido crudo de un archivo desde GitHub"""
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{repo_path}"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3.raw",
        "User-Agent": "K8s-Env-Analyzer"
    }
    resp = requests.get(url, headers=headers, params={"ref": branch})
    resp.raise_for_status()
    return resp.text

def parse_config_yaml(content, physical_env, ops_folder, logical_envs):
    """Resuelve placeholders ${...} y retorna paths por ambiente lógico"""
    try:
        config_data = yaml.safe_load(content)
    except yaml.YAMLError as e:
        raise ValueError(f"Error al parsear YAML de configuración: {e}")
    
    paths = []
    if isinstance(config_data, dict):
        if "configuration" in config_data:
            paths = config_data["configuration"].get("paths", [])
        elif "paths" in config_data:
            paths = config_data["paths"]
    
    if not paths:
        raise ValueError("No se encontraron 'paths' en el YAML de configuración")
    
    paths_by_env = {}
    for logical_env in logical_envs:
        resolved = []
        for tpl in paths:
            if not isinstance(tpl, str): continue
            p = tpl.replace("${physicalEnvironment}", physical_env)
            p = p.replace("${opsrepo_folder}", ops_folder)
            p = p.replace("${logicalEnvironment}", logical_env)
            p = re.sub(r'/+', '/', p).lstrip('/')
            resolved.append(p)
        paths_by_env[logical_env] = resolved
    return paths_by_env

def extract_env_properties(doc):
    """
    Extrae ÚNICAMENTE las propiedades dentro de cualquier sección 'env'.
    """
    envs = {}

    def find_env_section(obj):
        if isinstance(obj, dict):
            if 'env' in obj and isinstance(obj['env'], dict):
                vals = list(obj['env'].values())
                if vals and not any(isinstance(v, (dict, list)) for v in vals[:5]):
                    return obj['env']
            for v in obj.values():
                found = find_env_section(v)
                if found: return found
        elif isinstance(obj, list):
            for item in obj:
                found = find_env_section(item)
                if found: return found
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
        print(f"   ⚠️  YAML inválido en {file_path}: {e}")
        return all_envs

    for doc in docs:
        if isinstance(doc, dict):
            all_envs.update(extract_env_properties(doc))
    return all_envs

def find_duplicates(envs_by_file):
    """
    Detecta claves repetidas entre archivos del mismo ambiente
    Retorna información detallada de duplicados
    """
    key_map = defaultdict(list)
    
    # Mapear cada clave a sus archivos y valores
    for file_path, envs in envs_by_file.items():
        for key, value in envs.items():
            key_map[key].append({
                "file": file_path,
                "value": str(value),
                "filename": os.path.basename(file_path)
            })

    duplicates = {}
    for key, occurrences in key_map.items():
        if len(occurrences) > 1:  # Solo si aparece en más de un archivo
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

def analyze_environment(env_name, paths, branch, owner, repo, token):
    print(f"\n Analizando ambiente: {env_name.upper()}")
    print(f"   📁 {len(paths)} archivos a procesar")
    
    envs_by_file = {}
    success = fail = 0
    
    for p in paths:
        try:
            content = get_raw_file(p, branch, owner, repo, token)
            envs_by_file[p] = parse_env_yaml(content, p)
            success += 1
            time.sleep(0.2)
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                print(f"   ⚠️  No encontrado: {p}")
                fail += 1
            else:
                print(f"   ❌ Error HTTP {e.response.status_code} en {p}")
                fail += 1
        except Exception as e:
            print(f"   ⚠️  Error en {p}: {type(e).__name__}")
            fail += 1
            
    print(f"   ✅ {success} leídos |  {fail} fallidos")
    return find_duplicates(envs_by_file)

def generate_txt_report(all_results, owner, repo, branch, physical_env, ops_folder):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    output_file = f"reporte_env_duplicados_{repo}_{branch}_{datetime.now().strftime('%Y%m%d_%H%M')}.txt"
    lines = []
    
    # Encabezado
    lines.append("=" * 90)
    lines.append("REPORTE DE VARIABLES DUPLICADAS EN SECCIÓN 'env' - KUBERNETES")
    lines.append("=" * 90)
    lines.append(f"Generado        : {timestamp}")
    lines.append(f"Repositorio     : {owner}/{repo}")
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
            # Resumen del ambiente
            files_with_dups = set()
            for key, info in dups.items():
                for occ in info["occurrences"]:
                    files_with_dups.add(occ["filename"])
            total_files_affected += len(files_with_dups)
            
            lines.append(f"  📊 RESUMEN:")
            lines.append(f"     • Total de variables duplicadas: {len(dups)}")
            lines.append(f"     • Archivos con duplicados: {len(files_with_dups)}")
            lines.append("")
            
            # Lista de variables repetidas
            lines.append(f"  📋 LISTA DE VARIABLES DUPLICADAS ({len(dups)} variables):")
            lines.append("  " + "-" * 86)
            
            # Ordenar por número de ocurrencias (mayor primero)
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
                    # Truncar valor si es muy largo
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

    # Resumen general final
    lines.append("")
    lines.append("╔" + "═" * 88 + "╗")
    lines.append(f"║  RESUMEN GENERAL DEL REPORTE{' ' * 57} ║")
    lines.append("╚" + "═" * 88 + "╝")
    lines.append("")
    lines.append(f"  Total de variables duplicadas encontradas: {total_duplicated_keys}")
    lines.append(f"  Total de archivos afectados: {total_files_affected}")
    lines.append(f"  Ambientes analizados: {len(all_results)}")
    lines.append("")
    
    # Tabla resumen por ambiente
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
    
    # Guardar archivo
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
        # 1. Repositorio
        print("\n📦 REPOSITORIO")
        print("-" * 70)
        repo_in = input("Repositorio (owner/repo): ").strip()
        if "/" not in repo_in: 
            raise ValueError("Formato inválido. Usa: owner/repo")
        owner, repo = repo_in.split("/", 1)
        
        branch = input("Rama del repositorio [main]: ").strip() or "main"
        
        # 2. Token
        print("\n🔑 AUTENTICACIÓN")
        print("-" * 70)
        token = os.getenv("GITHUB_TOKEN")
        if not token:
            print("⚠️  GITHUB_TOKEN no encontrado en variables de entorno")
            token = getpass.getpass("Ingresa tu Personal Access Token: ").strip()
        else:
            print("✅ Token detectado desde variable de entorno")
        
        if not token: 
            raise ValueError("Se requiere un token válido para acceder a GitHub")
        
        # 3. Archivo de configuración
        print("\n📄 ARCHIVO DE CONFIGURACIÓN")
        print("-" * 70)
        cfg_path = input("Ruta del YAML de configuración [DeployConfigStructure.yaml]: ").strip()
        if not cfg_path: 
            cfg_path = "DeployConfigStructure.yaml"
        
        # 4. Parámetros de resolución
        print("\n⚙️  PARÁMETROS DE RESOLUCIÓN")
        print("-" * 70)
        phys = input("physicalEnvironment: ").strip()
        if not phys: 
            raise ValueError("physicalEnvironment es requerido")
        
        ops = input("opsrepo_folder: ").strip()
        if not ops: 
            raise ValueError("opsrepo_folder es requerido")
        
        # 5. Selección de ambientes
        print("\n🌍 AMBIENTES LÓGICOS")
        print("-" * 70)
        logical_envs = select_logical_environments()
        print(f"\n✅ Ambientes seleccionados: {', '.join(logical_envs)}")
        
        # 6. Ejecutar análisis
        print("\n" + "="*70)
        print("🚀 INICIANDO ANÁLISIS DE DUPLICADOS")
        print("="*70)
        
        print(f"\n📥 Descargando configuración: {cfg_path}")
        cfg_content = get_raw_file(cfg_path, branch, owner, repo, token)
        
        print("🔄 Resolviendo paths para cada ambiente...")
        paths_by_env = parse_config_yaml(cfg_content, phys, ops, logical_envs)
        
        all_results = {}
        for env_name, paths in paths_by_env.items():
            all_results[env_name] = analyze_environment(
                env_name, paths, branch, owner, repo, token
            )
        
        # 7. Generar reporte
        print("\n📊 GENERANDO REPORTE DE DUPLICADOS")
        print("="*70)
        output_file = generate_txt_report(
            all_results, owner, repo, branch, phys, ops
        )
        
        print("\n" + "="*70)
        print("✅ ANÁLISIS COMPLETADO EXITOSAMENTE")
        print("="*70)
        print(f"\n📁 Archivo de reporte: {output_file}")
        print("\n💡 El reporte incluye:")
        print("   • Lista completa de variables duplicadas")
        print("   • Archivos donde aparece cada variable")
        print("   • Valores de cada ocurrencia")
        print("   • Indicador si los valores son idénticos o diferentes")
        print("")
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Proceso cancelado por el usuario")
    except FileNotFoundError as e:
        print(f"\n❌ ERROR: Archivo no encontrado - {e}")
        print("   → Verifica que la ruta del archivo sea correcta en el repositorio")
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            print(f"\n❌ ERROR: Recurso no encontrado (404)")
            print("   → Verifica: repositorio, rama, token y ruta del archivo")
        elif e.response.status_code in [401, 403]:
            print(f"\n❌ ERROR: Autenticación fallida ({e.response.status_code})")
            print("   → Verifica que el token sea válido y tenga permisos de lectura")
        else:
            print(f"\n❌ ERROR HTTP: {e.response.status_code} - {e.response.reason}")
    except ValueError as e:
        print(f"\n❌ ERROR: {e}")
    except Exception as e:
        print(f"\n❌ ERROR CRÍTICO: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()