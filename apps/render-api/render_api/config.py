import os
import shutil
from dataclasses import dataclass
from pathlib import Path

MIB = 1024 * 1024


@dataclass(frozen=True)
class Settings:
    renderer: Path
    data_dir: Path
    token: str = ""
    workers: int = 1
    max_jobs: int = 16
    max_upload_bytes: int = 128 * MIB
    max_unpacked_bytes: int = 512 * MIB
    max_archive_entries: int = 512
    max_output_bytes: int = 256 * MIB
    max_output_files: int = 128
    timeout_seconds: float = 300
    upload_timeout_seconds: float = 60
    max_log_bytes: int = 64 * 1024

    def __post_init__(self):
        if not 1 <= self.workers <= 8 or not 1 <= self.max_jobs <= 1024:
            raise ValueError("workers must be 1..8 and max_jobs must be 1..1024")
        limits = (
            self.max_upload_bytes,
            self.max_unpacked_bytes,
            self.max_archive_entries,
            self.max_output_bytes,
            self.max_output_files,
            self.max_log_bytes,
        )
        if min(limits) <= 0 or not 0 < self.timeout_seconds <= 3600:
            raise ValueError("limits must be positive; render timeout must be <= 3600 seconds")
        if not 0 < self.upload_timeout_seconds <= 3600:
            raise ValueError("upload timeout must be 0..3600 seconds")

    @classmethod
    def from_env(cls):
        executable = "idml-render.exe" if os.name == "nt" else "idml-render"
        default = shutil.which(executable) or str(Path("target/release") / executable)
        return cls(
            renderer=Path(os.getenv("IDML_RENDER_BIN", default)).resolve(),
            data_dir=Path(os.getenv("IDML_API_DATA_DIR", "outputs/render-api")).resolve(),
            token=os.getenv("IDML_API_TOKEN", ""),
            workers=int(os.getenv("IDML_API_RENDER_WORKERS", "1")),
            max_jobs=int(os.getenv("IDML_API_MAX_JOBS", "16")),
            timeout_seconds=float(os.getenv("IDML_API_RENDER_TIMEOUT", "300")),
        )
