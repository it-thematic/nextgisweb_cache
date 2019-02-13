# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals
from os.path import join
from tempfile import mkdtemp

from mapproxy.config.loader import ProxyConfiguration
from nextgisweb.component import Component
from nextgisweb.env import env

from .util import COMP_ID, _


class CacheComponent(Component):
    identity = COMP_ID

    def initialize(self):
        super(CacheComponent, self).initialize()
        self.proxies = dict()

    def get_proxy(self, resource_id):
        """
        Получение экземпляра mapproxy TileCache по id ресурса

        :param int resource_id: идентификатор ресурса
        :return: экземпляр класса кэша для конкретного ресурса
        :rtype: ProxyConfiguration
        """
        if 'path' not in self.settings:
            self.settings['path'] = env.core.settings.get('sdir', None)
        if not self.settings['path']:
            self.logger.warn(_('Cache store in temporary directory!'))
            self.settings['path'] = mkdtemp(prefix='cache_')

        if resource_id in self.proxies.keys():
            return self.proxies[resource_id]

        conf = dict(
            caches={
                resource_id: dict(
                    cache=dict(
                        type='mbtiles',
                        filename=join(self.settings['path'], '{}.mbtiles'.format(resource_id))
                    ),
                    sources=list(),
                    grids=list('GLOBAL_WEBMERCATOR', ),
                    bulk_meta_tiles=True,
                    link_single_color_images=True,
                )
            }
        )

        self.proxies[resource_id] = ProxyConfiguration(conf=conf)
        return self.proxies[resource_id]

    def setup_pyramid(self, config):
        from . import api
        api.setup_pyramid(self, config)


def pkginfo():
    return dict(
        components=dict(
            cache="nextgisweb_cache"
        )
    )


def amd_packages():
    return ()
