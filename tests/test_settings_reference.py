from pathlib import Path

from newsworker.settings_doc import PAGE_HEADER, SETTINGS_HELP, public_fields, settings_markdown


def test_every_setting_is_documented_once():
    documented = [name for group in SETTINGS_HELP.values() for name in group]
    assert sorted(documented) == sorted(public_fields())


def test_reference_page_is_generated_from_the_code():
    page = Path(__file__).resolve().parents[1] / "docs/docs/guides/settings-reference.md"
    assert page.read_text(encoding="utf-8") == PAGE_HEADER + settings_markdown(), (
        "Regenerate the page with: python -m newsworker.settings_doc"
    )
