"""HTTP Pydantic schemas. These are the backend source for OpenAPI."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints


class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ApiFieldErrorOut(StrictSchema):
    field: str
    message: str


class ApiErrorOut(StrictSchema):
    code: str
    message: str
    field_errors: list[ApiFieldErrorOut] = Field(default_factory=list)
    request_id: str
    retryable: bool = False
    details: dict[str, Any] | None = None


class ApiErrorEnvelope(StrictSchema):
    error: ApiErrorOut


class RegisterRequest(StrictSchema):
    email: EmailStr
    password: Annotated[
        str, StringConstraints(min_length=8, max_length=200, strip_whitespace=False)
    ]
    full_name: str = Field(min_length=1, max_length=200)
    company_name: str = Field(min_length=1, max_length=200)
    industry: str | None = Field(default=None, max_length=120)


class AcceptInvitationRequest(StrictSchema):
    email: EmailStr
    password: (
        Annotated[
            str, StringConstraints(min_length=8, max_length=200, strip_whitespace=False)
        ]
        | None
    ) = None
    full_name: str | None = Field(default=None, min_length=1, max_length=200)


class LoginRequest(StrictSchema):
    email: EmailStr
    password: Annotated[
        str, StringConstraints(min_length=1, max_length=200, strip_whitespace=False)
    ]


class ForgotPasswordRequest(StrictSchema):
    email: EmailStr


class ResetPasswordRequest(StrictSchema):
    token: str = Field(min_length=20, max_length=200)
    new_password: Annotated[
        str, StringConstraints(min_length=8, max_length=200, strip_whitespace=False)
    ]


class ForgotPasswordResponse(StrictSchema):
    accepted: bool
    message: str


class ResetPasswordResponse(StrictSchema):
    ok: bool


class InvitationPreviewOut(StrictSchema):
    email: EmailStr
    workspace_name: str
    role: Literal["editor", "viewer"]
    expires_at: datetime


class UserOut(StrictSchema):
    id: str
    email: EmailStr
    full_name: str
    created_at: datetime


class WorkspaceOut(StrictSchema):
    id: str
    name: str
    slug: str
    industry: str | None = None
    role: Literal["owner", "editor", "viewer"]
    permissions: list[str]
    created_at: datetime


class LoginResponse(StrictSchema):
    user: UserOut
    workspaces: list[WorkspaceOut]
    active_workspace_id: str | None
    access_token: str
    expires_at: datetime


class SessionResponse(StrictSchema):
    user: UserOut
    workspaces: list[WorkspaceOut]
    active_workspace_id: str | None
    expires_at: datetime


class SelectWorkspaceRequest(StrictSchema):
    workspace_id: str


class InviteMemberRequest(StrictSchema):
    email: EmailStr
    role: Literal["editor", "viewer"]


class MemberOut(StrictSchema):
    id: str
    user: UserOut | None = None
    role: Literal["owner", "editor", "viewer"]
    status: Literal["active", "invited", "suspended"]
    invited_email: EmailStr | None = None
    invited_by: str | None = None
    invitation_expires_at: datetime | None = None
    joined_at: datetime | None = None


class InviteMemberResponse(StrictSchema):
    member: MemberOut
    outcome: Literal["sent", "email_failed", "already_member", "already_invited"]
    invite_url: str | None = None


class UploadLimits(StrictSchema):
    max_file_size_bytes: int
    max_files_per_request: int
    accepted_kinds: list[str]
    accepted_mime_types: list[str]
    max_text_characters: int = 20_000_000
    max_table_rows: int = 100_000
    max_table_columns: int = 256
    max_table_cells: int = 1_000_000
    max_pdf_pages: int = 200
    max_processing_seconds: int = 600
    ocr_enabled: bool = False


class DocumentError(StrictSchema):
    code: str
    message: str
    hint: str | None = None


class DocumentOut(StrictSchema):
    id: str
    workspace_id: str
    filename: str
    kind: str
    mime_type: str
    size: int
    status: str
    progress: int | None
    job_id: str | None = None
    error: DocumentError | None = None
    extracted: dict[str, Any] | None = None
    extraction_status: Literal[
        "pending", "extracted", "partial", "metadata_only", "failed"
    ] = "pending"
    knowledge_status: Literal["pending", "ready", "not_available", "failed"] = "pending"
    retrieval_mode: Literal["lexical", "semantic_vector", "not_available"] = (
        "not_available"
    )
    profile_status: Literal[
        "pending", "ready", "not_available", "not_applicable", "failed"
    ] = "not_applicable"
    selectable_for_content: bool = False
    uploaded_by: str
    uploaded_at: datetime
    processed_at: datetime | None = None


class ExtractedContentUnit(StrictSchema):
    kind: Literal["text", "table_row"]
    locator: str
    text: str | None = None
    headers: list[str] | None = None
    cells: list[str] | None = None


class ExtractedContentPage(StrictSchema):
    document_id: str
    parser_version: str
    source_version: str
    items: list[ExtractedContentUnit]
    next_cursor: str | None = None
    has_more: bool
    total_text_blocks: int
    total_tables: int
    total_rows: int
    warnings: list[str] = Field(default_factory=list)


class ReprocessDocumentRequest(StrictSchema):
    mode: Literal["document", "profile_only"] = "document"


class JobErrorOut(StrictSchema):
    code: str
    message: str
    hint: str | None = None
    retryable: bool = False


class JobStepOut(StrictSchema):
    key: str
    label: str
    status: str
    progress: int | None = None
    message: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: JobErrorOut | None = None


class JobOut(StrictSchema):
    id: str
    kind: str
    status: str
    title: str
    progress: int | None
    steps: list[JobStepOut]
    result: dict[str, Any] | None = None
    error: JobErrorOut | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    cancellable: bool


class AcceptedResponse(StrictSchema):
    job_id: str
    job: JobOut


class JobEventOut(StrictSchema):
    id: str
    job_id: str
    at: datetime
    type: str
    message: str
    progress: int | None = None


BrandFieldKey = Literal[
    "business_name",
    "industry",
    "description",
    "products",
    "target_audience",
    "brand_voice",
    "tone_keywords",
    "do_not_use",
    "competitors",
    "contact",
]


class ProfileProvenanceOut(StrictSchema):
    document_id: str
    document_name: str
    page: int | None = None
    sheet: str | None = None
    row: int | None = None
    quote: str
    char_start: int | None = None
    char_end: int | None = None


class ProfileAlternativeOut(StrictSchema):
    value: Any
    provenance: list[ProfileProvenanceOut] = Field(default_factory=list)


class BrandProfileFieldOut(StrictSchema):
    key: BrandFieldKey
    label: str
    value: Any = None
    state: Literal["suggested", "confirmed", "edited", "missing", "conflict"]
    confidence: float | None = Field(default=None, ge=0, le=1)
    provenance: list[ProfileProvenanceOut] = Field(default_factory=list)
    alternatives: list[ProfileAlternativeOut] = Field(default_factory=list)
    updated_at: datetime | None = None
    updated_by: str | None = None


class BrandProfileOut(StrictSchema):
    id: str
    workspace_id: str
    version: int
    profile_text: str | None = None
    profile_mode: Literal["legacy", "manual_text_v1"] = "legacy"
    applied_at: datetime | None = None
    applied_by: str | None = None
    business_name: BrandProfileFieldOut
    industry: BrandProfileFieldOut
    description: BrandProfileFieldOut
    products: BrandProfileFieldOut
    target_audience: BrandProfileFieldOut
    brand_voice: BrandProfileFieldOut
    tone_keywords: BrandProfileFieldOut
    do_not_use: BrandProfileFieldOut
    competitors: BrandProfileFieldOut
    contact: BrandProfileFieldOut
    confirmed_at: datetime | None = None
    confirmed_by: str | None = None
    completeness: float = Field(ge=0, le=1)
    updated_at: datetime


class ProfileFieldUpdate(StrictSchema):
    key: BrandFieldKey
    value: Any


class UpdateBrandProfileRequest(StrictSchema):
    version: int = Field(ge=1)
    profile_text: (
        Annotated[
            str,
            StringConstraints(strip_whitespace=False, min_length=1, max_length=20_000),
        ]
        | None
    ) = None
    fields: list[ProfileFieldUpdate] = Field(default_factory=list, max_length=10)
    confirm: bool = False


class ConfirmBrandProfileRequest(StrictSchema):
    version: int = Field(ge=1)


class BrandProfileRevisionOut(StrictSchema):
    id: str
    workspace_id: str
    version: int
    profile: BrandProfileOut
    confirmed_at: datetime | None = None
    confirmed_by: str | None = None
    created_at: datetime
    input_snapshot_id: str | None = None
    warnings: list[str] = Field(default_factory=list)
