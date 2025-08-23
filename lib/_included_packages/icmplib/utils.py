'''
    icmplib
    ~~~~~~~

    Easily forge ICMP packets and make your own ping and traceroute.

        https://github.com/ValentinBELYN/icmplib

    :copyright: Copyright 2017-2023 Valentin BELYN.
    :license: GNU LGPLv3, see the LICENSE for details.

    ~~~~~~~

    This program is free software: you can redistribute it and/or
    modify it under the terms of the GNU Lesser General Public License
    as published by the Free Software Foundation, either version 3 of
    the License, or (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU Lesser General Public License for more details.

    You should have received a copy of the GNU Lesser General Public
    License along with this program.  If not, see
    <https://www.gnu.org/licenses/>.
'''

import socket, asyncio

from threading import Lock
from sys import platform
from os import getpid
from re import match
from random import choices

from .exceptions import NameLookupError


PID = getpid()
PLATFORM_LINUX   = platform == 'linux'
PLATFORM_MACOS   = platform == 'darwin'
PLATFORM_WINDOWS = platform == 'win32'

_lock_id = Lock()
_current_id = PID


def random_byte_message(size):
    '''
    Generate a random byte sequence of the specified size.

    '''
    sequence = choices(
        b'abcdefghijklmnopqrstuvwxyz'
        b'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
        b'1234567890', k=size)

    return bytes(sequence)


def unique_identifier():
    '''
    Generate a unique identifier between 0 and 65535.
    The first number generated will be equal to the PID + 1.

    '''
    global _current_id

    with _lock_id:
        _current_id += 1
        _current_id &= 0xffff

        return _current_id


def resolve(name, family=None, use_orig=False):
    '''
    Resolve a hostname or FQDN to an IP address. Depending on the name
    specified in parameters, several IP addresses may be returned.

    This function relies on the DNS name server configured on your
    operating system.

    :type name: str
    :param name: A hostname or a Fully Qualified Domain Name (FQDN).

    :type family: int, optional
    :param family: The address family. Can be set to `4` for IPv4 or `6`
        for IPv6 addresses. By default, this function searches for IPv4
        addresses first for compatibility reasons (A DNS lookup) before
        searching for IPv6 addresses (AAAA DNS lookup).

    :rtype: list[str]
    :returns: A list of IP addresses corresponding to the name passed as
        a parameter.

    :raises NameLookupError: If the requested name does not exist or
        cannot be resolved.

    '''
    try:
        if family == 6:
            _family = socket.AF_INET6
        else:
            _family = socket.AF_INET

        func = socket.getaddrinfo if use_orig else socket.getaddrinfo_orig

        lookup = func(
            host=name,
            port=None,
            family=_family,
            type=socket.SOCK_DGRAM)

        return [address[4][0] for address in lookup]

    except OSError:
        if not family:
            return resolve(name, 6)

    raise NameLookupError(name)


async def async_resolve(name, family=None):
    '''
    Resolve a hostname or FQDN to an IP address. Depending on the name
    specified in parameters, several IP addresses may be returned.

    This function relies on the DNS name server configured on your
    operating system.

    This function is non-blocking.

    :type name: str
    :param name: A hostname or a Fully Qualified Domain Name (FQDN).

    :type family: int, optional
    :param family: The address family. Can be set to `4` for IPv4 or `6`
        for IPv6 addresses. By default, this function searches for IPv4
        addresses first for compatibility reasons (A DNS lookup) before
        searching for IPv6 addresses (AAAA DNS lookup).

    :rtype: list[str]
    :returns: A list of IP addresses corresponding to the name passed as
        a parameter.

    :raises NameLookupError: If the requested name does not exist or
        cannot be resolved.

    '''
    try:
        if family == 6:
            _family = socket.AF_INET6
        else:
            _family = socket.AF_INET

        loop = asyncio.get_running_loop()

        lookup = await loop.getaddrinfo(
            host=name,
            port=None,
            family=_family,
            type=socket.SOCK_DGRAM)

        return [address[4][0] for address in lookup]

    except OSError:
        if not family:
            return await async_resolve(name, 6)

    raise NameLookupError(name)


def is_hostname(name):
    '''
    Indicate whether the specified name is a hostname or an FQDN.
    Return a `boolean`.

    '''
    pattern = r'(?i)^([a-z0-9-]+|([a-z0-9_-]+[.])+[a-z]+)$'
    return match(pattern, name) is not None


def is_ipv4_address(address):
    '''
    Indicate whether the specified address is an IPv4 address.
    Return a `boolean`.

    '''
    pattern = r'^([0-9]{1,3}[.]){3}[0-9]{1,3}$'
    return match(pattern, address) is not None


def is_ipv6_address(address):
    '''
    Indicate whether the specified address is an IPv6 address.
    Return a `boolean`.

    '''
    return ':' in address
