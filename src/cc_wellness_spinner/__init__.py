"""cc-wellness-spinner — installs wellness-nudge spinner messages into
Claude Code's spinnerVerbs setting."""

import argparse
import importlib.metadata
import importlib.resources
import json
import os
import random
import sys
import tempfile
from pathlib import Path

LANGS = ["en", "pt-BR"]


class CliError(Exception):
    pass


def normalize_lang(value):
    for lang in LANGS:
        if lang.lower() == str(value).lower():
            return lang
    return None


def resolve_settings_path():
    config_dir = os.environ.get("CLAUDE_CONFIG_DIR")
    base = Path(config_dir) if config_dir else Path.home() / ".claude"
    return base / "settings.json"


def load_pack(lang):
    try:
        path = importlib.resources.files(__package__) / "packs" / f"{lang}.json"
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as err:
        raise CliError(
            f"Could not load the {lang} message pack ({err}). Try reinstalling the package."
        )


def read_settings(path):
    try:
        text = Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    except (OSError, UnicodeDecodeError) as err:
        raise CliError(
            f"Could not read {path} ({err}). Fix or remove the file first — nothing was written."
        )
    try:
        data = json.loads(text)
    except json.JSONDecodeError as err:
        raise CliError(
            f"Could not parse {path} as JSON ({err}). Fix or remove the file first — nothing was written."
        )
    if not isinstance(data, dict):
        raise CliError(
            f"Could not parse {path} as JSON (expected a top-level object). Fix or remove the file first — nothing was written."
        )
    return data


def merge_spinner_verbs(settings, mode, verbs):
    previous_present = "spinnerVerbs" in settings
    previous = settings.get("spinnerVerbs")
    new_settings = dict(settings)
    new_settings["spinnerVerbs"] = {"mode": mode, "verbs": list(verbs)}
    return new_settings, previous, previous_present


def uninstall_spinner_verbs(settings):
    was_present = "spinnerVerbs" in settings
    new_settings = dict(settings)
    removed = new_settings.pop("spinnerVerbs", None)
    return new_settings, removed, was_present


def read_version():
    try:
        return importlib.metadata.version("cc-wellness-spinner")
    except importlib.metadata.PackageNotFoundError:
        return "0+unknown"


def pick_random(items, n):
    return random.sample(items, min(n, len(items)))


def write_settings(path, settings):
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".tmp-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps(settings, indent=2, ensure_ascii=False) + "\n")
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def print_help(stdout):
    stdout.write(
        """cc-wellness-spinner — while Claude works for you, it also looks out for you

Installs wellness-nudge spinner messages into Claude Code's spinnerVerbs
setting.

Usage:
  uvx cc-wellness-spinner [options]

Options:
  --lang <en|pt-BR>        Message pack language (case-insensitive)
  --mode <append|replace>  append = defaults + custom, replace = custom only
  --list                   Print the chosen message pack and exit
  --dry-run                Print the resulting settings.json, write nothing
  --uninstall              Remove the spinnerVerbs key from settings.json
  --help                   Show this help
  --version                Show the version number

With no options and a TTY, runs interactively. Without a TTY, defaults to
--lang en --mode replace and prompts for nothing.
"""
    )


def _ask(stdin, stdout, prompt):
    stdout.write(prompt)
    stdout.flush()
    line = stdin.readline()
    if line == "":
        raise EOFError()
    return line.strip()


def prompt_lang(stdin, stdout):
    while True:
        answer = _ask(stdin, stdout, "Language [en/pt-BR] (en): ")
        if answer == "":
            return "en"
        lang = normalize_lang(answer)
        if lang is not None:
            return lang
        stdout.write(f'Unknown language "{answer}". Choose en or pt-BR.\n')


def prompt_mode(stdin, stdout):
    while True:
        answer = _ask(stdin, stdout, "Mode [append/replace] (replace): ")
        if answer == "":
            return "replace"
        mode = answer.lower()
        if mode in ("append", "replace"):
            return mode
        stdout.write(f'Unknown mode "{answer}". Choose append or replace.\n')


