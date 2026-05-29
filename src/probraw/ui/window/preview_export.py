from __future__ import annotations

from ._imports import *  # noqa: F401,F403


class PreviewExportMixin:
    def _rendered_tiff_srgb_u8(self, path: Path) -> np.ndarray:
        from PIL import ImageCms

        with Image.open(path) as img:
            icc = img.info.get("icc_profile")
            if icc:
                profile = ImageCms.ImageCmsProfile(io.BytesIO(icc))
                converted = ImageCms.profileToProfile(
                    img,
                    profile,
                    ImageCms.createProfile("sRGB"),
                    outputMode="RGB",
                )
            else:
                converted = img.convert("RGB")
            return np.asarray(converted, dtype=np.uint8).copy()

    def _expected_export_preview_srgb_u8(
        self,
        image: np.ndarray,
        *,
        recipe: Recipe,
        profile_path: Path | None,
    ) -> np.ndarray | None:
        if profile_path is None and is_generic_output_space(recipe.output_space):
            output_profile = ensure_generic_output_profile(
                recipe.output_space,
                directory=self._session_generic_profile_dir(),
            )
            return profiled_float_to_display_u8(image, output_profile, None)
        if profile_path is not None and not is_generic_output_space(recipe.output_space):
            return profiled_float_to_display_u8(image, profile_path, None)
        return None

    def _verify_export_preview_color_parity(
        self,
        output_tiff: Path,
        image: np.ndarray,
        *,
        recipe: Recipe,
        profile_path: Path | None,
    ) -> dict[str, float] | None:
        expected = self._expected_export_preview_srgb_u8(
            image,
            recipe=recipe,
            profile_path=profile_path,
        )
        if expected is None:
            return None
        actual = self._rendered_tiff_srgb_u8(output_tiff)
        if actual.shape != expected.shape:
            raise RuntimeError(
                "Fallo de paridad colorimetrica: el TIFF exportado no coincide en dimensiones "
                f"con la vista previa ({actual.shape} != {expected.shape})."
            )
        diff = np.abs(actual.astype(np.int16) - expected.astype(np.int16))
        mean_delta = float(np.mean(diff))
        p99_delta = float(np.percentile(diff, 99))
        max_delta = int(np.max(diff))
        metrics = {
            "mean_delta_u8": round(mean_delta, 4),
            "p99_delta_u8": round(p99_delta, 4),
            "max_delta_u8": float(max_delta),
        }
        if mean_delta > 1.5 or p99_delta > 4.0 or max_delta > 12:
            raise RuntimeError(
                "Fallo de paridad colorimetrica vista previa/exportacion: "
                f"media={mean_delta:.3f}, p99={p99_delta:.3f}, max={max_delta}. "
                "No se acepta el TIFF porque no reproduce la imagen visualizada."
            )
        return metrics

    def _on_save_preview(self) -> None:
        if self._preview_srgb is None:
            QtWidgets.QMessageBox.information(self, self.tr("Info"), "No hay vista previa para guardar.")
            return
        self._ensure_session_output_controls()
        default_out = str(self._session_default_outputs()["preview"])
        out_text, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            self.tr("Guardar vista previa PNG"),
            default_out,
            "PNG (*.png)",
        )
        if not out_text:
            return
        out = Path(out_text)
        if out.suffix.lower() != ".png":
            out = out.with_suffix(".png")
        out.parent.mkdir(parents=True, exist_ok=True)
        bgr = np.clip(np.round(self._preview_srgb[..., ::-1] * 255.0), 0, 255).astype(np.uint8)
        ok = cv2.imwrite(str(out), bgr)
        if not ok:
            QtWidgets.QMessageBox.critical(self, self.tr("Error"), self.tr("No se pudo guardar:") + f" {out}")
            return
        self._log_preview(f"Vista previa guardada en: {out}")
        self._set_status(self.tr("Vista previa guardada:") + f" {out}")
        self._save_active_session(silent=True)

    def _on_develop_selected(self) -> None:
        if hasattr(self, "_flush_render_adjustment_sidecar_persist"):
            self._flush_render_adjustment_sidecar_persist()
        if hasattr(self, "_flush_detail_adjustment_sidecar_persist"):
            self._flush_detail_adjustment_sidecar_persist()
        if self._selected_file is None:
            QtWidgets.QMessageBox.information(self, self.tr("Info"), self.tr("Selecciona un archivo para revelar."))
            return

        in_path = self._selected_file
        recipe = self._build_effective_recipe()
        profile_path = self._active_session_icc_for_settings()
        recipe = self._visible_export_recipe_for_color_management(
            recipe,
            input_profile_path=profile_path,
        )
        if not self._require_color_managed_recipe_for_ui(
            recipe,
            input_profile_path=profile_path,
            title=self.tr("Revelado sin gestión de color"),
        ):
            return
        defaults = self._session_default_outputs()
        default_out = str(defaults["tiff_dir"] / f"{in_path.stem}.tiff")
        out_text, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Guardar TIFF revelado",
            default_out,
            "TIFF (*.tif *.tiff)",
        )
        if not out_text:
            return
        requested_out_path = Path(out_text)
        out_path = versioned_output_path(requested_out_path)

        nl = self.slider_noise_luma.value() / 100.0
        nc = self.slider_noise_color.value() / 100.0
        sharpen = self.slider_sharpen.value() / 100.0
        radius = self.slider_radius.value() / 10.0
        ca_red, ca_blue = self._ca_scale_factors()
        render_adjustments = self._render_adjustment_kwargs()
        sidecar_detail_state = self._detail_adjustment_state()
        sidecar_render_state = self._render_adjustment_state()
        tiff_compression = self._selected_tiff_compression()
        tiff_maxworkers = self._selected_tiff_maxworkers()
        detail_adjustments = {
            "applied": True,
            "denoise_luminance": nl,
            "denoise_color": nc,
            "sharpen_amount": sharpen,
            "sharpen_radius": radius,
            "lateral_ca_red_scale": ca_red,
            "lateral_ca_blue_scale": ca_blue,
        }
        try:
            proof_config = self._resolve_proof_config_for_gui()
            c2pa_config = self._resolve_c2pa_config_for_gui()
        except Exception as exc:
            self._show_signature_config_error(exc)
            return

        def task():
            decode_recipe = Recipe(**asdict(recipe))
            decode_recipe.use_cache = True
            decode_cache_dir = self._preview_decode_cache_dir(in_path)
            image = (
                develop_standard_output_array(in_path, decode_recipe, cache_dir=decode_cache_dir)
                if profile_path is None and is_generic_output_space(recipe.output_space)
                else develop_image_array(in_path, decode_recipe, cache_dir=decode_cache_dir)
            )
            geometry_adjustments = self._output_geometry_adjustment_state(image)
            image = self._apply_output_adjustments(
                image,
                denoise_luma=nl,
                denoise_color=nc,
                sharpen_amount=sharpen,
                sharpen_radius=radius,
                lateral_ca_red_scale=ca_red,
                lateral_ca_blue_scale=ca_blue,
                render_adjustments=render_adjustments,
            )
            c2pa_render_adjustments = {
                "applied": True,
                **render_adjustments,
                "geometry": geometry_adjustments,
            }
            sidecar_render_payload = {
                **sidecar_render_state,
                "geometry": geometry_adjustments,
            }
            mode, proof_result = write_signed_profiled_tiff(
                out_path,
                image,
                source_raw=in_path,
                recipe=recipe,
                profile_path=profile_path,
                c2pa_config=c2pa_config,
                proof_config=proof_config,
                detail_adjustments=detail_adjustments,
                render_adjustments=c2pa_render_adjustments,
                render_context={
                    "entrypoint": "gui_single_develop",
                    "geometry": geometry_adjustments,
                    "tiff_compression": tiff_compression,
                    "tiff_maxworkers": tiff_maxworkers,
                },
                generic_profile_dir=self._session_generic_profile_dir(),
                tiff_compression=tiff_compression,
                tiff_maxworkers=tiff_maxworkers,
            )
            parity_metrics = self._verify_export_preview_color_parity(
                out_path,
                image,
                recipe=recipe,
                profile_path=profile_path,
            )
            rendered_profile_path = self._render_profile_path_for_recipe(
                recipe,
                input_profile_path=profile_path,
                color_management_mode=mode,
            )
            profile_id = self._active_development_profile_id
            development_profile = None
            if profile_id:
                profile_descriptor = self._development_profile_by_id(profile_id) or {}
                kind = str(profile_descriptor.get("kind") or "manual")
                development_profile = {
                    "id": profile_id,
                    "name": str(profile_descriptor.get("name") or profile_id),
                    "kind": kind,
                    "profile_type": str(profile_descriptor.get("profile_type") or self._adjustment_profile_type_for_kind(kind)),
                }
            sidecar = self._write_raw_settings_sidecar(
                in_path,
                recipe=recipe,
                development_profile=development_profile,
                detail_adjustments=sidecar_detail_state,
                render_adjustments=sidecar_render_payload,
                profile_path=rendered_profile_path,
                color_management_mode=mode,
                output_tiff=out_path,
                proof_path=Path(proof_result.proof_path),
                source_sha256=proof_result.raw_sha256,
                status="rendered",
            )
            return {
                "output_tiff": str(out_path),
                "requested_tiff": str(requested_out_path),
                "proof": proof_result.proof_path,
                "raw_sidecar": str(sidecar) if sidecar is not None else "",
                "color_parity": parity_metrics,
            }

        def on_success(payload) -> None:
            if payload.get("requested_tiff") != payload.get("output_tiff"):
                self._log_preview(f"Salida existente preservada; nueva version: {payload['output_tiff']}")
            self._log_preview(f"TIFF revelado: {payload['output_tiff']}")
            self._log_preview(f"ProbRAW Proof: {payload['proof']}")
            if payload.get("color_parity"):
                self._log_preview(f"Paridad color vista previa/exportacion: {payload['color_parity']}")
            if payload.get("raw_sidecar"):
                self._log_preview(f"Mochila ProbRAW: {payload['raw_sidecar']}")
            self._refresh_color_reference_thumbnail_markers()
            if not self._sync_selected_sidecar_to_preview(
                in_path,
                status_message=self.tr("Vista sincronizada con el TIFF revelado:") + f" {Path(str(payload['output_tiff'])).name}",
            ) and self._selected_file == in_path and self._original_linear is not None:
                self._refresh_preview()
            self._set_status(self.tr("Revelado completado:") + f" {payload['output_tiff']}")
            self._save_active_session(silent=True)

        self._start_background_task(self.tr("Revelado a TIFF"), task, on_success)
