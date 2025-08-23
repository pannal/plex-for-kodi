from __future__ import absolute_import
import sys
import os
import re
import traceback
import requests
import socket
import urllib3
import datetime
from . import threadutils
import six.moves.urllib.request, six.moves.urllib.parse, six.moves.urllib.error
import mimetypes
import functools
from . import plexobjects
from xml.etree import ElementTree

from . import asyncadapter

from . import callback
from . import util

codes = requests.codes
status_codes = requests.status_codes._codes


DEFAULT_TIMEOUT = asyncadapter.AsyncTimeout(util.TIMEOUT).setConnectTimeout(util.TIMEOUT)

RESOLVED_PD_HOSTS = {}

CURRENT_ACME_CRT_DATE = datetime.date(year=2035, month=6, day=3)
TODAY = datetime.date.today()

_getaddrinfo = socket.getaddrinfo


def pgetaddrinfo(host, port, *args, **kwargs):
    """
    "circumvent" DNS rebind protection for our requests. this does not apply to Kodi requests (assets etc.)
    """
    if host.endswith("plex.direct"):
        v6 = host.count("-") > 3
        if host in RESOLVED_PD_HOSTS:
            ip = RESOLVED_PD_HOSTS[host]
        else:
            base = host.split(".", 1)[0]
            ip = RESOLVED_PD_HOSTS[host] = v6 and base.replace("-", ":") or base.replace("-", ".")
            util.DEBUG_LOG("Dynamically resolving {} to {}", host, ip)

        fam = v6 and socket.AF_INET6 or socket.AF_INET
        stype = kwargs.get("type", kwargs.get("socktype", socket.SOCK_STREAM))
        proto = kwargs.get("proto", socket.IPPROTO_TCP)

        return [(fam, stype, proto, '', (ip, port))]
    return _getaddrinfo(host, port, *args, **kwargs)


socket.getaddrinfo = pgetaddrinfo
socket.getaddrinfo_orig = _getaddrinfo


def GET(*args, **kwargs):
    return requests.get(*args, headers=util.BASE_HEADERS.copy(), timeout=DEFAULT_TIMEOUT, **kwargs)


def POST(*args, **kwargs):
    return requests.post(*args, headers=util.BASE_HEADERS.copy(), timeout=DEFAULT_TIMEOUT, **kwargs)


def Session():
    s = asyncadapter.Session()
    s.request = functools.partial(s.request, timeout=DEFAULT_TIMEOUT)
    s.headers = util.BASE_HEADERS.copy()

    return s


class RequestContext(dict):
    def __getattr__(self, attr):
        return self.get(attr)

    def __setattr__(self, attr, value):
        self[attr] = value


