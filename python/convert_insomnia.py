#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import yaml
import json
import argparse
import sys
import os

def convertir_insomnia_v5_a_v4(entrada, salida):
    """
    Convierte un archivo de exportación de Insomnia v5 (YAML) 
    a formato v4 (JSON).
    """
    
    # 1. Validar que el archivo de entrada existe
    if not os.path.isfile(entrada):
        print(f"Error: El archivo '{entrada}' no existe.")
        sys.exit(1)

    try:
        # 2. Leer el archivo YAML
        print(f"Leyendo archivo YAML: {entrada}...")
        with open(entrada, 'r', encoding='utf-8') as f:
            try:
                data = yaml.safe_load(f)
            except yaml.YAMLError as e:
                print(f"Error al parsear YAML: {e}")
                sys.exit(1)

        # 3. Validación básica de estructura
        # Las exportaciones de Insomnia suelen ser una lista de recursos
        if data is None:
            print("Error: El archivo YAML está vacío.")
            sys.exit(1)
        
        if not isinstance(data, (list, dict)):
            print("Advertencia: La raíz del documento no es una lista ni un diccionario, se procederá tal cual.")

        # 4. Escribir el archivo JSON
        print(f"Escribiendo archivo JSON: {salida}...")
        with open(salida, 'w', encoding='utf-8') as f:
            # ensure_ascii=False permite caracteres especiales (ñ, tildes, emojis)
            # indent=2 hace que el JSON sea legible (pretty print)
            json.dump(data, f, indent=2, ensure_ascii=False)

        print("¡Conversión completada con éxito!")
        print(f"Ruta de salida: {os.path.abspath(salida)}")

    except Exception as e:
        print(f"Ocurrió un error inesperado: {e}")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(
        description="Convierte exportaciones de Insomnia v5 (YAML) a v4 (JSON)."
    )
    parser.add_argument(
        "input_file",
        help="Ruta al archivo .yaml exportado desde Insomnia v5"
    )
    parser.add_argument(
        "output_file",
        nargs="?",
        default="insomnia_v4_export.json",
        help="Ruta para el archivo .json de salida (Por defecto: insomnia_v4_export.json)"
    )

    args = parser.parse_args()

    # Ejecutar conversión
    convertir_insomnia_v5_a_v4(args.input_file, args.output_file)

if __name__ == "__main__":
    main()