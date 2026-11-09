"""Simple JSON model registry for ML artifacts."""

from __future__ import annotations

import json
import pickle
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class ModelRegistryEntry:
    """Tracked model version metadata."""

    model_id: str
    model_name: str
    model_type: str
    artifact_path: str
    feature_list_path: str
    metrics_path: str
    features_used: tuple[str, ...]
    training_start_date: str | None
    training_end_date: str | None
    validation_start_date: str | None
    validation_end_date: str | None
    created_at: str
    active_status: bool = False
    metrics: dict[str, Any] = field(default_factory=dict)


class ModelRegistry:
    """Persist and load ML model registry entries."""

    def __init__(self, registry_path: Path) -> None:
        self.registry_path = registry_path

    def register_model(
        self,
        *,
        model_name: str,
        model_type: str,
        artifact_path: Path,
        feature_list_path: Path,
        metrics_path: Path,
        features_used: tuple[str, ...],
        training_start_date: str | None = None,
        training_end_date: str | None = None,
        validation_start_date: str | None = None,
        validation_end_date: str | None = None,
        active_status: bool = False,
    ) -> ModelRegistryEntry:
        """Add a model version and optionally make it active."""

        if not artifact_path.exists():
            raise FileNotFoundError(f"Model artifact does not exist: {artifact_path}")
        if not feature_list_path.exists():
            raise FileNotFoundError(f"Feature list does not exist: {feature_list_path}")
        if not metrics_path.exists():
            raise FileNotFoundError(f"Metrics file does not exist: {metrics_path}")

        payload = self._read_registry()
        if active_status:
            for entry in payload["models"]:
                entry["active_status"] = False

        metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
        entry = ModelRegistryEntry(
            model_id=str(uuid4()),
            model_name=model_name,
            model_type=model_type,
            artifact_path=str(artifact_path),
            feature_list_path=str(feature_list_path),
            metrics_path=str(metrics_path),
            features_used=features_used,
            training_start_date=training_start_date,
            training_end_date=training_end_date,
            validation_start_date=validation_start_date,
            validation_end_date=validation_end_date,
            created_at=datetime.now(timezone.utc).isoformat(),
            active_status=active_status,
            metrics=metrics,
        )
        payload["models"].append(_entry_to_dict(entry))
        self._write_registry(payload)
        return entry

    def list_models(self) -> list[ModelRegistryEntry]:
        """Return all registered model versions."""

        payload = self._read_registry()
        return [_entry_from_dict(item) for item in payload["models"]]

    def get_model(self, model_id: str) -> ModelRegistryEntry:
        """Return one registered model by ID."""

        for entry in self.list_models():
            if entry.model_id == model_id:
                return entry
        raise KeyError(f"Unknown model_id: {model_id}")

    def set_active(self, model_id: str) -> ModelRegistryEntry:
        """Make an existing model active, enabling rollback to prior versions."""

        payload = self._read_registry()
        found: dict[str, Any] | None = None
        for entry in payload["models"]:
            entry["active_status"] = entry["model_id"] == model_id
            if entry["active_status"]:
                found = entry
        if found is None:
            raise KeyError(f"Unknown model_id: {model_id}")
        self._write_registry(payload)
        return _entry_from_dict(found)

    def active_model(self) -> ModelRegistryEntry | None:
        """Return the active model entry, if one is set."""

        for entry in self.list_models():
            if entry.active_status:
                return entry
        return None

    def load_model_artifact(self, model_id: str) -> Any:
        """Load a registered pickle artifact."""

        entry = self.get_model(model_id)
        with Path(entry.artifact_path).open("rb") as handle:
            return pickle.load(handle)

    def _read_registry(self) -> dict[str, Any]:
        if not self.registry_path.exists():
            return {"models": []}
        return json.loads(self.registry_path.read_text(encoding="utf-8"))

    def _write_registry(self, payload: dict[str, Any]) -> None:
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        self.registry_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _entry_to_dict(entry: ModelRegistryEntry) -> dict[str, Any]:
    return {
        "model_id": entry.model_id,
        "model_name": entry.model_name,
        "model_type": entry.model_type,
        "artifact_path": entry.artifact_path,
        "feature_list_path": entry.feature_list_path,
        "metrics_path": entry.metrics_path,
        "features_used": list(entry.features_used),
        "training_start_date": entry.training_start_date,
        "training_end_date": entry.training_end_date,
        "validation_start_date": entry.validation_start_date,
        "validation_end_date": entry.validation_end_date,
        "created_at": entry.created_at,
        "active_status": entry.active_status,
        "metrics": entry.metrics,
    }


def _entry_from_dict(data: dict[str, Any]) -> ModelRegistryEntry:
    return ModelRegistryEntry(
        model_id=data["model_id"],
        model_name=data["model_name"],
        model_type=data["model_type"],
        artifact_path=data["artifact_path"],
        feature_list_path=data["feature_list_path"],
        metrics_path=data["metrics_path"],
        features_used=tuple(data.get("features_used", ())),
        training_start_date=data.get("training_start_date"),
        training_end_date=data.get("training_end_date"),
        validation_start_date=data.get("validation_start_date"),
        validation_end_date=data.get("validation_end_date"),
        created_at=data["created_at"],
        active_status=bool(data.get("active_status", False)),
        metrics=dict(data.get("metrics", {})),
    )
