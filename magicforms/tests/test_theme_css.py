"""Design-token discipline for the stylesheet (no database needed)."""

import re
import subprocess
import sys
from pathlib import Path

from django.test import SimpleTestCase

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "magicforms/static/magicforms/css/src"
THEME = ROOT / "magicforms/static/magicforms/css/theme.css"
BUILD = ROOT / "scripts/build_theme_css.py"

LITERAL = re.compile(r"#[0-9a-fA-F]{3,8}\b|rgba?\([^)]*\)|hsla?\([^)]*\)")
TOKEN_DEF = re.compile(r"^\s*(--mf-[a-z0-9-]+)\s*:", re.M)
# Only bare uses count: var(--x, fallback) is valid even when --x is provided at runtime
# (entity theme inline styles, scroll_reveal.js) or intentionally absent.
TOKEN_USE = re.compile(r"var\((--mf-[a-z0-9-]+)\)")


class ThemeCssTests(SimpleTestCase):
    def test_theme_css_is_built_from_src_parts(self):
        result = subprocess.run([sys.executable, str(BUILD), "--check"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def test_component_files_use_tokens_not_colour_literals(self):
        offenders = []
        for part in sorted(SRC.glob("*.css")):
            if part.name.startswith("00-"):
                continue
            for lineno, line in enumerate(part.read_text(encoding="utf-8").splitlines(), 1):
                if "url(" in line:
                    continue
                code = line.split("/*")[0]
                if LITERAL.search(code):
                    offenders.append(f"{part.name}:{lineno}: {line.strip()}")
        self.assertEqual(offenders, [], "Colour literals belong in src/00-tokens.css:\n" + "\n".join(offenders))

    def test_every_token_used_is_defined(self):
        tokens_css = (SRC / "00-tokens.css").read_text(encoding="utf-8")
        defined = set(TOKEN_DEF.findall(tokens_css))
        used = set()
        for part in SRC.glob("*.css"):
            used |= set(TOKEN_USE.findall(part.read_text(encoding="utf-8")))
        # Tokens may also be defined locally inside component rules (e.g. per-page overrides).
        local = set()
        for part in SRC.glob("*.css"):
            local |= set(TOKEN_DEF.findall(part.read_text(encoding="utf-8")))
        missing = sorted(used - defined - local)
        self.assertEqual(missing, [], f"Undefined tokens: {missing}")

    def test_dark_palette_covers_every_colour_token(self):
        tokens_css = (SRC / "00-tokens.css").read_text(encoding="utf-8")
        dark_blocks = re.findall(r'\[data-theme="dark"\]\s*\{(.*?)\n\}', tokens_css, re.S)
        self.assertTrue(dark_blocks, "dark palette block missing")
        dark_defined = set()
        for block in dark_blocks:
            dark_defined |= set(TOKEN_DEF.findall(block))
        light_blocks = re.findall(r":root\s*\{(.*?)\n\}", tokens_css, re.S)
        colour_tokens = set()
        for block in light_blocks:
            for m in re.finditer(r"^\s*(--mf-[a-z0-9-]+)\s*:\s*(.+?);", block, re.M):
                if LITERAL.search(m.group(2)) and "shadow" not in m.group(1) and m.group(1) not in ("--mf-accent",):
                    colour_tokens.add(m.group(1))
        missing = sorted(colour_tokens - dark_defined)
        self.assertEqual(missing, [], f"Colour tokens without a dark value: {missing}")
