# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import typing

import pytest

from lancet.exceptions import LancetException
from lancet.gui.dialog_registry import DialogRegistry


class AcquireScenario(typing.NamedTuple):
    """Describes what happens inside a DialogRegistry.acquire() with-block."""

    body: typing.Callable[[DialogRegistry], None]
    expects_exception: type[BaseException] | None


def body_noop(_: DialogRegistry) -> None:
    """Body that does nothing. The lock should release cleanly when the with-block ends."""
    return None


def body_raises(_: DialogRegistry) -> None:
    """Body that raises an exception. The lock must still release in the finally branch."""
    raise RuntimeError("boom")


def body_disowns_during(dialogs: DialogRegistry) -> None:
    """Body that calls disown_if_present mid-block, mimicking Qt finished signal."""
    dialogs.disown_if_present("test-dialog")


ACQUIRE_BODY_SCENARIOS: dict[str, AcquireScenario] = {
    "noop_releases_lock": AcquireScenario(body=body_noop, expects_exception=None),
    "exception_in_body_still_releases_lock": AcquireScenario(body=body_raises, expects_exception=RuntimeError),
    "disown_during_body_then_clean_exit_releases_lock": AcquireScenario(
        body=body_disowns_during, expects_exception=None
    ),
}


def run_acquire_scenario(dialogs: DialogRegistry, scenario: AcquireScenario) -> None:
    """Drive a single AcquireScenario through DialogRegistry.acquire(), asserting on raised exceptions."""
    if scenario.expects_exception is None:
        with dialogs.acquire("test-dialog"):
            scenario.body(dialogs)
    else:
        with pytest.raises(scenario.expects_exception):
            with dialogs.acquire("test-dialog"):
                scenario.body(dialogs)


class TestDialogRegistryAcquireReleaseContract:
    """DialogRegistry.acquire() must always release the name on exit, even on exceptions."""

    @pytest.mark.parametrize("scenario", ACQUIRE_BODY_SCENARIOS.values(), ids=ACQUIRE_BODY_SCENARIOS.keys())
    def test_is_locked_clears_after_exit(self, scenario: AcquireScenario) -> None:
        """For every with-block body, is_locked() must return False after the block ends."""
        dialogs = DialogRegistry()

        run_acquire_scenario(dialogs, scenario)

        assert dialogs.is_locked() is False

    @pytest.mark.parametrize("scenario", ACQUIRE_BODY_SCENARIOS.values(), ids=ACQUIRE_BODY_SCENARIOS.keys())
    def test_reacquirable_after_exit(self, scenario: AcquireScenario) -> None:
        """After the with-block ends, the same name can be acquired again without error."""
        dialogs = DialogRegistry()

        run_acquire_scenario(dialogs, scenario)

        with dialogs.acquire("test-dialog"):
            assert dialogs.is_locked() is True
        assert dialogs.is_locked() is False


class TestDialogRegistryIsLockedDuring:
    """While the with-block runs, is_locked() must report True."""

    def test_is_locked_true_inside_block(self) -> None:
        """is_locked() returns True for the duration of the with-block body."""
        dialogs = DialogRegistry()

        with dialogs.acquire("inside-check"):
            assert dialogs.is_locked() is True


class TestDialogRegistryRejectsDoubleAcquire:
    """Re-entering acquire() with a name that is already registered must raise."""

    def test_double_acquire_same_name_raises(self) -> None:
        """Acquiring the same name twice raises LancetException."""
        dialogs = DialogRegistry()

        with dialogs.acquire("twice"):
            with pytest.raises(LancetException):
                with dialogs.acquire("twice"):
                    pass


class TestDialogRegistryIdempotentDisown:
    """disown_if_present must be idempotent: safe to call when absent, safe to call after clean exit."""

    def test_disown_unknown_name_is_noop(self) -> None:
        """Calling disown_if_present with a never-registered name does not raise."""
        dialogs = DialogRegistry()

        dialogs.disown_if_present("never-held")
        assert dialogs.is_locked() is False

    def test_disown_after_clean_exit_is_safe(self) -> None:
        """Calling disown_if_present after the with-block has already exited must not raise."""
        dialogs = DialogRegistry()

        with dialogs.acquire("late-disown"):
            pass
        # The finally branch has already disowned; a late disown is a no-op.
        dialogs.disown_if_present("late-disown")
        assert dialogs.is_locked() is False


class TestDialogRegistryMultiName:
    """DialogRegistry supports holding multiple different names simultaneously."""

    def test_two_different_names_can_be_held_simultaneously(self) -> None:
        """Two distinct names may both be held at once via nested with-blocks."""
        dialogs = DialogRegistry()

        with dialogs.acquire("first"):
            with dialogs.acquire("second"):
                assert dialogs.is_locked() is True

        assert dialogs.is_locked() is False
