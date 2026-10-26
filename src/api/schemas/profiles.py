from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CopyPart = Literal["cookies", "history", "site_data", "passwords", "tabs", "workflows"]


class ProfileCreate(BaseModel):
    name: str
    proxy: str | None = None
    os_type: str = "windows"
    timezone: str | None = Field(
        None, description="IANA timezone, e.g. Asia/Ho_Chi_Minh. Unset = follow the IP"
    )
    locale: str | None = Field(
        None, description="language-REGION, e.g. vi-VN. Unset = follow the IP"
    )
    engine: str = Field(
        "camoufox",
        description="camoufox (Firefox) or chrome (experimental, fingerprint-chromium). "
        "Fixed once the profile is created",
    )


class ProfileClone(BaseModel):
    name: str | None = Field(
        None,
        description='New profile name; default "<name>-copy". With count > 1 it is the base '
        "of the names: <name>-1, <name>-2... (numbers in use are skipped)",
    )
    count: int = Field(1, ge=1, le=50, description="How many copies to make")
    # "copy" in JSON; BaseModel already has a copy() method.
    model_config = ConfigDict(populate_by_name=True)
    parts: list[CopyPart] = Field(
        default_factory=list,
        alias="copy",
        description="What to copy besides the settings: cookies, history (and bookmarks), "
        "site_data (localStorage, IndexedDB, site permissions), passwords, tabs (the source "
        "must be stopped for these), workflows (a copy of each workflow recorded in the "
        "profile, for every clone). The copy always gets a new fingerprint.",
    )
    copy_data: bool = Field(False, description="Shorthand: copy every browser data part")


class ProfileUpdate(BaseModel):
    """All fields optional — only supplied fields are changed."""

    name: str | None = None
    proxy: str | None = None
    os_type: str | None = None
    timezone: str | None = Field(None, description='"" switches back to automatic')
    locale: str | None = Field(None, description='"" switches back to automatic')
    engine: str | None = Field(None, description="Cannot be changed; only the current value")


class ProfileResponse(BaseModel):
    name: str
    proxy: str | None
    os_type: str
    timezone: str | None = None
    locale: str | None = None
    engine: str = "camoufox"
    data_dir: str
    is_running: bool


class ProfileListResponse(BaseModel):
    profiles: list[ProfileResponse]
    total: int


class DataDirResponse(BaseModel):
    name: str
    data_dir: str
    exists: bool


class ExportRequest(BaseModel):
    export_dir: str
    include_data: bool = True


class ExportResponse(BaseModel):
    success: bool
    zip_path: str | None = None
    error: str | None = None


class ImportRequest(BaseModel):
    zip_path: str
    overwrite: bool = False


class ImportResponse(BaseModel):
    success: bool
    profile_name: str | None = None
    error: str | None = None


class CookieImportRequest(BaseModel):
    """Cookies as JSON (Cookie-Editor / EditThisCookie / Playwright) or Netscape text."""

    content: str


class CookieImportResponse(BaseModel):
    success: bool
    imported: int = 0
    error: str | None = None


class FingerprintResponse(BaseModel):
    name: str
    exists: bool
    os: str | None = None
    platform: str | None = None
    screen: str | None = None
    hardware_concurrency: int | None = None


class CloneResponse(BaseModel):
    profiles: list[ProfileResponse]
    total: int
    workflows_copied: int = 0
