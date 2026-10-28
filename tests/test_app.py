import copy
from pathlib import Path

import pytest
from textual.widgets import Button, Static, Tree

from anki_x.app import AnkiX
from anki_x.bootstrap import Environment
from anki_x.navigation import NavigationStore
from anki_x.storage import Settings, write_json
from test_navigation import FakeClient
from test_productization import paths_at


class ConnectedClient(FakeClient):
    endpoint = "http://fixture/api/v1"

    def __init__(self, journal):
        super().__init__()
        self.journal = journal

    def call(self, method, **params):
        if method == "profiles.list": return ["Test User"]
        raise AssertionError(method)


class Connected:
    def __init__(self, client): self.client = client
    def inspect(self):
        return Environment("ready", "Connected", "Ready", profile="Test User", tested_version=True, client=self.client)


class Missing:
    def inspect(self):
        return Environment("anki_missing", "先安装 Anki", "点击安装按钮即可获取官方安装包。")


def make_app(tmp_path, connector=None):
    paths = paths_at(tmp_path)
    paths.ensure()
    settings = Settings(paths)
    settings.set("autoplay", False)
    settings.set("deck", "English::CET4")
    client = ConnectedClient(paths.state / "pending.json")
    return AnkiX(paths, settings, connector=connector or Connected(client))


@pytest.mark.asyncio
async def test_first_run_without_anki_offers_install_and_paths(tmp_path):
    app = make_app(tmp_path, Missing())
    async with app.run_test(size=(100, 38)) as pilot:
        await pilot.pause(0.5)
        assert app.page == "setup"
        assert app.query_one("#install-anki", Button).display
        assert "先安装" in str(app.query_one("#setup-copy", Static).render())
        await pilot.press("q")


@pytest.mark.asyncio
async def test_tree_review_back_and_restart_answer(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause(0.5)
        assert app.page == "home"
        await pilot.press("l", "l", "enter")
        await pilot.pause(0.5)
        assert app.page == "review"
        assert app.deck.deck_id == "3"
        await pilot.press("space")
        assert app.review.state["side"] == "answer"
        await pilot.press("b")
        await pilot.pause(0.3)
        assert app.page == "home"
        await pilot.press("enter")
        await pilot.pause(0.3)
        assert app.page == "review"
        assert app.review.state["side"] == "answer"
        await pilot.press("q")
    restarted = make_app(tmp_path)
    async with restarted.run_test(size=(110, 40)) as pilot:
        await pilot.pause(0.8)
        assert restarted.page == "review"
        assert restarted.review.state["side"] == "answer"
        await pilot.press("q")


@pytest.mark.asyncio
async def test_unknown_pending_write_opens_recovery_before_study(tmp_path):
    app = make_app(tmp_path)
    write_json(app.paths.state / "pending.json", {"state": "sending", "method": "scheduling.answer"})
    async with app.run_test(size=(100, 38)) as pilot:
        await pilot.pause(0.5)
        assert app.page == "setup"
        assert "尚未确认" in str(app.query_one("#setup-copy", Static).render())
        assert app.review is None
        await pilot.press("q")


@pytest.mark.asyncio
async def test_settings_changes_persist_and_return_to_home(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test(size=(100, 38)) as pilot:
        await pilot.pause(0.5)
        await pilot.press("s")
        assert app.page == "settings"
        await pilot.click("#toggle-title")
        assert not app.settings.get("show_title")
        await pilot.press("escape")
        assert app.page == "home"
        await pilot.press("q")
    assert not Settings(app.paths).get("show_title")
