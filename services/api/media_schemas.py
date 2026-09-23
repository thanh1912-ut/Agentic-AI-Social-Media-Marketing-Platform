"""HTTP schemas for uploaded, tenant-owned image assets."""

from pydantic import BaseModel, ConfigDict


class MediaAssetOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    filename: str
    mime_type: str
    size_bytes: int
    content_sha256: str
    width: int
    height: int
    alt_text: str
    content_path: str
