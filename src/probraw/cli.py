from __future__ import annotations

import argparse
from pathlib import Path
import json
import sys
import warnings

warnings.filterwarnings(
    "ignore",
    message='.*"Matplotlib" related API features are not available.*',
)

try:
    from colour.utilities import ColourUsageWarning

    warnings.filterwarnings("ignore", category=ColourUsageWarning)
except Exception:
    pass

from .performance import SYSTEM_CONFIG_PATH, configure_runtime, performance_report, write_performance_config

configure_runtime()

from .chart.detection import detect_chart, detect_chart_from_corners, draw_detection_overlay
from .chart.sampling import (
    ReferenceCatalog,
    chart_detection_from_json,
    sample_chart,
    sampleset_from_json,
)
from .core.models import to_json_dict, write_json
from .core.utils import versioned_output_path
from .core.recipe import load_recipe, save_recipe
from .display_color import detect_system_display_profile, display_profile_label
from .metadata_viewer import inspect_file_metadata
from .profile.development import build_development_profile
from .profile.builder import build_profile, validate_profile, write_samples_cgats
from .profile.export import batch_develop
from .provenance.c2pa import (
    DEFAULT_TIMESTAMP_URL,
    C2PASignConfig,
    auto_c2pa_config,
    c2pa_config_from_environment,
    verify_c2pa_raw_link,
)
from .provenance.probraw_proof import (
    ProbRawProofConfig,
    generate_ed25519_identity,
    proof_config_from_environment,
    verify_probraw_proof,
)
from .qa_compare import compare_qa_reports
from .raw.metadata import raw_info
from .raw.pipeline import develop_controlled
from .reporting import (
    check_amaze_backend,
    check_c2pa_support,
    check_color_environment,
    check_external_tools,
    gather_run_context,
)
from .version import __version__
from .workflow import auto_profile_batch

APP_VERSION = __version__
DEFAULT_CLI_NAME = "probraw"


def _runtime_cli_name() -> str:
    stem = Path(sys.argv[0]).stem
    return stem if stem == "probraw" else DEFAULT_CLI_NAME


