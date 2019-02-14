# -*- coding: utf-8 -*-
from nextgisweb.webmap.adapter import WebMapAdapter
from .util import _


@WebMapAdapter.registry.register
class CacheAdapter(object):
    """ An adapter that implements visulation of layer style through
    cache service, but the service itself is implemented by other component. """

    identity = 'cache'
    mid = 'ngw-cache/CacheAdapter'
    display_name = _("Cache")
