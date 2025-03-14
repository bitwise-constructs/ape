import sys

import pytest

from ape import Project
from ape.managers.accounts import AccountManager
from ape.managers.project import LocalProject
from ape.utils import ManagerAccessMixin, create_tempdir
from ape_console._cli import CONSOLE_EXTRAS_FILENAME, ApeConsoleNamespace, console
from ape_console.plugin import custom_exception_handler


@pytest.fixture(autouse=True)
def mock_console(mocker):
    """Prevent console from actually launching."""
    return mocker.patch("ape_console._cli._launch_console")


def test_console_extras_uses_ape_namespace(mocker, mock_console):
    """
    Test that if console is given extras, those are included in the console
    but not as args to the extras files, as those files expect items from the
    default ape namespace.
    """
    namespace_patch = mocker.patch("ape_console._cli._create_namespace")
    accounts_custom = mocker.MagicMock()
    extras = {"accounts": accounts_custom}
    console(extra_locals=extras)
    actual = namespace_patch.call_args[1]
    assert actual["accounts"] == accounts_custom


def test_console_custom_project(mock_console):
    with create_tempdir() as path:
        project = Project(path)
        extras_file = path / CONSOLE_EXTRAS_FILENAME
        extras_file.touch()
        console(project=project)
        extras = mock_console.call_args[0][0]
        actual = extras["project"]

    assert actual == project

    # Ensure sys.path was updated correctly.
    assert sys.path[0] == str(project.path)


def test_custom_exception_handler_handles_non_ape_project(mocker):
    """
    If the user has assigned the variable ``project`` to something else
    in their active ``ape console`` session, the exception handler
    **SHOULD NOT** attempt to use its ``.path``.
    """
    session = mocker.MagicMock()
    session.user_ns = {"project": 123}  # Like doing `project = 123` in a console.

    err = Exception()

    handler_patch = mocker.patch("ape_console.plugin.handle_ape_exception")

    # Execute - this was failing before the fix.
    custom_exception_handler(session, None, err, None)

    # We are expecting the local project's path in the handler.
    expected_path = ManagerAccessMixin.local_project.path
    handler_patch.assert_called_once_with(err, [expected_path])


class TestApeConsoleNamespace:
    def test_accounts(self):
        extras = ApeConsoleNamespace()
        assert isinstance(extras["accounts"], AccountManager)

    @pytest.mark.parametrize("scope", ("local", "global"))
    def test_extras(self, scope):
        extras = ApeConsoleNamespace()
        _ = getattr(extras, f"_{scope}_extras")
        extras.__dict__[f"_{scope}_extras"] = {"foo": "123"}
        assert extras["foo"] == "123"

    @pytest.mark.parametrize("scope", ("local", "global"))
    def test_extras_load_using_ape_namespace(self, scope):
        extras = ApeConsoleNamespace()
        _ = getattr(extras, f"_{scope}_path")
        extras_content = """
def ape_init_extras(project):
    return {"foo": type(project)}
"""
        with create_tempdir() as temp:
            extras_file = temp / CONSOLE_EXTRAS_FILENAME
            extras_file.write_text(extras_content)
            extras.__dict__[f"_{scope}_path"] = extras_file
            extras.__dict__.pop(f"_{scope}_extras", None)
            assert extras["foo"] is LocalProject
