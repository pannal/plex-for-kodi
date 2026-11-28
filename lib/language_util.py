# coding=utf-8
"""Language-code helpers. Niche and iso639-backed, kept out of the hot util modules."""
from __future__ import absolute_import

from plexnet import util as pnUtil


# Codes Plex emits that are not ISO-639 at all, mapped to the closest part2t.
# iso639 raises KeyError on these, so every lookup has to go through
# resolveLanguage() rather than calling languages.get() directly.
PLEX_LANGUAGE_ALIASES = {
    "pob": "por",  # Plex's Brazilian Portuguese
}


def resolveLanguage(code, part="part2t"):
    """The iso639 language for `code`, or None if it cannot be resolved.

    Accepts 2-letter (part1) or 3-letter (part2t/part2b) codes, with or without a region
    suffix (e.g. "pt-BR", "pob-BR"), and the Plex-only codes in PLEX_LANGUAGE_ALIASES.
    Never raises - iso639 signals "unknown" with KeyError, which callers in playback
    paths must not have to guard individually."""
    code = (code or "").strip().lower().replace("_", "-").split("-")[0]
    if len(code) not in (2, 3):
        return None

    from iso639 import languages
    if len(code) == 2:
        part = "part1"
    else:
        code = PLEX_LANGUAGE_ALIASES.get(code, code)

    try:
        return languages.get(**{part: code})
    except KeyError:
        return None


def normalizeLanguagePart2t(code):
    """Normalize an ISO-639 code to its part2t form (matching plex stream languageCodes and the
    disable_subtitle_languages setting). Accepts 2-letter (part1) or 3-letter (part2t) codes,
    with or without a region suffix (e.g. "pt-BR", "pob-BR"); None if unresolved."""
    lang = resolveLanguage(code)
    return lang.part2t if lang else None


def getNativeLanguages(configured):
    """Effective set of 'native' subtitle language codes (part2t) whose same-language subtitles
    should be suppressed.

    Unions the user-configured disable_subtitle_languages (multi-language, authoritative) with
    Plex's single Preferred Audio Language, but only when the account's Subtitle Mode is
    "Shown with foreign audio" (auto_select_subtitle == 1) — the one mode that means "don't show
    subtitles when the audio is in my language". Modes 0 (manual) and 2 (always) derive nothing.
    """
    native = set(configured or [])
    acc = pnUtil.ACCOUNT
    if acc and getattr(acc, 'autoSelectSubtitle', 0) == 1:
        audio_lang = normalizeLanguagePart2t(getattr(acc, 'audioLanguage', '') or '')
        if audio_lang:
            native.add(audio_lang)
    return native