class HttpRequest(object):
    __slots__ = ("server", "path", "hasParams", "ignoreResponse", "session", "currentResponse", "method", "url",
                 "thread", "__dict__")
    _cancel = False

    USE_SYSTEM_CERT_BUNDLE = False

    def __init__(self, url, method=None):
        self.server = None
        self.path = None
        self.hasParams = '?' in url
        self.ignoreResponse = False
        self.session = asyncadapter.Session()
        self.session.headers = util.BASE_HEADERS.copy()
        self.currentResponse = None
        self.method = method
        self.url = url
        self.thread = None

        # Use a specific CA cert bundle if applicable
        if not self.USE_SYSTEM_CERT_BUNDLE and util.USE_CERT_BUNDLE != "system" and url[:5] == "https":
            if util.USE_CERT_BUNDLE == "custom":
                # noinspection PyTypeChecker
                self.session.verify = os.path.join(util.translatePath(util.ADDON.getAddonInfo("profile")),
                                                 "custom_bundle.crt")

            elif util.USE_CERT_BUNDLE == "acme" and TODAY <= CURRENT_ACME_CRT_DATE:
                self.session.verify = os.path.join(
                    os.path.dirname(os.path.realpath(__file__)), 'certs', 'acme.bundle.crt')
            #else:
            #    self.session.cert = os.path.join(certsPath, 'ca-bundle.crt')

    def removeAsPending(self):
        from . import plexapp
        util.APP.delRequest(self)

    def startAsync(self, *args, **kwargs):
        self.thread = threadutils.KillableThread(target=self._startAsync, args=args, kwargs=kwargs, name='HTTP-ASYNC:{0}'.format(self.url))
        self.thread.start()
        return True

    def _startAsync(self, body=None, contentType=None, context=None):
        timeout = context and context.timeout or DEFAULT_TIMEOUT
        self.logRequest(body, timeout)
        if self._cancel:
            return
        try:
            if self.method == 'PUT':
                res = self.session.put(self.url, timeout=timeout, stream=True)
            elif self.method == 'DELETE':
                res = self.session.delete(self.url, timeout=timeout, stream=True)
            elif self.method == 'HEAD':
                res = self.session.head(self.url, timeout=timeout, stream=True)
            elif self.method == 'OPTIONS':
                res = self.session.options(self.url, timeout=timeout, stream=True)
            elif self.method == 'POST' or body is not None:
                if not contentType:
                    self.session.headers["Content-Type"] = "application/x-www-form-urlencoded"
                else:
                    self.session.headers["Content-Type"] = mimetypes.guess_type(contentType)

                res = self.session.post(self.url, data=body or None, timeout=timeout, stream=True)
            else:
                res = self.session.get(self.url, timeout=timeout, stream=True)
            self.currentResponse = res

            if self._cancel:
                return
        except asyncadapter.TimeoutException:
            from . import plexapp
            plexapp.util.APP.onRequestTimeout(context)
            self.removeAsPending()
            return
        except asyncadapter.CanceledException:
            return
        except (urllib3.exceptions.ProtocolError, requests.exceptions.ConnectionError):
            self.removeAsPending()
            return
        except Exception as e:
            util.ERROR('Request failed {0}'.format(util.cleanToken(self.url)))
            if not hasattr(e, 'response'):
                return
            res = e.response

        self.onResponse(res, context)

        self.removeAsPending()

    def getWithTimeout(self, timeout=DEFAULT_TIMEOUT):
        return HttpObjectResponse(self.getPostWithTimeout(timeout), self.path, self.server)

    def postWithTimeout(self, timeout=DEFAULT_TIMEOUT, body=None):
        self.method = 'POST'
        return HttpObjectResponse(self.getPostWithTimeout(timeout, body), self.path, self.server)

    def getToStringWithTimeout(self, timeout=DEFAULT_TIMEOUT):
        res = self.getPostWithTimeout(timeout)
        if not res:
            return ''
        return res.text.encode('utf8')

    def postToStringWithTimeout(self, body=None, timeout=DEFAULT_TIMEOUT):
        self.method = 'POST'
        res = self.getPostWithTimeout(timeout, body)
        if not res:
            return ''
        return res.text.encode('utf8')

    def getPostWithTimeout(self, timeout=DEFAULT_TIMEOUT, body=None):
        if self._cancel:
            return

        self.logRequest(body, timeout=timeout, _async=False)
        try:
            if self.method == 'PUT':
                res = self.session.put(self.url, timeout=timeout, stream=True)
            elif self.method == 'DELETE':
                res = self.session.delete(self.url, timeout=timeout, stream=True)
            elif self.method == 'HEAD':
                res = self.session.head(self.url, timeout=timeout, stream=True)
            elif self.method == 'POST' or body is not None:
                res = self.session.post(self.url, data=body, timeout=timeout, stream=True)
            else:
                res = self.session.get(self.url, timeout=timeout, stream=True)

            self.currentResponse = res

            if self._cancel:
                return None

            util.LOG("Got a {0} from {1}", res.status_code, util.cleanToken(self.url))
            # self.event = msg
            return res
        except Exception as e:
            info = traceback.extract_tb(sys.exc_info()[2])[-1]
            util.WARN_LOG(
                "Request errored out - URL: {0} File: {1} Line: {2} Msg: {3}".format(util.cleanToken(self.url), os.path.basename(info[0]), info[1], getattr(e, 'message', ''))
            )

        return None

    def wasOK(self):
        return self.currentResponse and self.currentResponse.ok

    def wasNotFound(self):
        return self.currentResponse is not None and self.currentResponse.status_code == requests.codes.not_found

    def getIdentity(self):
        return str(id(self))

    def getUrl(self):
        return self.url

    def getRelativeUrl(self):
        url = self.getUrl()
        m = re.match(r'^\w+://.+?(/.+)', url)
        if m:
            return m.group(1)
        return url

    def killSocket(self):
        if not self.currentResponse:
            return

        try:
            socket.fromfd(self.currentResponse.raw.fileno(), socket.AF_INET, socket.SOCK_STREAM).shutdown(socket.SHUT_RDWR)
            return
        except AttributeError:
            pass
        except Exception as e:
            util.ERROR(err=e)

        try:
            self.currentResponse.raw._fp.fp._sock.shutdown(socket.SHUT_RDWR)
        except AttributeError:
            pass
        except Exception as e:
            util.ERROR(err=e)

    def cancel(self):
        self._cancel = True
        self.session.cancel()
        self.removeAsPending()
        self.killSocket()

    def addParam(self, encodedName, value):
        if self.hasParams:
            self.url += "&" + encodedName + "=" + six.moves.urllib.parse.quote_plus(value)
        else:
            self.hasParams = True
            self.url += "?" + encodedName + "=" + six.moves.urllib.parse.quote_plus(value)

    def addHeader(self, name, value):
        self.session.headers[name] = value

    def createRequestContext(self, requestType, callback_=None, timeout=None):
        context = RequestContext()
        context.requestType = requestType
        context.timeout = timeout or DEFAULT_TIMEOUT

        if callback_:
            context.callback = callback.Callable(self.onResponse)
            context.completionCallback = callback_
            context.callbackCtx = callback_.context

        return context

    def onResponse(self, event, context):
        if context.completionCallback:
            response = HttpResponse(event)
            context.completionCallback(self, response, context)

    def logRequest(self, body, timeout=None, _async=True):
        # Log the real request method
        method = self.method
        if not method:
            method = body is not None and "POST" or "GET"
        util.LOG(
            "Starting request: {0} {1} (async={2} timeout={3})".format(method, util.cleanToken(self.url),
                                                                       _async, timeout)
        )