def prompt_confirm(stdin, stdout, question):
    answer = _ask(stdin, stdout, question)
    return answer.lower() in ("", "y", "yes")


class _ArgParser(argparse.ArgumentParser):
    def error(self, message):
        raise CliError(message)


def _build_parser():
    parser = _ArgParser(add_help=False, allow_abbrev=False)
    parser.add_argument("--lang")
    parser.add_argument("--mode")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--uninstall", action="store_true")
    parser.add_argument("--help", action="store_true")
    parser.add_argument("--version", action="store_true")
    return parser


def main(argv, stdin, stdout, stderr):
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.help:
        print_help(stdout)
        return 0
    if args.version:
        stdout.write(read_version() + "\n")
        return 0

    lang = None
    if args.lang is not None:
        lang = normalize_lang(args.lang)
        if lang is None:
            raise CliError(f'unknown --lang "{args.lang}". Choose en or pt-BR.')

    mode = None
    if args.mode is not None:
        mode = args.mode.lower()
        if mode not in ("append", "replace"):
            raise CliError(f'unknown --mode "{args.mode}". Choose append or replace.')

    settings_path = resolve_settings_path()

    if args.uninstall:
        settings = read_settings(settings_path)
        new_settings, removed, was_present = uninstall_spinner_verbs(settings)
        if not was_present:
            stdout.write("No spinnerVerbs setting found — nothing to remove.\n")
            return 0
        removed_json = json.dumps(removed, indent=2, ensure_ascii=False)
        if args.dry_run:
            stdout.write(f"Dry run — would remove spinnerVerbs:\n{removed_json}\n")
            return 0
        write_settings(settings_path, new_settings)
        stdout.write(f"Removed spinnerVerbs:\n{removed_json}\n")
        stdout.write(f"Updated {settings_path}\n")
        return 0

    if args.list:
        pack = load_pack(lang or "en")
        stdout.write(f"{pack['name']} ({pack['code']})\n")
        for verb in pack["verbs"]:
            stdout.write(f"  {verb}\n")
        return 0

    settings = read_settings(settings_path)
    interactive = stdin.isatty()

    try:
        chosen_lang = lang
        chosen_mode = mode
        if chosen_lang is None:
            chosen_lang = prompt_lang(stdin, stdout) if interactive else "en"
        if chosen_mode is None:
            chosen_mode = prompt_mode(stdin, stdout) if interactive else "replace"

        pack = load_pack(chosen_lang)

        if interactive:
            stdout.write(f"\nPreview ({pack['name']}):\n")
            for verb in pick_random(pack["verbs"], 5):
                stdout.write(f"  ✶ {verb}…\n")
            if not prompt_confirm(stdin, stdout, "\nInstall? [Y/n] "):
                stdout.write("Aborted. Nothing written.\n")
                return 0
    except (EOFError, KeyboardInterrupt):
        stdout.write("Aborted. Nothing written.\n")
        return 0

    merged, previous, previous_present = merge_spinner_verbs(
        settings, chosen_mode, pack["verbs"]
    )
    if previous_present and previous != merged["spinnerVerbs"]:
        stderr.write(
            "Existing spinnerVerbs will be replaced:\n"
            + json.dumps(previous, indent=2, ensure_ascii=False)
            + "\n"
        )

    if args.dry_run:
        stdout.write(json.dumps(merged, indent=2, ensure_ascii=False) + "\n")
        return 0

    write_settings(settings_path, merged)
    stdout.write(
        f"\nInstalled {pack['name']} spinner messages ({chosen_mode}) → {settings_path}\n"
    )
    stdout.write("Restart any running Claude Code session to pick this up.\n")
    stdout.write(
        "Note: the VS Code extension uses a different key (claudeCode.spinnerVerbs "
        "in VS Code's own settings.json) — this tool does not touch that.\n"
    )
    return 0


def cli():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except AttributeError:
            pass  # ponytail: non-reconfigurable stream (StringIO in tests) — leave as-is
    try:
        code = main(sys.argv[1:], sys.stdin, sys.stdout, sys.stderr)
    except CliError as err:
        print(f"Error: {err}", file=sys.stderr)
        code = 1
    sys.exit(code)
