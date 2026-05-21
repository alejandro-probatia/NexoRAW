from __future__ import annotations

from ._imports import *  # noqa: F401,F403


class EditHistoryMixin:
    _EDIT_HISTORY_LIMIT = 80

    def _initialize_edit_history(self) -> None:
        self._edit_undo_stack = [self._capture_edit_state()]
        self._edit_redo_stack = []
        self._update_edit_actions()

    def _reset_edit_history_to_current(self) -> None:
        if not hasattr(self, "combo_raw_developer"):
            return
        self._initialize_edit_history()

    def _capture_edit_state(self) -> dict[str, Any]:
        recipe = self._build_effective_recipe() if hasattr(self, "_build_effective_recipe") else Recipe()
        crop_rect = getattr(self, "_image_crop_rect", None)
        crop = list(crop_rect) if isinstance(crop_rect, tuple) else None
        crop_base_size = getattr(self, "_image_crop_base_size", None)
        crop_normalized = getattr(self, "_image_crop_normalized_rect", None)
        return {
            "recipe": asdict(recipe),
            "render_adjustments": self._render_adjustment_state()
            if hasattr(self, "_render_adjustment_state")
            else {},
            "detail_adjustments": self._detail_adjustment_state()
            if hasattr(self, "_detail_adjustment_state")
            else {},
            "image_crop_rect": crop,
            "image_crop_base_size": list(crop_base_size) if isinstance(crop_base_size, tuple) else None,
            "image_crop_normalized_rect": list(crop_normalized) if isinstance(crop_normalized, tuple) else None,
            "viewer_rotation": float(getattr(self, "_viewer_rotation", 0.0) or 0.0),
            "color_samples": self._color_picker_samples_state()
            if hasattr(self, "_color_picker_samples_state")
            else {},
        }

    def _edit_state_key(self, state: dict[str, Any]) -> str:
        return json.dumps(state, sort_keys=True, ensure_ascii=False, default=str)

    def _edit_state_preview_key(self, state: dict[str, Any]) -> str:
        preview_state = {
            "recipe": state.get("recipe") if isinstance(state.get("recipe"), dict) else {},
            "render_adjustments": state.get("render_adjustments")
            if isinstance(state.get("render_adjustments"), dict)
            else {},
            "detail_adjustments": state.get("detail_adjustments")
            if isinstance(state.get("detail_adjustments"), dict)
            else {},
        }
        return self._edit_state_key(preview_state)

    def _push_edit_history_snapshot(self, label: str = "") -> None:
        if bool(getattr(self, "_applying_edit_history", False)):
            return
        if int(getattr(self, "_suspend_edit_history", 0) or 0) > 0:
            return
        if not hasattr(self, "_edit_undo_stack"):
            return
        state = self._capture_edit_state()
        current = self._edit_undo_stack[-1] if self._edit_undo_stack else None
        if current is not None and self._edit_state_key(current) == self._edit_state_key(state):
            self._update_edit_actions()
            return
        self._edit_undo_stack.append(state)
        limit = int(getattr(self, "_EDIT_HISTORY_LIMIT", 80) or 80)
        if len(self._edit_undo_stack) > limit:
            self._edit_undo_stack = self._edit_undo_stack[-limit:]
        self._edit_redo_stack = []
        self._update_edit_actions()
        if label:
            self._last_edit_history_label = str(label)

    def _restore_edit_state(self, state: dict[str, Any]) -> None:
        previous_state = self._capture_edit_state()
        raw_suspend = int(getattr(self, "_suspend_raw_export_autosave", 0) or 0)
        render_suspend = int(getattr(self, "_suspend_render_adjustment_autosave", 0) or 0)
        detail_suspend = int(getattr(self, "_suspend_detail_adjustment_autosave", 0) or 0)
        history_suspend = int(getattr(self, "_suspend_edit_history", 0) or 0)
        self._applying_edit_history = True
        self._suspend_raw_export_autosave = raw_suspend + 1
        self._suspend_render_adjustment_autosave = render_suspend + 1
        self._suspend_detail_adjustment_autosave = detail_suspend + 1
        self._suspend_edit_history = history_suspend + 1
        try:
            recipe_payload = state.get("recipe") if isinstance(state.get("recipe"), dict) else {}
            self._apply_recipe_to_controls(Recipe(**recipe_payload))
            render_state = state.get("render_adjustments")
            self._apply_render_adjustment_state(
                render_state if isinstance(render_state, dict) else self._default_render_adjustment_state()
            )
            detail_state = state.get("detail_adjustments")
            self._apply_detail_adjustment_state(
                detail_state if isinstance(detail_state, dict) else self._default_detail_adjustment_state()
            )
            crop = state.get("image_crop_rect")
            if isinstance(crop, (list, tuple)) and len(crop) >= 4:
                self._image_crop_rect = tuple(int(round(float(v))) for v in crop[:4])
            else:
                self._image_crop_rect = None
            base_size = state.get("image_crop_base_size")
            if isinstance(base_size, (list, tuple)) and len(base_size) >= 2:
                self._image_crop_base_size = (int(base_size[0]), int(base_size[1]))
            else:
                self._image_crop_base_size = None
            normalized = state.get("image_crop_normalized_rect")
            if isinstance(normalized, (list, tuple)) and len(normalized) >= 4:
                self._image_crop_normalized_rect = tuple(float(v) for v in normalized[:4])
            else:
                self._image_crop_normalized_rect = None
            self._viewer_rotation = float(state.get("viewer_rotation", 0.0) or 0.0) % 360.0
            self._image_level_selection_active = False
            self._image_level_points = []
            self._viewer_zoom = 1.0
            if hasattr(self, "_sync_viewer_transform"):
                self._sync_viewer_transform()
            if hasattr(self, "_sync_image_tool_overlays"):
                self._sync_image_tool_overlays()
            if hasattr(self, "_update_viewer_interaction_cursor"):
                self._update_viewer_interaction_cursor()
            if "color_samples" in state and hasattr(self, "_restore_color_picker_samples_state"):
                sample_state = state.get("color_samples")
                self._restore_color_picker_samples_state(
                    sample_state if isinstance(sample_state, dict) else {},
                    persist=True,
                )
        finally:
            self._suspend_raw_export_autosave = raw_suspend
            self._suspend_render_adjustment_autosave = render_suspend
            self._suspend_detail_adjustment_autosave = detail_suspend
            self._suspend_edit_history = history_suspend
            self._applying_edit_history = False

        preview_changed = self._edit_state_preview_key(previous_state) != self._edit_state_preview_key(state)
        if preview_changed:
            self._invalidate_preview_cache()
            if getattr(self, "_original_linear", None) is not None:
                self._refresh_preview(force_final=True)
        if hasattr(self, "_schedule_render_adjustment_sidecar_persist"):
            self._schedule_render_adjustment_sidecar_persist(immediate=True)
        if hasattr(self, "_schedule_detail_adjustment_sidecar_persist"):
            self._schedule_detail_adjustment_sidecar_persist(immediate=True)
        if hasattr(self, "_schedule_raw_export_sidecar_persist"):
            self._schedule_raw_export_sidecar_persist(immediate=True)
        self._save_active_session(silent=True)

    def _edit_undo(self, _checked: bool = False) -> None:
        if len(getattr(self, "_edit_undo_stack", [])) <= 1:
            self._update_edit_actions()
            return
        current = self._edit_undo_stack.pop()
        self._edit_redo_stack.append(current)
        state = self._edit_undo_stack[-1]
        self._restore_edit_state(state)
        self._update_edit_actions()
        self._set_status(self.tr("Deshecho"))

    def _edit_redo(self, _checked: bool = False) -> None:
        if not getattr(self, "_edit_redo_stack", []):
            self._update_edit_actions()
            return
        state = self._edit_redo_stack.pop()
        self._edit_undo_stack.append(state)
        self._restore_edit_state(state)
        self._update_edit_actions()
        self._set_status(self.tr("Rehecho"))

    def _edit_clear_adjustments(self, _checked: bool = False) -> None:
        default_state = {
            "recipe": asdict(Recipe()),
            "render_adjustments": self._default_render_adjustment_state(),
            "detail_adjustments": self._default_detail_adjustment_state(),
            "image_crop_rect": None,
            "viewer_rotation": 0.0,
        }
        self._restore_edit_state(default_state)
        self._push_edit_history_snapshot("clear_adjustments")
        self._set_status(self.tr("Ajustes eliminados"))

    def _update_edit_actions(self) -> None:
        undo_enabled = len(getattr(self, "_edit_undo_stack", [])) > 1
        redo_enabled = bool(getattr(self, "_edit_redo_stack", []))
        action = getattr(self, "action_edit_undo", None)
        if action is not None:
            action.setEnabled(undo_enabled)
        action = getattr(self, "action_edit_redo", None)
        if action is not None:
            action.setEnabled(redo_enabled)

    def _add_edit_menu(self, menu_bar) -> None:
        menu_edit = menu_bar.addMenu(self.tr("Editar"))
        self.action_edit_undo = self._action(self.tr("Deshacer"), self._edit_undo, "Ctrl+Z")
        self.action_edit_redo = self._action(self.tr("Rehacer"), self._edit_redo, "Ctrl+Y")
        menu_edit.addAction(self.action_edit_undo)
        menu_edit.addAction(self.action_edit_redo)
        menu_edit.addSeparator()
        menu_edit.addAction(self._action(self.tr("Eliminar ajustes"), self._edit_clear_adjustments))
        menu_edit.aboutToShow.connect(self._update_edit_actions)
        self._update_edit_actions()
