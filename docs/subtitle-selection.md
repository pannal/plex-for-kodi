# How PM4K chooses subtitles

PM4K never decides from scratch. **Plex preselects a subtitle, and PM4K keeps it** — with
one thing it's allowed to do on top: turn a subtitle *off* when the **audio** is one of your
**Native languages**. Forced subtitles are never turned off.

So the whole behavior is two inputs combined.

## Input 1 — your Native languages

The audio languages you don't want subtitles for. The list PM4K actually checks is:

- Everything in the **Native languages** setting, **plus**
- Your **Plex Preferred Audio Language**, added automatically **only** when your Plex
  subtitle mode is **"Shown with foreign audio."**

In "Always" and "Manual" modes nothing is added automatically — the list is just the
**Native languages** setting as you typed it (often empty).

> **If you're on "Shown with foreign audio," this won't change what you see.** In that mode
> Plex already hides preferred-audio-language subtitles on its own, so auto-adding your
> Preferred Audio Language here just **mirrors** what Plex is doing — it never *starts*
> hiding subtitles you currently get. It only does real work when you understand **more than
> one** language: Plex has a single preferred-audio slot, so you list the extra languages
> under **Native languages** and PM4K suppresses those too.

> "Native languages" in the tables below means that *effective* list — the setting's
> contents, plus the auto-added Plex audio language in foreign-audio mode.

## Input 2 — what Plex preselects

| Your Plex subtitle mode | Plex preselects |
|---|---|
| Always enabled | A full subtitle |
| Shown with foreign audio | A full subtitle when the audio is foreign; a forced one (if the file has it) when the audio is your preferred language |
| Manual | Nothing (until you pick one) |

## Putting them together

| Plex preselected… | Audio is **not** a Native language | Audio **is** a Native language |
|---|---|---|
| A full subtitle | Kept — **subs on** | Dropped — **no subs** |
| A forced subtitle | Kept | **Kept** (forced never dropped) |
| Nothing | No subs | No subs |

This core table doesn't depend on the mode — the mode only decides *what Plex preselects*.

## Worked examples

- **English speaker, English audio + English subs, Plex on "Always":** Always mode adds
  nothing, so English isn't a Native language → Plex's full English subtitle is kept →
  **subs on, always.**

- **Same, but English added to the Native languages setting:** English *is* a Native
  language → full subtitle dropped → **no subs.** Your own setting overrides Plex's "always."
  (Fix: remove English from Native languages.)

- **A bilingual user — the reason Native languages exists.** Plex stores only **one**
  Preferred Audio Language. Someone who understands both English and Portuguese sets Preferred
  Audio to English with mode **"Shown with foreign audio."** Their Portuguese content's audio
  is always tagged plain `por` (audio codes carry no Brazilian-Portuguese distinction), so
  Plex classifies it as *foreign* and selects a subtitle for it — even though they understand
  it. Plex has no way to be told about the second language; that's an inherent Plex
  limitation. **Fix:** add **Portuguese** to **Native languages**. Now `por` audio is a Native
  language → the subtitle Plex selected is **dropped** → no subs on Portuguese content, while
  genuinely foreign audio still gets subtitles.

  (Aside: the `pt-BR` form only ever appears on *subtitle* preferences, which this logic never
  reads — the audio side this depends on is always plain `por`, so it matches "Portuguese"
  from the picker directly.)

## The things that bend the rules

- **Manual selection holds for the current playback only.** A subtitle you pick *during*
  playback is session-scoped and isn't remembered as a manual choice once you leave —
  re-entering the item re-runs the normal selection above. A subtitle you pick *from preplay*
  sets your Plex default for the item; a subtitle you *download* is added to the item
  server-side. Those two persist, but on the next load they're still subject to the
  Native-languages check like any other preselected track.

- **"Forced subtitles fix" setting.** Works around Plex preselecting a *forced* track when a
  full one is available (regardless of your preference) — with it on, PM4K uses the full
  track instead. It does this only when the audio *isn't* a Native language (its real
  purpose); when the audio *is* a Native language it leaves the forced track alone, so you
  still get the foreign-passage subs. (Inactive unless your Plex forced-subtitle preference
  is "prefer non-forced.")

- **"Forced" means** Plex flagged the track forced, or the word "forced" is in its name.

- **Decided once** — the choice is made at playback start and reused, unless the file or its
  tracks change.

## Known limitations

- **The manual-selection marker is in-memory only.** It protects a hand-picked subtitle
  within the current playback, but it isn't persisted, so it never carries a manual choice
  across re-entering the item.

- **The transcode-decision path doesn't check the manual marker.** Direct-play honours a
  manual pick over the Native-languages check; a transcoded playback (or an in-playback
  rebuild) can still drop a manual full subtitle whose audio is a Native language.
