# PM4K / PlexMod for Kodi

[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/Z8Z8X6P9T)

This is a modification of the official open-source Plex client for Kodi "plex-for-kodi" (Plex4Kodi)  semi-maintained by me (pannal).

Contrary to how this repository was handled before, this client does _not_ claim to adhere to the Plex Inc. design guidelines, all the time.

It implements features that are not implemented in other official Plex clients and may implement others in non-conform ways.

It is still based off of the original P4K source and critical bugfixes might be PR'd back.

## Active branches
* [develop-kodi21](https://github.com/pannal/plex-for-kodi/tree/develop_kodi21) (Kodi 19, 20, 21 cross-compatible)
* [develop-kodi18](https://github.com/pannal/plex-for-kodi/tree/develop_kodi18) (legacy)

Master branch is based off of the official plex-for-kodi master branch.

## Installation

### Via repository (recommended)
* Add `https://pm4k.eu` to your Kodi installation as a file source
* Go to Settings->Addons, choose "Install from zip file", choose the file source you added and install the repository
* Install Plex via Settings->Addons->Install from repository->Don't Panic->Video add-ons->Plex
* Optional, recommended: Install Plextuary via Settings->Addons->Install from repository->Don't Panic->Look and Feel->Skin->Plextuary

### Installation (stable only, not optimized, possibly outdated)
* Install "PM4K for Kodi" from the official Kodi repository
* Optional, recommended: Install Plextuary skin using the above

### Manual
* Checkout any branch of this GitHub repository, rename to `script.plexmod` and use as an addon (for it to work with "Install from zip", the contents of the zip should be the folder `script.plexmod`.

### Installing to a read-only or write-protected location
Set the environment variable `INSTALLATION_DIR_AVOID_WRITE` to any value before starting Kodi to prevent the addon from trying to write to its installation directory. Useful for package managers.

## Translation
You can help! Join the translation effort at [POEditor](https://poeditor.com/join/project/ASOl50YAXg) (thanks for the free open source license, guys).

## Help/Bug Reports
https://forums.plex.tv/t/plexmod-for-kodi-18-19-20-21/481208

## License
[LICENSE](https://github.com/plexinc/plex-for-kodi/blob/master/LICENSE.txt)

## Powered by

[![JetBrains logo.](https://resources.jetbrains.com/storage/products/company/brand/logos/jetbrains.svg)](https://jb.gg/OpenSource)
