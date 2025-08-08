## Use
Setting PM4K to use a custom repository may be useful in scenarios where the testing device is running a special OS (ex. CoreELEC) and you want to push updates to that device while using the same update mechanism used in PM4K.

This is not intended for general use and is meant to be used by developers who want to contribute to the addon.

## Setup
Before you can use this, there's some code changes that need to be made. Fork the repository and make the following changes in your new fork:
* Adjust the code in ```lib/updater/py```:
    * (required) ```SHOW_CUSTOM_UPDATER_OPTION = False``` --> Set to ```True``` to enable the option of setting a custom repository
    * (optional) ```CUSTOM_UPDATER_CHECK_IMMEDIATE = True``` --> Set to ```True``` to force an update check every time you open PM4K
    * (required) ```CUSTOM_UPDATER_REPO = "pannal/plex-for-kodi"``` --> Replace ```pannal/plex-for-kodi``` with your username/repository
    * (required) ```CUSTOM_UPDATER_BRANCH = "develop_kodi21"``` --> Replace ```develop_kodi21``` with the name of your branch

Once you are done with that, download and install the new forked addon onto your machine. From here, change the following setting:
* Settings -> System -> Update source -> Custom

You can now push updates to your branch and every time you bump the version of the addon, PM4K will automatically try to pull an update on next run:
* Adjust the code in ```addon.xml```:
    * ```version="0.8.0-beta13.5"``` --> Bump the version up (ex. ```version="0.8.0-beta13.6"```)

## Notes
* If you disable ```SHOW_CUSTOM_UPDATER_OPTION``` and re-open PM4K, it will reset the 'Update source' setting back to default.
* When submitting a pull request with new changes where this was used, make sure to reset the settings back to their default values (refer to the Setup section).
