import contextlib
import json
import os
import pathlib
import shutil
import threading
import time
from collections.abc import Callable, Collection

from ...core.config import DATA_DIR, PROFILES_FILE
from ...core.logging import get_logger
from ...models.profile import ENGINES, Profile
from ...utils.validation import (
    valid_or_none,
    validate_locale,
    validate_profile_name,
    validate_timezone,
)
from .clone_parts import PARTS, copy_parts
from .transfer import export_to_zip, import_from_zip, read_profile_meta

logger = get_logger("profile.manager")

MAX_CLONES = 50


# Windows keeps a file "in use" for a moment after the process holding it exits
# (and antivirus or the indexer may hold it briefly too).
_LOCK_RETRIES = 6
_LOCK_DELAY = 0.5


def _retry_locked(action: Callable[[], object]) -> None:
    for attempt in range(_LOCK_RETRIES):
        try:
            action()
            return
        except PermissionError:
            if attempt == _LOCK_RETRIES - 1:
                raise
            time.sleep(_LOCK_DELAY)


def _remove_tree(path: str) -> None:
    """Delete a profile's data directory, waiting out files still briefly locked."""
    for attempt in range(_LOCK_RETRIES):
        shutil.rmtree(path, ignore_errors=True)
        if not os.path.exists(path):
            return
        if attempt < _LOCK_RETRIES - 1:
            time.sleep(_LOCK_DELAY)
    logger.warning("Could not remove every file of %s; some are still in use", path)


class CloneError(Exception):
    """A profile could not be cloned; `status` is the HTTP status to report."""

    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


def _engine_or_default(value: object) -> str:
    return value if value in ENGINES else "camoufox"


def _replace(src: pathlib.Path, dst: pathlib.Path, attempts: int = 10) -> None:
    """os.replace, retried briefly: on Windows it fails with a sharing violation
    while another process (antivirus, indexer, a reader) has the target open."""
    for i in range(attempts):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if i == attempts - 1:
                raise
            time.sleep(0.02 * (i + 1))