class HttpResponse(object):
    def __init__(self, event):
        self.event = event
        if not self.event is None:
            self.event.content  # force data to be read
            self.event.close()

    def isSuccess(self):
        if not self.event:
            return False
        return self.event.status_code >= 200 and self.event.status_code < 300

    def isError(self):
        return not self.isSuccess()

    def getStatus(self):
        if self.event is None:
            return 0
        return self.event.status_code

    def getBodyString(self):
        if self.event is None:
            return ''
        return self.event.text.encode('utf-8')

    def getErrorString(self):
        if self.event is None:
            return ''
        return self.event.reason

    def getBodyXml(self):
        if not self.event is None:
            return ElementTree.fromstring(self.getBodyString())

        return None

    def getResponseHeader(self, name):
        if self.event is None:
            return None
        return self.event.headers.get(name)


class HttpObjectResponse(HttpResponse, plexobjects.PlexContainer):
    def __init__(self, response, path, server=None):
        self.event = response
        if self.event:
            self.event.content  # force data to be read
            self.event.close()

        data = self.getBodyXml()

        plexobjects.PlexContainer.__init__(self, data, initpath=path, server=server, address=path)
        self.container = self

        self.items = plexobjects.listItems(server, path, data=data, container=self)


def addRequestHeaders(transferObj, headers=None):
    if isinstance(headers, dict):
        for header in headers:
            transferObj.addHeader(header, headers[header])
            util.DEBUG_LOG("Adding header to {0}: {1}: {2}", transferObj, header, headers[header])


def addUrlParam(url, param):
    return url + ('?' in url and '&' or '?') + param
