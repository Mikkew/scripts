#!/usr/bin/env python3
"""
Analizador interactivo de duplicados en variables de entorno Kubernetes.
- Solicita repo y rama por consola
- Usa GITHUB_TOKEN si existe, si no lo pide de forma segura
- Genera reporte TXT por ambiente (sct, cert0, cert)
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
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3.raw"}
    resp = requests.get(url, headers=headers, params={"ref": branch})
    resp.raise_for_status()
    return resp.text

def resolve_paths(config_data, env):
    """Extrae rutas del YAML de configuración y reemplaza placeholders"""
    paths = []
    def extract(obj):
        if isinstance(obj, dict):
            for v in obj.values(): extract(v)
        elif isinstance(obj, list):
            for v in obj: extract(v)
        elif isinstance(obj, str) and any(obj.endswith(ext) for ext in (".yaml", ".yml")):
            cleaned = re.sub(r"\{(env|ENV|environment|Environment)\}", env, obj, flags=re.IGNORECASE)
            paths.append(cleaned)
    extract(config_data)
    return paths

def extract_k8s_envs(doc):
    """Extrae variables de entorno de un documento YAML de K8s"""
    envs = {}
    kind = doc.get("kind", "")
    name = doc.get("metadata", {}).get("name", "unknown")

    if kind == "ConfigMap" and doc.get("data"):
        for k, v in doc["data"].items():
            envs[f"configmap.{name}.{k}"] = str(v)

    elif kind == "Secret":
        if "stringData" in doc:
            for k, v in doc["stringData"].items():
                envs[f"secret.{name}.{k}"] = str(v)
        elif "data" in doc:
            import base64
            for k, v in doc["data"].items():
                try:
                    envs[f"secret.{name}.{k}"] = base64.b64decode(v).decode("utf-8", errors="replace")
                except Exception:
                    envs[f"secret.{name}.{k}"] = "[base64-invalid]"

    elif kind in ("Deployment", "StatefulSet", "DaemonSet", "Job", "CronJob", "Pod"):
        spec = doc.get("spec", {})
        if kind == "CronJob":
            spec = spec.get("jobTemplate", {}).get("spec", {}).get("template", {}).get("spec", {})
        else:
            spec = spec.get("template", {}).get("spec", {})

        containers = spec.get("containers", []) + spec.get("initContainers", [])
        for container in containers:
            cname = container.get("name", "unknown")
            for env_item in container.get("env", []):
                ename = env_item.get("name")
                if ename and "value" in env_item:
                    envs[f"pod.{cname}.{ename}"] = str(env_item["value"])
                elif ename and "valueFrom" in env_item:
                    envs[f"pod.{cname}.{ename}"] = "[valueFrom-ref]"

    else:  # Fallback: YAML plano o values de Helm
        def flatten(d, parent=""):
            items = {}
            if isinstance(d, dict):
                for k, v in d.items():
                    new_k = f"{parent}.{k}" if parent else k
                    items.update(flatten(v, new_k) if isinstance(v, dict) else {new_k: str(v)})
            return items
        envs.update(flatten(doc))

    return envs

def parse_k8s_yaml(content, file_path):
    """Parsea YAML multi-documento y extrae envs"""
    all_envs = {}
    try:
        docs = list(yaml.safe_load_all(content))
    except yaml.YAMLError as e:
        print(f"   ⚠️  YAML inválido en {file_path}: {e}")
        return all_envs

    for doc in docs:
        if isinstance(doc, dict):
            all_envs.update(extract_k8s_envs(doc))
    return all_envs

def find_duplicates(envs_by_file):
    """Detecta claves repetidas entre archivos del mismo ambiente"""
    key_map = defaultdict(list)
    for f, envs in envs_by_file.items():
        for k, v in envs.items():
            key_map[k].append({"file": f, "value": str(v)})

    duplicates = {}
    for k, occs in key_map.items():
        if len(occs) > 1:
            values = set(o["value"] for o in occs)
            duplicates[k] = {
                "count": len(occs),
                "identical_values": len(values) == 1,
                "occurrences": occs
            }
    return duplicates

def analyze_environment(env, config_data, branch, owner, repo, token):
    print(f"🌍 Analizando ambiente: {env.upper()}...")
    paths = resolve_paths(config_data, env)
    
    envs_by_file = {}
    for p in paths:
        try:
            content = get_raw_file(p, branch, owner, repo, token)
            envs_by_file[p] = parse_k8s_yaml(content, p)
            time.sleep(0.25)  # Respetar rate-limit
        except Exception as e:
            print(f"   ⚠️  Error en {p}: {e}")
            
    return find_duplicates(envs_by_file)

def generate_txt_report(all_results, owner, repo, branch):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    output_file = f"reporte_duplicados_{repo}_{branch}_{datetime.now().strftime('%Y%m%d_%H%M')}.txt"
    lines = []
    
    lines.append("=" * 80)
    lines.append("REPORTE DE DUPLICADOS EN VARIABLES DE ENTORNO KUBERNETES")
    lines.append(f"Generado        : {timestamp}")
    lines.append(f"Repositorio     : {owner}/{repo} (rama: {branch})")
    lines.append(f"Ambientes       : sct, cert0, cert")
    lines.append("=" * 80)
    lines.append("")

    for env in ["sct", "cert0", "cert"]:
        dups = all_results.get(env, {})
        lines.append(f"[AMBIENTE: {env.upper()}]")
        lines.append(f"Total claves duplicadas: {len(dups)}")
        lines.append("-" * 80)

        if not dups:
            lines.append("✅ No se encontraron duplicados en este ambiente.")
        else:
            sorted_dups = sorted(dups.items(), key=lambda x: x[1]["count"], reverse=True)
            for key, info in sorted_dups:
                status = "VALORES IDÉNTICOS" if info["identical_values"] else "VALORES DISTINTOS"
                clean_key = key.split(".")[-1] if "." in key else key
                lines.append(f"🔑 {clean_key} (origen: {key}) [{status}]")
                lines.append(f"   Archivos ({info['count']}):")
                for occ in info["occurrences"]:
                    val = str(occ["value"])
                    if len(val) > 100:
                        val = val[:97] + "..."
                    lines.append(f"     📄 {occ['file']}")
                    lines.append(f"        └─ {val}")
        lines.append("=" * 80)
        lines.append("")

    lines.append("FIN DEL REPORTE")
    
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
        
    print(f"\n💾 Reporte TXT generado: {output_file}")
    return output_file

def main():
    print("\n🔍 Analizador de Duplicados K8s - Modo Interactivo")
    print("="*50)
    
    # 1️⃣ Solicitar Repo y Branch
    repo_input = input("📦 Introduce el repositorio (formato: owner/repo): ").strip()
    if "/" not in repo_input:
        raise ValueError("❌ Formato inválido. Usa owner/repo (ej: mi-org/mi-repo)")
    owner, repo = repo_input.split("/", 1)
    
    branch = input("🌿 Introduce la rama (ej: main, develop) [main]: ").strip() or "main"
    
    # 2️⃣ Gestionar Token
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        print("🔑 No se encontró GITHUB_TOKEN en el entorno.")
        token = getpass.getpass("   Introduce tu Personal Access Token: ").strip()
    else:
        print("✅ Token detectado desde variable de entorno.")
        
    config_path = input("📄 Ruta del YAML de configuración en el repo [config/file-paths.yaml]: ").strip() or "config/file-paths.yaml"
    print("="*50)
    
    if not token:
        raise ValueError("⛔ Se requiere un token válido para acceder a GitHub.")

    # 3️⃣ Ejecutar análisis
    try:
        print("📥 Descargando configuración de rutas...")
        config_content = get_raw_file(config_path, branch, owner, repo, token)
        config_data = yaml.safe_load(config_content)

        all_results = {}
        for env in ["sct", "cert0", "cert"]:
            all_results[env] = analyze_environment(env, config_data, branch, owner, repo, token)

        generate_txt_report(all_results, owner, repo, branch)
        print("✅ Proceso finalizado con éxito.")
        
    except KeyboardInterrupt:
        print("\n⚠️  Proceso cancelado por el usuario.")
    except requests.exceptions.HTTPError as e:
        print(f"\n❌ Error de autenticación o permisos: {e.response.status_code} {e.response.reason}")
        if e.response.status_code == 404:
            print("   → Verifica que el repo, rama y ruta del YAML sean correctos y el token tenga acceso.")
    except Exception as e:
        print(f"\n❌ Error crítico: {e}")

if __name__ == "__main__":
    main()