class ProfileManager:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.profiles: dict[str, Profile] = {}
        self._load_profiles()
        pathlib.Path(DATA_DIR).mkdir(exist_ok=True, parents=True)

    def _find_by_casefold(self, name: str) -> str | None:
        """Return the existing profile key that case-folds to *name*, or None.

        Used to enforce case-insensitive uniqueness across all platforms so that
        a profiles.json exported on Linux (case-sensitive FS) can be imported on
        Windows/macOS (case-insensitive FS) without data-dir collisions.
        """
        lower = name.casefold()
        return next((k for k in self.profiles if k.casefold() == lower), None)

    def _data_path(self, name: str) -> str:
        return os.path.join(DATA_DIR, name)

    def _load_profiles(self) -> None:
        if pathlib.Path(PROFILES_FILE).exists():
            try:
                with pathlib.Path(PROFILES_FILE).open(encoding="utf-8") as f:
                    data = json.load(f)
                    for name, p_data in data.items():
                        if not validate_profile_name(name)[0] or p_data.get("name") != name:
                            logger.warning("Skipping profile with unsafe name: %r", name)
                            continue
                        clean_data = {
                            "name": p_data.get("name"),
                            "proxy": p_data.get("proxy"),
                            "os_type": p_data.get(
                                "os_type",
                                p_data.get("config", {}).get("os", "windows"),
                            ),
                            "timezone": valid_or_none(p_data.get("timezone"), validate_timezone),
                            "locale": valid_or_none(p_data.get("locale"), validate_locale),
                            "engine": _engine_or_default(p_data.get("engine")),
                        }
                        self.profiles[name] = Profile(**clean_data)
                logger.info("Loaded %d profiles", len(self.profiles))
            except Exception as e:
                logger.exception("Error loading profiles: %s", e)

    def save_profiles(self) -> None:
        """Atomic write: write to a temp file then os.replace."""
        path = pathlib.Path(PROFILES_FILE)
        tmp = path.with_suffix(".json.tmp")
        try:
            tmp.write_text(
                json.dumps(
                    {name: p.to_dict() for name, p in self.profiles.items()},
                    indent=4,
                ),
                encoding="utf-8",
            )
            _replace(tmp, path)
            logger.debug("Profiles saved")
        except Exception as e:
            logger.exception("Error saving profiles: %s", e)
            with contextlib.suppress(OSError):
                tmp.unlink(missing_ok=True)

    def add_profile(
        self,
        name: str,
        proxy: str,
        os_type: str,
        timezone: str | None = None,
        locale: str | None = None,
        engine: str = "camoufox",
    ) -> bool:
        with self._lock:
            if self._find_by_casefold(name) is not None:
                return False
            # Create directory before touching profiles.json so a mkdir failure
            # does not leave an entry with no data dir on disk.
            try:
                pathlib.Path(self._data_path(name)).mkdir(exist_ok=True, parents=True)
            except OSError as e:
                logger.warning("Could not create data dir for %s: %s", name, e)
                return False
            self.profiles[name] = Profile(
                name=name,
                proxy=proxy or None,
                os_type=os_type,
                timezone=timezone or None,
                locale=locale or None,
                engine=engine,
            )
            self.save_profiles()
            logger.info("Created profile: %s", name)
            return True

    def update_profile(
        self,
        original_name: str,
        new_name: str,
        new_proxy: str,
        new_os: str,
        new_timezone: str | None = None,
        new_locale: str | None = None,
    ) -> bool:
        """Replace every field; a None/empty timezone or locale means automatic."""
        with self._lock:
            if original_name not in self.profiles:
                return False

            if new_name != original_name:
                # Case-insensitive uniqueness: a case-only rename of the profile
                # itself is allowed; renaming to another profile's casefold is not.
                conflicting = self._find_by_casefold(new_name)
                if conflicting is not None and conflicting != original_name:
                    return False

            # Rename the data directory BEFORE mutating in-memory state so that
            # an OSError leaves memory and JSON untouched.
            if new_name != original_name:
                old_dir = pathlib.Path(self._data_path(original_name))
                new_dir = pathlib.Path(self._data_path(new_name))
                if old_dir.exists():
                    if new_dir.exists():
                        # On case-insensitive filesystems (Windows/macOS) a
                        # case-only rename sees the target as existing because
                        # both paths point to the same directory entry.  Allow
                        # the rename only in that situation.
                        try:
                            same = old_dir.samefile(new_dir)
                        except OSError:
                            same = False
                        if not same:
                            # Refuse: do NOT delete potential user data.
                            logger.warning(
                                "Cannot rename %s -> %s: target data dir already exists",
                                original_name,
                                new_name,
                            )
                            return False
                    try:
                        _retry_locked(lambda: old_dir.rename(new_dir))
                    except OSError as e:
                        logger.warning("Could not rename data dir for %s: %s", original_name, e)
                        return False

            profile = self.profiles[original_name]
            profile.name = new_name
            profile.proxy = new_proxy or None
            profile.os_type = new_os
            profile.timezone = new_timezone or None
            profile.locale = new_locale or None

            if new_name != original_name:
                del self.profiles[original_name]
                self.profiles[new_name] = profile

            self.save_profiles()
            logger.info("Updated profile: %s -> %s", original_name, new_name)
            return True

    def delete_profile(self, name: str) -> bool:
        with self._lock:
            if name not in self.profiles:
                return False
            del self.profiles[name]
            self.save_profiles()
            # Inside the lock: a profile re-created under the same (or, on a
            # case-insensitive file system, a case-variant) name must not have
            # its fresh data dir removed by this delete.
            _remove_tree(self._data_path(name))
        logger.info("Deleted profile: %s", name)
        return True

    def clone_name(self, source: str) -> str:
        """A free name for a copy: "<source>-copy", then "<source>-copy-2"..."""
        with self._lock:
            base = f"{source[:56]}-copy"  # room for "-copy-NN" within 64 characters
            name, n = base, 1
            while self._find_by_casefold(name) is not None:
                n += 1
                name = f"{base}-{n}"
            return name

    def _name_free(self, name: str) -> bool:
        if self._find_by_casefold(name) is not None:
            return False
        data = pathlib.Path(self._data_path(name))
        return not (data.exists() and any(data.iterdir()))

    def clone_names(self, base: str, count: int) -> list[str]:
        """Names for `count` copies: `base` itself for one, else base-1, base-2...
        skipping names already taken (or left with a data folder)."""
        if count <= 1:
            return [base]
        stem = base[:60]  # room for "-NNN" within 64 characters
        names: list[str] = []
        with self._lock:
            i = 0
            while len(names) < count:
                i += 1
                if self._name_free(candidate := f"{stem}-{i}"):
                    names.append(candidate)
        return names

    def clone_profiles(
        self, source: str, names: list[str], parts: Collection[str] = ()
    ) -> list[Profile]:
        """Clone `source` once per name, in order. A failure part way keeps the copies
        already made and says how many there are."""
        if not 1 <= len(names) <= MAX_CLONES:
            raise CloneError(f"Make between 1 and {MAX_CLONES} copies at a time")
        made: list[Profile] = []
        for name in names:
            try:
                made.append(self.clone_profile(source, name, parts))
            except CloneError as e:
                if not made:
                    raise
                raise CloneError(
                    f"Created {len(made)} of {len(names)} copies, then: {e}", e.status
                ) from e
        return made

    def clone_profile(self, source: str, new_name: str, parts: Collection[str] = ()) -> Profile:
        """Create `new_name` with the settings of `source` and a fingerprint of its own.

        `parts` picks the browser data to copy as well (clone_parts.PARTS: cookies,
        history, site_data, passwords, tabs); the caller must make sure the source
        browser is stopped when any is given. Raises CloneError.
        """
        if unknown := set(parts) - set(PARTS):
            raise CloneError(f"Unknown part to copy: {', '.join(sorted(unknown))}")
        with self._lock:
            original = self.profiles.get(source)
            if original is None:
                raise CloneError(f"Profile '{source}' not found", status=404)
            if (existing := self._find_by_casefold(new_name)) is not None:
                raise CloneError(f"Profile '{existing}' already exists", status=409)
            src_dir = pathlib.Path(self._data_path(source))
            dst_dir = pathlib.Path(self._data_path(new_name))
            if dst_dir.exists() and any(dst_dir.iterdir()):
                # Data left by a deleted profile: never mix it into the clone.
                raise CloneError(f"A data folder for '{new_name}' already exists", status=409)
            try:
                dst_dir.mkdir(parents=True, exist_ok=True)
                if parts and src_dir.is_dir():
                    copy_parts(src_dir, dst_dir, original.engine, parts)
            except OSError as e:
                shutil.rmtree(dst_dir, ignore_errors=True)
                raise CloneError(f"Could not copy the browser data: {e}", status=500) from e
            clone = Profile(
                name=new_name,
                proxy=original.proxy,
                os_type=original.os_type,
                timezone=original.timezone,
                locale=original.locale,
                engine=original.engine,
            )
            self.profiles[new_name] = clone
            self.save_profiles()
        logger.info(
            "Cloned profile %s -> %s (copied: %s)", source, new_name, ", ".join(parts) or "-"
        )
        return clone

    def list_profiles(self) -> list[Profile]:
        with self._lock:
            return list(self.profiles.values())

    def export_profile(
        self,
        name: str,
        export_path: str,
        include_data: bool = True,
    ) -> tuple[bool, str]:
        with self._lock:
            if name not in self.profiles:
                return False, "Profile not found"
            profile = self.profiles[name]
            data_path = self._data_path(name)
        return export_to_zip(profile, data_path, export_path, include_data)

    def import_profile(
        self,
        zip_path: str,
        overwrite: bool = False,
    ) -> tuple[bool, str]:
        # Decide before extracting: an archive must not write into an existing
        # profile's data unless overwriting, and an overwrite that changes the
        # engine starts from an empty directory (the engines' data do not mix).
        meta = read_profile_meta(zip_path) or {}
        name = meta.get("name")
        with self._lock:
            # Case-insensitive collision check: find any existing profile whose
            # name casefolds to the imported name so the check is consistent on
            # all platforms (Windows/macOS case-insensitive FS, Linux sensitive).
            existing_key = self._find_by_casefold(name) if name else None
            if existing_key is not None:
                if not overwrite:
                    return False, f"Profile '{name}' already exists"
                if (meta.get("engine") or "camoufox") != self.profiles[existing_key].engine:
                    shutil.rmtree(self._data_path(existing_key), ignore_errors=True)

            success, result = import_from_zip(zip_path, DATA_DIR)
            if not success:
                return False, result

            profile = result

            # An overwrite under a different case replaces the old entry rather
            # than leaving two names for one data directory.
            if existing_key is not None and existing_key != profile.name:
                old_dir = pathlib.Path(self._data_path(existing_key))
                new_dir = pathlib.Path(self._data_path(profile.name))
                if old_dir.exists() and not (new_dir.exists() and old_dir.samefile(new_dir)):
                    shutil.rmtree(old_dir, ignore_errors=True)
                del self.profiles[existing_key]
            self.profiles[profile.name] = profile
            self.save_profiles()
            logger.info("Registered imported profile: %s", profile.name)
            return True, profile.name
