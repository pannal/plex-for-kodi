# coding=utf-8
import os
import re

from kodi_six import xbmc
from kodi_six import xbmcvfs

from plexnet import plexapp

from lib.kodijsonrpc import rpc
from lib.util import ADDON, translatePath, KODI_BUILD_NUMBER, DEBUG_LOG, LOG, FROM_KODI_REPOSITORY
from lib.advancedsettings import adv


ADV_MSIZE_RE = re.compile(r'<memorysize>(\d+)</memorysize>')
ADV_RFACT_RE = re.compile(r'<readfactor>(\d+)</readfactor>')
ADV_CACHE_RE = re.compile(r'\s*<cache>.*</cache>', re.S | re.I)


class KodiCacheManager(object):
    """
    A pretty cheap approach at managing the <cache> section of advancedsettings.xml

    Starting with build 20.90.821 (Kodi 21.0-BETA2) a lot of caching issues have been fixed and
    readfactor behaves better. We need to adjust for that.
    """
    useModernAPI = False
    memorySize = 20  # in MB
    readFactor = 4
    defRF = 4
    defRFSM = 20
    recRFRange = "4-10"
    template = None
    orig_tpl_path = os.path.join(ADDON.getAddonInfo('path'), "pm4k_cache_template.xml")
    custom_tpl_path = "special://profile/pm4k_cache_template.xml"
    translated_ctpl_path = translatePath(custom_tpl_path)

    # give Android a little more leeway with its sometimes weird memory management; otherwise stick with 23% of free mem
    safeFactor = .20 if xbmc.getCondVisibility('System.Platform.Android') else .23

    def __init__(self):
        if KODI_BUILD_NUMBER >= 2090821:
            self.memorySize = rpc.Settings.GetSettingValue(setting='filecache.memorysize')['value']
            self.readFactor = rpc.Settings.GetSettingValue(setting='filecache.readfactor')['value'] / 100.0
            if self.readFactor % 1 == 0:
                self.readFactor = int(self.readFactor)
            DEBUG_LOG("Not using advancedsettings.xml for cache/buffer management, we're at least Kodi 21 non-alpha")
            self.useModernAPI = True
            self.defRFSM = 7
            self.recRFRange = "1.5-4"

            if KODI_BUILD_NUMBER >= 2090830:
                self.recRFRange = ADDON.getLocalizedString(32976)

        else:
            self.load()
            self.template = self.getTemplate()

        plexapp.util.APP.on('change:slow_connection',
                            lambda value=None, **kwargs: self.write(readFactor=value and self.defRFSM or self.defRF))

    def getTemplate(self):
        if xbmcvfs.exists(self.custom_tpl_path):
            try:
                f = xbmcvfs.File(self.custom_tpl_path)
                data = f.read()
                f.close()
                if data:
                    return data
            except:
                pass

        DEBUG_LOG("Custom pm4k_cache_template.xml not found, using default")
        f = xbmcvfs.File(self.orig_tpl_path)
        data = f.read()
        f.close()
        return data

    def load(self):
        data = adv.getData()
        if not data:
            return

        cachexml_match = ADV_CACHE_RE.search(data)
        if cachexml_match:
            cachexml = cachexml_match.group(0)

            try:
                self.memorySize = int(ADV_MSIZE_RE.search(cachexml).group(1)) // 1024 // 1024
            except:
                DEBUG_LOG("script.plexmod: invalid or not found memorysize in advancedsettings.xml")

            try:
                self.readFactor = int(ADV_RFACT_RE.search(cachexml).group(1))
            except:
                DEBUG_LOG("script.plexmod: invalid or not found readfactor in advancedsettings.xml")

        #    self._cleanData = data.replace(cachexml, "")
        #else:
        #    self._cleanData = data

    def write(self, memorySize=None, readFactor=None):
        # never write to advancedSettings when we're installed from the Kodi repository and don't have the modern API
        if FROM_KODI_REPOSITORY and not self.useModernAPI:
            return

        memorySize = self.memorySize = memorySize if memorySize is not None else self.memorySize
        readFactor = self.readFactor = readFactor if readFactor is not None else self.readFactor

        if self.useModernAPI:
            # kodi cache settings have moved to Services>Caching
            try:
                rpc.Settings.SetSettingValue(setting='filecache.memorysize', value=self.memorySize)
                rpc.Settings.SetSettingValue(setting='filecache.readfactor', value=int(self.readFactor * 100))
            except:
                pass
            return

        data = adv.getData()
        cd = "<advancedsettings>\n</advancedsettings>"
        if data:
            cachexml_match = ADV_CACHE_RE.search(data)
            if cachexml_match:
                cachexml = cachexml_match.group(0)
                cd = data.replace(cachexml, "")
            else:
                cd = data

        finalxml = "{}\n</advancedsettings>".format(
            cd.replace("</advancedsettings>", self.template.format(memorysize=memorySize * 1024 * 1024,
                                                                   readfactor=readFactor))
        )

        adv.write(finalxml)

    def clamp16(self, x):
        return x - x % 16

    @property
    def viableOptions(self):
        default = list(filter(lambda x: x < self.recMax,
                              [16, 20, 24, 32, 48, 64, 96, 128, 192, 256, 384, 512, 768, 1024]))

        # add option to overcommit slightly
        overcommit = []
        if xbmc.getCondVisibility('System.Platform.Android'):
            overcommit.append(min(self.clamp16(int(self.free * 0.23)), 2048))

        overcommit.append(min(self.clamp16(int(self.free * 0.26)), 2048))
        overcommit.append(min(self.clamp16(int(self.free * 0.3)), 2048))

        # re-append current memorySize here, as recommended max might have changed
        return list(sorted(list(set(default + [self.memorySize, self.recMax] + overcommit))))

    @property
    def readFactorOpts(self):
        ret = list(sorted(list(set([1.25, 1.5, 1.75, 2, 2.5, 3, 4, 5, 7, 10, 15, 20, 30, 50] + [self.readFactor]))))
        if KODI_BUILD_NUMBER >= 2090830 and self.readFactor > 0:
            # support for adaptive read factor from build 2090822 onwards
            ret.insert(0, 0)
        return ret

    @property
    def free(self):
        return float(xbmc.getInfoLabel('System.Memory(free)')[:-2])

    @property
    def recMax(self):
        freeMem = self.free
        recMem = min(int(freeMem * self.safeFactor), 2048)
        LOG("Free memory: {} MB, recommended max: {} MB".format(freeMem, recMem))
        return recMem


kcm = KodiCacheManager()
CACHE_SIZE = kcm.memorySize