def _parse_corner_arg(value: str) -> tuple[float, float]:
    try:
        x_text, y_text = value.split(",", 1)
        return float(x_text), float(y_text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("usa formato x,y para cada esquina") from exc


def build_parser(prog: str | None = None) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog=prog or DEFAULT_CLI_NAME,
        description="CLI de ProbRAW para perfilado ICC reproducible",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {APP_VERSION}")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("raw-info")
    s.add_argument("input")

    s = sub.add_parser("metadata")
    s.add_argument("input", help="Archivo RAW/TIFF/imagen a inspeccionar")
    s.add_argument("--out", default=None, help="JSON de salida opcional")
    s.add_argument("--no-c2pa", action="store_true", help="No intenta leer manifiestos C2PA")

    s = sub.add_parser("develop")
    s.add_argument("input")
    s.add_argument("--recipe", required=True)
    s.add_argument("--out", required=True)
    s.add_argument("--audit-linear", default=None)
    s.add_argument("--cache-dir", default=None, help="Directorio de cache numerica de demosaico si la receta usa use_cache")

    s = sub.add_parser("detect-chart")
    s.add_argument("input")
    s.add_argument("--out", required=True)
    s.add_argument("--preview", default=None)
    s.add_argument("--chart-type", choices=["colorchecker24", "it8"], default="colorchecker24")
    s.add_argument(
        "--manual-corners",
        nargs=4,
        type=_parse_corner_arg,
        metavar="X,Y",
        help="Cuatro esquinas de la carta para deteccion manual/asistida",
    )

    s = sub.add_parser("sample-chart")
    s.add_argument("input")
    s.add_argument("--detection", required=True)
    s.add_argument("--reference", required=True)
    s.add_argument("--out", required=True)
    s.add_argument("--recipe", default=None, help="Receta opcional para parametros de muestreo")

    s = sub.add_parser("build-profile")
    s.add_argument("samples")
    s.add_argument("--recipe", required=True)
    s.add_argument("--out", required=True)
    s.add_argument("--report", required=True)
    s.add_argument("--camera", default=None)
    s.add_argument("--lens", default=None)

    s = sub.add_parser("export-cgats")
    s.add_argument("samples")
    s.add_argument("--out", required=True)

    s = sub.add_parser("build-develop-profile")
    s.add_argument("samples")
    s.add_argument("--recipe", required=True)
    s.add_argument("--out", required=True, help="Perfil de revelado JSON")
    s.add_argument("--calibrated-recipe", required=True, help="Receta calibrada YAML/JSON")

    s = sub.add_parser("batch-develop")
    s.add_argument("input")
    s.add_argument("--recipe", required=True)
    s.add_argument(
        "--profile",
        default=None,
        help=(
            "Perfil ICC de entrada de sesion. Opcional solo cuando la receta usa "
            "output_space estandar sin carta (srgb, adobe_rgb o prophoto_rgb)."
        ),
    )
    s.add_argument("--out", required=True)
    s.add_argument(
        "--tiff-compression",
        choices=["none", "zip", "lzw", "jpeg", "zstd"],
        default="none",
        help="Compresion del TIFF final: none, zip/deflate, lzw, jpeg o zstd",
    )
    s.add_argument(
        "--workers",
        type=int,
        default=None,
        help="Numero de trabajadores para el lote; 1 fuerza serial, 0/omitido usa auto",
    )
    s.add_argument(
        "--tiff-workers",
        type=int,
        default=None,
        help="Hilos de compresion por TIFF; 0/omitido reparte CPU automaticamente en lote",
    )
    s.add_argument("--cache-dir", default=None, help="Directorio de cache numerica de demosaico si la receta usa use_cache")
    s.add_argument("--c2pa-sign", action="store_true", help="Firma C2PA opcional si hay certificado disponible")
    s.add_argument("--no-c2pa", action="store_true", help="No intenta firma C2PA automatica; mantiene ProbRAW Proof")
    s.add_argument("--c2pa-cert", default=None, help="Cadena de certificado PEM para C2PA")
    s.add_argument("--c2pa-key", default=None, help="Clave privada PEM para C2PA")
    s.add_argument("--c2pa-alg", default="ps256", help="Algoritmo de firma C2PA: ps256, ps384, es256...")
    s.add_argument("--c2pa-timestamp-url", default=DEFAULT_TIMESTAMP_URL, help="URL TSA RFC 3161")
    s.add_argument("--c2pa-signer-name", default="ProbRAW", help="Nombre publico del agente firmante")
    s.add_argument(
        "--c2pa-technical-manifest",
        default=None,
        help="Manifiesto tecnico existente cuyo SHA-256 se incluira en la asercion C2PA",
    )
    s.add_argument("--proof-key", default=None, help="Clave privada Ed25519 para ProbRAW Proof")
    s.add_argument("--proof-public-key", default=None, help="Clave publica Ed25519 para ProbRAW Proof")
    s.add_argument("--proof-key-passphrase", default=None, help="Frase de clave privada ProbRAW Proof")
    s.add_argument("--proof-signer-name", default=None, help="Nombre del firmante ProbRAW Proof")
    s.add_argument("--proof-signer-id", default=None, help="Identificador estable del firmante ProbRAW Proof")
    s.add_argument("--session-id", default=None, help="Identificador de sesion opcional para trazabilidad")

    s = sub.add_parser("proof-keygen")
    s.add_argument("--private-key", required=True, help="Ruta de la clave privada Ed25519 PEM")
    s.add_argument("--public-key", default=None, help="Ruta de la clave publica Ed25519 PEM")
    s.add_argument("--passphrase", default=None, help="Cifra la clave privada con esta frase")
    s.add_argument("--overwrite", action="store_true", help="Sobrescribe claves existentes")

    s = sub.add_parser("verify-proof")
    s.add_argument("proof", help="Sidecar .probraw.proof.json")
    s.add_argument("--tiff", default=None, help="TIFF final asociado")
    s.add_argument("--raw", default=None, help="RAW fuente para comprobar SHA-256")
    s.add_argument("--public-key", default=None, help="Clave publica esperada del firmante")

    s = sub.add_parser("validate-profile")
    s.add_argument("samples")
    s.add_argument("--profile", required=True)
    s.add_argument("--out", required=True)

    s = sub.add_parser("auto-profile-batch")
    s.add_argument("--charts", required=True, help="Directorio de capturas RAW/imagen con carta ColorChecker")
    s.add_argument("--targets", required=True, help="Directorio de RAW/imagenes objetivo para batch")
    s.add_argument("--recipe", required=True)
    s.add_argument("--reference", required=True)
    s.add_argument("--profile-out", required=True)
    s.add_argument("--profile-report", required=True)
    s.add_argument("--validation-report", default=None)
    s.add_argument("--out", required=True, help="Directorio de salida TIFF batch")
    s.add_argument("--workdir", required=True, help="Directorio de artefactos intermedios (detecciones/samples)")
    s.add_argument("--development-profile-out", default=None)
    s.add_argument("--calibrated-recipe-out", default=None)
    s.add_argument("--no-development-calibration", action="store_true")
    s.add_argument("--chart-type", choices=["colorchecker24", "it8"], default="colorchecker24")
    s.add_argument("--min-confidence", type=float, default=0.35)
    s.add_argument("--allow-fallback-detection", action="store_true")
    s.add_argument(
        "--validation-holdout-count",
        type=int,
        default=0,
        help="Reserva N capturas de carta para validacion cruzada independiente",
    )
    s.add_argument("--qa-mean-deltae2000-max", type=float, default=5.0)
    s.add_argument("--qa-max-deltae2000-max", type=float, default=10.0)
    s.add_argument(
        "--profile-validity-days",
        type=int,
        default=None,
        help="Vigencia opcional del perfil validado; al superarse se marca como expired",
    )
    s.add_argument("--camera", default=None)
    s.add_argument("--lens", default=None)
    s.add_argument(
        "--workers",
        type=int,
        default=None,
        help="Numero de trabajadores para la fase batch; 1 fuerza serial, 0/omitido usa auto",
    )
    s.add_argument(
        "--profile-workers",
        type=int,
        default=None,
        help="Trabajadores para revelar/detectar cartas; 1 fuerza serial, 0/omitido usa auto",
    )
    s.add_argument(
        "--profile-artifacts",
        choices=["full", "minimal"],
        default="full",
        help="Artefactos de perfilado: full escribe TIFF/overlays; minimal conserva JSON y omite imagenes intermedias",
    )
    s.add_argument("--cache-dir", default=None, help="Directorio de cache numerica de demosaico si la receta usa use_cache")

    s = sub.add_parser("compare-qa-reports")
    s.add_argument("reports", nargs="+", help="Reportes qa_session_report.json a comparar")
    s.add_argument("--out", default=None, help="JSON de salida opcional")

    s = sub.add_parser("check-tools")
    s.add_argument("--out", default=None, help="JSON de salida opcional")
    s.add_argument(
        "--strict",
        action="store_true",
        help="Devuelve codigo 2 si falta una herramienta externa requerida",
    )

    s = sub.add_parser("check-amaze")
    s.add_argument("--out", default=None, help="JSON de salida opcional")

    s = sub.add_parser("check-c2pa")
    s.add_argument("--out", default=None, help="JSON de salida opcional")

    s = sub.add_parser("check-display-profile")
    s.add_argument("--out", default=None, help="JSON de salida opcional")

    s = sub.add_parser("check-color-environment")
    s.add_argument("--out", default=None, help="JSON de salida opcional")
    s.add_argument(
        "--strict",
        action="store_true",
        help="Devuelve codigo 2 si la auditoria de color detecta advertencias",
    )

    s = sub.add_parser("tune-performance")
    s.add_argument("--out", default=None, help="JSON de salida opcional")
    s.add_argument(
        "--mode",
        choices=["conservative", "balanced", "aggressive"],
        default=None,
        help="Perfil de rendimiento a recomendar",
    )
    s.add_argument(
        "--write-system",
        action="store_true",
        help=f"Escribe la politica detectada en {SYSTEM_CONFIG_PATH}",
    )
    s.add_argument("--path", default=None, help="Ruta alternativa para escribir la politica")
    s.add_argument("--quiet", action="store_true", help="No imprime JSON si escribe configuracion")

    s = sub.add_parser("mtf-roi-worker", help=argparse.SUPPRESS)
    s.add_argument("request", help=argparse.SUPPRESS)
    s.add_argument("output", help=argparse.SUPPRESS)

    s = sub.add_parser("verify-c2pa")
    s.add_argument("input", help="TIFF final firmado")
    s.add_argument("--raw", required=True, help="RAW fuente para verificar SHA-256 declarado")
    s.add_argument("--manifest", default=None, help="batch_manifest.json externo de ProbRAW")

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser(_runtime_cli_name()).parse_args(argv)

    try:
        if args.command == "raw-info":
            result = raw_info(Path(args.input))
            print(json.dumps(to_json_dict(result), indent=2))
            return 0

        if args.command == "metadata":
            result = inspect_file_metadata(Path(args.input), include_c2pa=not bool(args.no_c2pa))
            if args.out:
                write_json(Path(args.out), result)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0

        if args.command == "develop":
            recipe = load_recipe(Path(args.recipe))
            requested_out_path = Path(args.out)
            requested_audit_path = Path(args.audit_linear) if args.audit_linear else None
            out_path = versioned_output_path(requested_out_path)
            audit_path = versioned_output_path(requested_audit_path) if requested_audit_path else None
            result = develop_controlled(
                Path(args.input),
                recipe,
                out_path,
                audit_path,
                cache_dir=Path(args.cache_dir) if args.cache_dir else None,
            )
            payload = {
                "run_context": gather_run_context(APP_VERSION),
                "requested_output_tiff": str(requested_out_path),
                "requested_audit_tiff": str(requested_audit_path) if requested_audit_path else None,
                "develop": to_json_dict(result),
            }
            print(json.dumps(payload, indent=2))
            return 0

        if args.command == "detect-chart":
            if args.manual_corners:
                result = detect_chart_from_corners(
                    Path(args.input),
                    corners=list(args.manual_corners),
                    chart_type=args.chart_type,
                )
            else:
                result = detect_chart(Path(args.input), chart_type=args.chart_type)
            write_json(Path(args.out), result)
            if args.preview:
                draw_detection_overlay(Path(args.input), result, Path(args.preview))
            print(json.dumps(to_json_dict(result), indent=2))
            return 0

        if args.command == "sample-chart":
            detection = chart_detection_from_json(Path(args.detection))
            reference = ReferenceCatalog.from_path(Path(args.reference))
            recipe = load_recipe(Path(args.recipe)) if args.recipe else None
            samples = sample_chart(
                Path(args.input),
                detection,
                reference,
                strategy=recipe.sampling_strategy if recipe else "trimmed_mean",
                trim_percent=recipe.sampling_trim_percent if recipe else 0.1,
                reject_saturated=recipe.sampling_reject_saturated if recipe else True,
            )
            write_json(Path(args.out), samples)
            print(json.dumps(to_json_dict(samples), indent=2))
            return 0

        if args.command == "build-profile":
            samples = sampleset_from_json(Path(args.samples))
            recipe = load_recipe(Path(args.recipe))
            result = build_profile(
                samples=samples,
                recipe=recipe,
                out_icc=Path(args.out),
                camera_model=args.camera,
                lens_model=args.lens,
            )
            write_json(Path(args.report), result)
            print(json.dumps(to_json_dict(result), indent=2))
            return 0

        if args.command == "export-cgats":
            samples = sampleset_from_json(Path(args.samples))
            write_samples_cgats(samples, Path(args.out))
            print(json.dumps({"output_cgats": str(Path(args.out))}, indent=2))
            return 0

        if args.command == "build-develop-profile":
            samples = sampleset_from_json(Path(args.samples))
            recipe = load_recipe(Path(args.recipe))
            result = build_development_profile(samples=samples, base_recipe=recipe)
            write_json(Path(args.out), result)
            save_recipe(result.calibrated_recipe, Path(args.calibrated_recipe))
            print(json.dumps(to_json_dict(result), indent=2))
            return 0

        if args.command == "batch-develop":
            recipe = load_recipe(Path(args.recipe))
            c2pa_config = None
            if not args.no_c2pa and (args.c2pa_sign or args.c2pa_cert or args.c2pa_key):
                if args.c2pa_cert and args.c2pa_key:
                    c2pa_config = C2PASignConfig(
                        cert_path=Path(args.c2pa_cert),
                        key_path=Path(args.c2pa_key),
                        alg=args.c2pa_alg,
                        timestamp_url=args.c2pa_timestamp_url,
                        signer_name=args.c2pa_signer_name,
                        technical_manifest_path=Path(args.c2pa_technical_manifest)
                        if args.c2pa_technical_manifest
                        else None,
                        session_id=args.session_id,
                    )
                elif args.c2pa_sign:
                    c2pa_config = c2pa_config_from_environment(
                        technical_manifest_path=Path(args.c2pa_technical_manifest)
                        if args.c2pa_technical_manifest
                        else None,
                        session_id=args.session_id,
                    )
                else:
                    raise RuntimeError("Configura --c2pa-cert y --c2pa-key, o usa --c2pa-sign con variables de entorno")
            elif not args.no_c2pa:
                c2pa_config = auto_c2pa_config(
                    technical_manifest_path=Path(args.c2pa_technical_manifest)
                    if args.c2pa_technical_manifest
                    else None,
                    session_id=args.session_id,
                    signer_name=args.c2pa_signer_name or "ProbRAW local signer",
                    timestamp_url=args.c2pa_timestamp_url,
                )

            if args.proof_key:
                proof_config = ProbRawProofConfig(
                    private_key_path=Path(args.proof_key),
                    public_key_path=Path(args.proof_public_key) if args.proof_public_key else None,
                    key_passphrase=args.proof_key_passphrase,
                    signer_name=args.proof_signer_name or "ProbRAW local signer",
                    signer_id=args.proof_signer_id or args.session_id,
                )
            else:
                proof_config = proof_config_from_environment()
            manifest = batch_develop(
                raws_dir=Path(args.input),
                recipe=recipe,
                profile_path=Path(args.profile) if args.profile else None,
                out_dir=Path(args.out),
                workers=args.workers,
                cache_dir=Path(args.cache_dir) if args.cache_dir else None,
                c2pa_config=c2pa_config,
                proof_config=proof_config,
                tiff_compression=args.tiff_compression,
                tiff_maxworkers=args.tiff_workers,
            )
            manifest_path = Path(args.out) / "batch_manifest.json"
            write_json(manifest_path, manifest)
            print(json.dumps(to_json_dict(manifest), indent=2))
            return 0

        if args.command == "proof-keygen":
            result = generate_ed25519_identity(
                private_key_path=Path(args.private_key),
                public_key_path=Path(args.public_key) if args.public_key else None,
                passphrase=args.passphrase,
                overwrite=bool(args.overwrite),
            )
            print(json.dumps(result, indent=2))
            return 0

        if args.command == "verify-proof":
            result = verify_probraw_proof(
                Path(args.proof),
                output_tiff=Path(args.tiff) if args.tiff else None,
                source_raw=Path(args.raw) if args.raw else None,
                public_key_path=Path(args.public_key) if args.public_key else None,
            )
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0 if result.get("status") == "ok" else 2

        if args.command == "validate-profile":
            samples = sampleset_from_json(Path(args.samples))
            result = validate_profile(samples=samples, profile_path=Path(args.profile))
            write_json(Path(args.out), result)
            print(json.dumps(to_json_dict(result), indent=2))
            return 0

        if args.command == "auto-profile-batch":
            recipe = load_recipe(Path(args.recipe))
            reference = ReferenceCatalog.from_path(Path(args.reference))
            result = auto_profile_batch(
                chart_captures_dir=Path(args.charts),
                target_captures_dir=Path(args.targets),
                recipe=recipe,
                reference=reference,
                profile_out=Path(args.profile_out),
                profile_report_out=Path(args.profile_report),
                validation_report_out=Path(args.validation_report) if args.validation_report else None,
                batch_out_dir=Path(args.out),
                work_dir=Path(args.workdir),
                development_profile_out=Path(args.development_profile_out) if args.development_profile_out else None,
                calibrated_recipe_out=Path(args.calibrated_recipe_out) if args.calibrated_recipe_out else None,
                calibrate_development=not bool(args.no_development_calibration),
                chart_type=args.chart_type,
                min_confidence=float(args.min_confidence),
                allow_fallback_detection=bool(args.allow_fallback_detection),
                validation_holdout_count=int(args.validation_holdout_count),
                qa_mean_delta_e2000_max=float(args.qa_mean_deltae2000_max),
                qa_max_delta_e2000_max=float(args.qa_max_deltae2000_max),
                profile_validity_days=args.profile_validity_days,
                camera_model=args.camera,
                lens_model=args.lens,
                workers=args.workers,
                cache_dir=Path(args.cache_dir) if args.cache_dir else None,
                profile_workers=args.profile_workers,
                profile_artifacts=args.profile_artifacts,
            )
            print(json.dumps(result, indent=2))
            return 0

        if args.command == "compare-qa-reports":
            result = compare_qa_reports([Path(p) for p in args.reports])
            if args.out:
                write_json(Path(args.out), result)
            print(json.dumps(result, indent=2))
            return 0

        if args.command == "check-tools":
            result = check_external_tools()
            if args.out:
                write_json(Path(args.out), result)
            print(json.dumps(result, indent=2))
            if args.strict and result.get("status") != "ok":
                return 2
            return 0

        if args.command == "check-amaze":
            result = check_amaze_backend()
            if args.out:
                write_json(Path(args.out), result)
            print(json.dumps(result, indent=2))
            return 0 if result.get("amaze_supported") else 2

        if args.command == "check-c2pa":
            result = check_c2pa_support()
            if args.out:
                write_json(Path(args.out), result)
            print(json.dumps(result, indent=2))
            return 0 if result.get("status") == "ok" else 2

        if args.command == "check-display-profile":
            detected = detect_system_display_profile()
            result = {
                "status": "ok" if detected is not None else "fallback_srgb",
                "platform": sys.platform,
                "monitor_profile": str(detected) if detected is not None else None,
                "label": display_profile_label(detected) if detected is not None else "sRGB",
            }
            if args.out:
                write_json(Path(args.out), result)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0

        if args.command == "check-color-environment":
            result = check_color_environment()
            if args.out:
                write_json(Path(args.out), result)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            if args.strict and result.get("status") != "ok":
                return 2
            return 0

        if args.command == "tune-performance":
            if args.write_system or args.path:
                target = Path(args.path) if args.path else SYSTEM_CONFIG_PATH
                result = write_performance_config(target, mode=args.mode)
                result["written_path"] = str(target)
                if args.out:
                    write_json(Path(args.out), result)
                if not args.quiet:
                    print(json.dumps(result, indent=2, ensure_ascii=False))
                return 0
            result = performance_report(mode=args.mode)
            if args.out:
                write_json(Path(args.out), result)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0

        if args.command == "mtf-roi-worker":
            from .analysis import mtf_roi

            return int(mtf_roi.main([args.request, args.output]))

        if args.command == "verify-c2pa":
            result = verify_c2pa_raw_link(
                signed_tiff=Path(args.input),
                source_raw=Path(args.raw),
                external_manifest_path=Path(args.manifest) if args.manifest else None,
            )
            print(json.dumps(result, indent=2))
            return 0 if result.get("status") == "ok" else 2

    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
