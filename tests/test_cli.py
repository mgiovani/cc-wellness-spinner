import importlib.metadata
import io
import json
import os
import re
from pathlib import Path

import pytest

from cc_wellness_spinner import (
    CliError,
    _ask,
    cli,
    load_pack,
    main,
    merge_spinner_verbs,
    normalize_lang,
    pick_random,
    print_help,
    prompt_confirm,
    prompt_lang,
    prompt_mode,
    read_settings,
    read_version,
    resolve_settings_path,
    uninstall_spinner_verbs,
    write_settings,
)


class FakeTTY(io.StringIO):
    def isatty(self):
        return True


def _cfg(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    return tmp_path / "settings.json"


# ---------------------------------------------------------------------------
# normalize_lang
# ---------------------------------------------------------------------------


def test_normalize_lang_matches_case_insensitively():
    assert normalize_lang("EN") == "en"
    assert normalize_lang("en") == "en"
    assert normalize_lang("PT-br") == "pt-BR"
    assert normalize_lang("pt-br") == "pt-BR"


def test_normalize_lang_unknown_is_none():
    assert normalize_lang("fr") is None
    assert normalize_lang("") is None


# ---------------------------------------------------------------------------
# resolve_settings_path
# ---------------------------------------------------------------------------


def test_resolve_settings_path_uses_env_var(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    assert resolve_settings_path() == tmp_path / "settings.json"


def test_resolve_settings_path_falls_back_to_home_when_unset(monkeypatch, tmp_path):
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert resolve_settings_path() == tmp_path / ".claude" / "settings.json"


def test_resolve_settings_path_falls_back_to_home_when_empty(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", "")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert resolve_settings_path() == tmp_path / ".claude" / "settings.json"


# ---------------------------------------------------------------------------
# load_pack
# ---------------------------------------------------------------------------


def test_load_pack_valid_langs():
    en = load_pack("en")
    assert en["code"] == "en"
    pt = load_pack("pt-BR")
    assert pt["code"] == "pt-BR"


def test_load_pack_unknown_raises_cli_error():
    with pytest.raises(CliError, match="Could not load the bogus message pack"):
        load_pack("bogus")


# ---------------------------------------------------------------------------
# read_settings
# ---------------------------------------------------------------------------


def test_read_settings_missing_file_returns_empty_dict(tmp_path):
    assert read_settings(tmp_path / "settings.json") == {}


def test_read_settings_malformed_json_raises(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(CliError, match="Could not parse"):
        read_settings(path)


def test_read_settings_non_dict_raises(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(CliError, match="expected a top-level object"):
        read_settings(path)


def test_read_settings_directory_raises(tmp_path):
    path = tmp_path / "settings.json"
    path.mkdir()
    with pytest.raises(CliError, match="Could not read"):
        read_settings(path)


# ---------------------------------------------------------------------------
# merge_spinner_verbs / uninstall_spinner_verbs (pure functions)
# ---------------------------------------------------------------------------


def test_merge_spinner_verbs_no_prior_value():
    settings = {"foo": "bar"}
    new, previous, present = merge_spinner_verbs(settings, "append", ["a", "b"])
    assert new["spinnerVerbs"] == {"mode": "append", "verbs": ["a", "b"]}
    assert new["foo"] == "bar"
    assert present is False
    assert previous is None
    assert settings == {"foo": "bar"}  # untouched (pure)


def test_merge_spinner_verbs_preserves_foreign_keys_and_reports_previous():
    settings = {"spinnerVerbs": {"mode": "x", "verbs": ["z"]}, "other": 1}
    new, previous, present = merge_spinner_verbs(settings, "replace", ["c"])
    assert present is True
    assert previous == {"mode": "x", "verbs": ["z"]}
    assert new["other"] == 1
    assert new["spinnerVerbs"] == {"mode": "replace", "verbs": ["c"]}


def test_uninstall_spinner_verbs_present():
    settings = {"spinnerVerbs": {"a": 1}, "foo": "bar"}
    new, removed, was_present = uninstall_spinner_verbs(settings)
    assert was_present is True
    assert removed == {"a": 1}
    assert "spinnerVerbs" not in new
    assert new["foo"] == "bar"
    assert "spinnerVerbs" in settings  # original untouched (pure)


def test_uninstall_spinner_verbs_absent():
    new, removed, was_present = uninstall_spinner_verbs({"foo": 1})
    assert was_present is False
    assert removed is None
    assert new == {"foo": 1}


def test_uninstall_spinner_verbs_null_still_present():
    new, removed, was_present = uninstall_spinner_verbs({"spinnerVerbs": None})
    assert was_present is True
    assert removed is None
    assert "spinnerVerbs" not in new


# ---------------------------------------------------------------------------
# read_version
# ---------------------------------------------------------------------------


def test_read_version_returns_string():
    version = read_version()
    assert isinstance(version, str)
    assert version


def test_read_version_falls_back_when_package_not_found(monkeypatch):
    def fake_version(name):
        raise importlib.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(importlib.metadata, "version", fake_version)
    assert read_version() == "0+unknown"


# ---------------------------------------------------------------------------
# pick_random
# ---------------------------------------------------------------------------


def test_pick_random_returns_subset():
    items = list(range(10))
    picked = pick_random(items, 5)
    assert len(picked) == 5
    assert len(set(picked)) == 5
    assert set(picked) <= set(items)


def test_pick_random_caps_at_length():
    items = list(range(3))
    picked = pick_random(items, 20)
    assert sorted(picked) == items


# ---------------------------------------------------------------------------
# write_settings
# ---------------------------------------------------------------------------


def test_write_settings_creates_dirs_and_trailing_newline(tmp_path):
    path = tmp_path / "nested" / "dir" / "settings.json"
    write_settings(path, {"a": 1})
    text = path.read_text(encoding="utf-8")
    assert text.endswith("\n")
    assert json.loads(text) == {"a": 1}
    assert '"a": 1' in text  # indent=2


def test_write_settings_does_not_escape_unicode(tmp_path):
    path = tmp_path / "settings.json"
    write_settings(path, {"msg": "água"})
    raw = path.read_bytes().decode("utf-8")
    assert "água" in raw
    assert "\\u00" not in raw


def test_write_settings_atomic_failure_leaves_no_litter(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    write_settings(path, {"original": True})
    original_bytes = path.read_bytes()

    def boom(_src, _dst):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        write_settings(path, {"new": True})

    assert path.read_bytes() == original_bytes
    leftovers = [p for p in tmp_path.iterdir() if ".tmp-" in p.name]
    assert leftovers == []


def test_write_settings_follows_symlink(tmp_path):
    target = tmp_path / "real_target.json"
    target.write_text("{}", encoding="utf-8")
    cfgdir = tmp_path / "cfgdir"
    cfgdir.mkdir()
    link = cfgdir / "settings.json"
    os.symlink(target, link)

    write_settings(link, {"hello": "world"})

    assert link.is_symlink()
    assert json.loads(target.read_text(encoding="utf-8")) == {"hello": "world"}


# ---------------------------------------------------------------------------
# print_help / _ask / prompt_lang / prompt_mode / prompt_confirm
# ---------------------------------------------------------------------------


def test_print_help_contains_usage_and_uninstall():
    out = io.StringIO()
    print_help(out)
    text = out.getvalue()
    assert "Usage:" in text
    assert "--uninstall" in text


def test_ask_reads_and_strips_line():
    stdin = io.StringIO("hello\n")
    stdout = io.StringIO()
    assert _ask(stdin, stdout, "Prompt: ") == "hello"
    assert stdout.getvalue() == "Prompt: "


def test_ask_eof_raises():
    stdin = io.StringIO("")
    stdout = io.StringIO()
    with pytest.raises(EOFError):
        _ask(stdin, stdout, "Prompt: ")


def test_prompt_lang_valid_first_try():
    stdin = io.StringIO("pt-br\n")
    stdout = io.StringIO()
    assert prompt_lang(stdin, stdout) == "pt-BR"


def test_prompt_lang_retries_on_invalid():
    stdin = io.StringIO("xx\nen\n")
    stdout = io.StringIO()
    assert prompt_lang(stdin, stdout) == "en"
    assert 'Unknown language "xx"' in stdout.getvalue()


def test_prompt_mode_valid_first_try():
    stdin = io.StringIO("replace\n")
    stdout = io.StringIO()
    assert prompt_mode(stdin, stdout) == "replace"


def test_prompt_mode_default_is_replace():
    assert prompt_mode(io.StringIO("\n"), io.StringIO()) == "replace"


def test_prompt_mode_retries_on_invalid():
    stdin = io.StringIO("bogus\nappend\n")
    stdout = io.StringIO()
    assert prompt_mode(stdin, stdout) == "append"
    assert 'Unknown mode "bogus"' in stdout.getvalue()


@pytest.mark.parametrize(
    "answer,expected",
    [("y\n", True), ("Yes\n", True), ("\n", True), ("n\n", False), ("nope\n", False)],
)
def test_prompt_confirm(answer, expected):
    stdin = io.StringIO(answer)
    stdout = io.StringIO()
    assert prompt_confirm(stdin, stdout, "Install? [Y/n] ") is expected


# ---------------------------------------------------------------------------
# main() — install flows
# ---------------------------------------------------------------------------


def test_main_fresh_install_non_tty_nested_missing_dir(monkeypatch, tmp_path):
    path = _cfg(monkeypatch, tmp_path / "nested" / "missing")
    out, err = io.StringIO(), io.StringIO()
    code = main([], io.StringIO(), out, err)
    assert code == 0
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert text.endswith("\n")
    data = json.loads(text)
    assert data["spinnerVerbs"]["mode"] == "replace"
    assert data["spinnerVerbs"]["verbs"] == load_pack("en")["verbs"]


def test_main_foreign_keys_survive_install_and_uninstall(monkeypatch, tmp_path):
    path = _cfg(monkeypatch, tmp_path)
    path.write_text(json.dumps({"someOtherSetting": "keep-me"}), encoding="utf-8")

    code = main([], io.StringIO(), io.StringIO(), io.StringIO())
    assert code == 0
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["someOtherSetting"] == "keep-me"
    assert "spinnerVerbs" in data

    code = main(["--uninstall"], io.StringIO(), io.StringIO(), io.StringIO())
    assert code == 0
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["someOtherSetting"] == "keep-me"
    assert "spinnerVerbs" not in data


@pytest.mark.parametrize("lang", ["en", "pt-BR"])
@pytest.mark.parametrize("mode", ["append", "replace"])
def test_main_install_lang_and_mode(monkeypatch, tmp_path, lang, mode):
    path = _cfg(monkeypatch, tmp_path)
    out = io.StringIO()
    code = main(["--lang", lang, "--mode", mode], io.StringIO(), out, io.StringIO())
    assert code == 0
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["spinnerVerbs"]["mode"] == mode
    assert data["spinnerVerbs"]["verbs"] == load_pack(lang)["verbs"]


def test_main_install_pt_br_stores_real_utf8_accents(monkeypatch, tmp_path):
    path = _cfg(monkeypatch, tmp_path)
    pack = load_pack("pt-BR")
    accented = next(v for v in pack["verbs"] if any(ord(c) > 127 for c in v))

    code = main(["--lang", "pt-BR"], io.StringIO(), io.StringIO(), io.StringIO())
    assert code == 0
    raw = path.read_bytes().decode("utf-8")
    assert accented in raw
    assert "\\u00" not in raw


@pytest.mark.parametrize("argv", [[], ["--uninstall"]])
@pytest.mark.parametrize("content", ["{not valid json", "[]"])
def test_main_malformed_or_non_dict_settings_raises(monkeypatch, tmp_path, argv, content):
    path = _cfg(monkeypatch, tmp_path)
    path.write_text(content, encoding="utf-8")
    with pytest.raises(CliError):
        main(argv, io.StringIO(), io.StringIO(), io.StringIO())


def test_main_settings_path_is_directory_raises(monkeypatch, tmp_path):
    path = _cfg(monkeypatch, tmp_path)
    path.mkdir()
    with pytest.raises(CliError):
        main([], io.StringIO(), io.StringIO(), io.StringIO())


def test_main_dry_run_purity_stdout_is_pure_json_and_file_untouched(monkeypatch, tmp_path):
    path = _cfg(monkeypatch, tmp_path)
    original = {"spinnerVerbs": {"mode": "append", "verbs": ["Working. old"]}, "other": "keep"}
    path.write_text(json.dumps(original), encoding="utf-8")
    original_bytes = path.read_bytes()

    out, err = io.StringIO(), io.StringIO()
    code = main(["--dry-run", "--lang", "en"], io.StringIO(), out, err)
    assert code == 0

    parsed = json.loads(out.getvalue())
    assert parsed["other"] == "keep"
    assert parsed["spinnerVerbs"]["verbs"] == load_pack("en")["verbs"]
    assert "Existing spinnerVerbs will be replaced:" in err.getvalue()
    assert path.read_bytes() == original_bytes


def test_main_dry_run_warns_about_prior_null_spinner_verbs(monkeypatch, tmp_path):
    path = _cfg(monkeypatch, tmp_path)
    path.write_text(json.dumps({"spinnerVerbs": None}), encoding="utf-8")

    out, err = io.StringIO(), io.StringIO()
    code = main(["--dry-run"], io.StringIO(), out, err)
    assert code == 0
    assert "Existing spinnerVerbs will be replaced:" in err.getvalue()
    assert "null" in err.getvalue()


def test_main_symlinked_settings_json(monkeypatch, tmp_path):
    target = tmp_path / "real_target.json"
    target.write_text("{}", encoding="utf-8")
    cfgdir = tmp_path / "cfgdir"
    cfgdir.mkdir()
    link = cfgdir / "settings.json"
    os.symlink(target, link)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(cfgdir))

    code = main([], io.StringIO(), io.StringIO(), io.StringIO())
    assert code == 0
    assert link.is_symlink()
    data = json.loads(target.read_text(encoding="utf-8"))
    assert "spinnerVerbs" in data


# ---------------------------------------------------------------------------
# main() — --list / --help / --version / unknown flag
# ---------------------------------------------------------------------------


def test_main_list_default_lang(monkeypatch, tmp_path):
    _cfg(monkeypatch, tmp_path)
    out = io.StringIO()
    code = main(["--list"], io.StringIO(), out, io.StringIO())
    assert code == 0
    text = out.getvalue()
    assert "English (en)" in text
    for verb in load_pack("en")["verbs"]:
        assert f"  {verb}" in text


def test_main_list_explicit_lang(monkeypatch, tmp_path):
    _cfg(monkeypatch, tmp_path)
    out = io.StringIO()
    code = main(["--list", "--lang", "pt-BR"], io.StringIO(), out, io.StringIO())
    assert code == 0
    assert "Português (Brasil) (pt-BR)" in out.getvalue()


def test_main_help():
    out = io.StringIO()
    code = main(["--help"], io.StringIO(), out, io.StringIO())
    assert code == 0
    text = out.getvalue()
    assert "Usage:" in text
    assert "--uninstall" in text


def test_main_version():
    out = io.StringIO()
    code = main(["--version"], io.StringIO(), out, io.StringIO())
    assert code == 0
    assert out.getvalue().strip() == read_version()


def test_main_unknown_flag_raises():
    with pytest.raises(CliError):
        main(["--bogus"], io.StringIO(), io.StringIO(), io.StringIO())


def test_main_unknown_mode_raises_cli_error(monkeypatch, tmp_path):
    _cfg(monkeypatch, tmp_path)
    with pytest.raises(
        CliError, match=re.escape('unknown --mode "bogus". Choose append or replace.')
    ):
        main(["--mode", "bogus"], io.StringIO(), io.StringIO(), io.StringIO())


def test_main_unknown_lang_raises_cli_error(monkeypatch, tmp_path):
    _cfg(monkeypatch, tmp_path)
    with pytest.raises(
        CliError, match=re.escape('unknown --lang "xx". Choose en or pt-BR.')
    ):
        main(["--lang", "xx"], io.StringIO(), io.StringIO(), io.StringIO())


# ---------------------------------------------------------------------------
# main() — interactive flows
# ---------------------------------------------------------------------------


def test_main_interactive_install_pt_br_replace(monkeypatch, tmp_path):
    path = _cfg(monkeypatch, tmp_path)
    stdin = FakeTTY("pt-br\nreplace\ny\n")
    code = main([], stdin, io.StringIO(), io.StringIO())
    assert code == 0
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["spinnerVerbs"]["mode"] == "replace"
    assert data["spinnerVerbs"]["verbs"] == load_pack("pt-BR")["verbs"]


def test_main_interactive_invalid_then_valid_retry(monkeypatch, tmp_path):
    path = _cfg(monkeypatch, tmp_path)
    stdin = FakeTTY("xx\nen\nbogus\nappend\n\n")
    out = io.StringIO()
    code = main([], stdin, out, io.StringIO())
    assert code == 0
    assert 'Unknown language "xx"' in out.getvalue()
    assert 'Unknown mode "bogus"' in out.getvalue()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["spinnerVerbs"]["mode"] == "append"
    assert data["spinnerVerbs"]["verbs"] == load_pack("en")["verbs"]


def test_main_interactive_confirm_declined(monkeypatch, tmp_path):
    path = _cfg(monkeypatch, tmp_path)
    stdin = FakeTTY("n\n")
    out = io.StringIO()
    code = main(["--lang", "en", "--mode", "append"], stdin, out, io.StringIO())
    assert code == 0
    assert "Aborted. Nothing written." in out.getvalue()
    assert not path.exists()


def test_main_interactive_eof_aborts(monkeypatch, tmp_path):
    path = _cfg(monkeypatch, tmp_path)
    stdin = FakeTTY("")
    out = io.StringIO()
    code = main([], stdin, out, io.StringIO())
    assert code == 0
    assert "Aborted. Nothing written." in out.getvalue()
    assert not path.exists()


# ---------------------------------------------------------------------------
# main() — uninstall flows
# ---------------------------------------------------------------------------


def test_main_uninstall_absent_key(monkeypatch, tmp_path):
    path = _cfg(monkeypatch, tmp_path)
    path.write_text("{}", encoding="utf-8")
    out = io.StringIO()
    code = main(["--uninstall"], io.StringIO(), out, io.StringIO())
    assert code == 0
    assert "No spinnerVerbs setting found — nothing to remove." in out.getvalue()


def test_main_uninstall_present_removes_and_writes(monkeypatch, tmp_path):
    path = _cfg(monkeypatch, tmp_path)
    path.write_text(json.dumps({"spinnerVerbs": {"mode": "append", "verbs": ["x"]}}), encoding="utf-8")
    out = io.StringIO()
    code = main(["--uninstall"], io.StringIO(), out, io.StringIO())
    assert code == 0
    assert "Removed spinnerVerbs:" in out.getvalue()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert "spinnerVerbs" not in data


def test_main_uninstall_dry_run_does_not_write(monkeypatch, tmp_path):
    path = _cfg(monkeypatch, tmp_path)
    original = json.dumps({"spinnerVerbs": {"mode": "append", "verbs": ["x"]}})
    path.write_text(original, encoding="utf-8")
    out = io.StringIO()
    code = main(["--uninstall", "--dry-run"], io.StringIO(), out, io.StringIO())
    assert code == 0
    assert "Dry run — would remove spinnerVerbs:" in out.getvalue()
    assert path.read_text(encoding="utf-8") == original


def test_main_uninstall_null_value_still_removed(monkeypatch, tmp_path):
    path = _cfg(monkeypatch, tmp_path)
    path.write_text(json.dumps({"spinnerVerbs": None}), encoding="utf-8")
    out = io.StringIO()
    code = main(["--uninstall"], io.StringIO(), out, io.StringIO())
    assert code == 0
    assert "Removed spinnerVerbs:" in out.getvalue()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert "spinnerVerbs" not in data


# ---------------------------------------------------------------------------
# cli()
# ---------------------------------------------------------------------------


def test_cli_error_exits_1_and_prints_to_stderr(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["cc-wellness-spinner", "--lang", "bogus"])
    with pytest.raises(SystemExit) as exc_info:
        cli()
    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert captured.err.startswith("Error: ")
