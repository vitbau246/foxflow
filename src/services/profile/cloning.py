"""Clone a profile with the parts the user picked; shared by the API and the desktop app."""

from __future__ import annotations

from collections.abc import Collection
from typing import TYPE_CHECKING

from ...utils.validation import validate_profile_name
from ..browser.launcher import ProfileBusyError
from .clone_parts import PARTS
from .manager import CloneError

if TYPE_CHECKING:
    from ...interfaces.protocols import IBrowserLauncher, IProfileManager
    from ...models.profile import Profile
    from ..workflow.store import WorkflowStore

WORKFLOWS = "workflows"


class SourceRunningError(CloneError):
    """Browser data was asked for while the source profile's browser runs."""

    def __init__(self) -> None:
        super().__init__("Stop the browser before copying its data", status=409)


# Everything a clone can take, in the order the interfaces list it.
CHOICES = (*PARTS, WORKFLOWS)


def clone(
    pm: IProfileManager,
    bl: IBrowserLauncher,
    store: WorkflowStore,
    source: str,
    base: str,
    count: int = 1,
    copy: Collection[str] = (),
) -> tuple[list[Profile], int]:
    """Make `count` copies of `source` named from `base`.

    `copy` picks what comes along besides the settings: browser data parts
    (clone_parts.PARTS; the source must be stopped) and "workflows" (a copy of
    each workflow recorded in the source, for every clone). Returns the clones
    and how many workflows were copied. Raises CloneError.
    """
    if unknown := set(copy) - set(CHOICES):
        raise CloneError(f"Unknown part to copy: {', '.join(sorted(unknown))}")
    parts = [p for p in PARTS if p in copy]
    names = pm.clone_names(base, count)
    for name in names:
        valid, message = validate_profile_name(name)
        if not valid:
            raise CloneError(message)
    try:
        if parts:
            # Copying a running browser's files would give a torn copy.
            with bl.exclusive(source):
                clones = pm.clone_profiles(source, names, parts)
        else:
            clones = pm.clone_profiles(source, names)
    except ProfileBusyError as e:
        raise SourceRunningError from e
    workflows = 0
    if WORKFLOWS in copy:
        for profile in clones:
            workflows += len(store.copy_to_profile(source, profile.name))
    return clones, workflows
