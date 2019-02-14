# -*- coding: utf-8 -*-
from __future__ import absolute_import

from StringIO import StringIO

from mapproxy.cache.tile import Tile, TileCreator, TileManager
from mapproxy.image import BlankImageSource, Image, ImageSource
from mapproxy.image.opts import ImageOptions

from nextgisweb.env import env
from nextgisweb.render.api import tile as render_tile
from nextgisweb.resource import DataScope, Resource

from pyramid.response import Response


PD_READ = DataScope.read
sett_name = 'permissions.disable_check.rendering'


class TileCreatorEx(TileCreator):

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request')
        super(TileCreatorEx, self).__init__(*args, **kwargs)

    def _create_single_tile(self, tile):
        with self.tile_mgr.lock(tile):
            if not self.is_cached(tile):
                response = render_tile(self.request)  # type: Response
                buf = StringIO(response.body)
                buf.seek(0)
                image = Image.Image.open(buf)
                source = ImageSource(image, cacheable=True)
                if not source:
                    return []
                if self.tile_mgr.image_opts != source.image_opts:
                    # call as_buffer to force conversion into cache format
                    source.as_buffer(self.tile_mgr.image_opts)
                source.image_opts = self.tile_mgr.image_opts
                tile.source = source
                tile.cacheable = source.cacheable
                tile = self.tile_mgr.apply_tile_filter(tile)
                if source.cacheable:
                    self.cache.store_tile(tile)
            else:
                self.cache.load_tile(tile)
        return [tile]


def cache(request):

    def is_cached(tile_manager, tile):
        """
        Проверка тайла в кэше
        :param TileManager tile_manager:
        :param Tile tile:
        :return:
        :rtype: bool
        """
        if isinstance(tile, tuple):
            tile = Tile(tile)
        if tile.coord is None:
            return True
        return tile_manager.cache.is_cached(tile)

    z = int(request.GET['z'])
    x = int(request.GET['x'])
    y = int(request.GET['y'])

    p_resource = request.GET['resource'].split(',')
    aimg = None
    for resource_id in p_resource:
        resource_proxy = env.cache.get_proxy(resource_id)
        caches = resource_proxy.caches[resource_id].caches()
        tile_manager = None  # type: TileManager
        grid, extent, tile_manager = caches[0]
        with tile_manager.session():
            tile = Tile(z, x, y)  # type: Tile
            # Попытка загрузки тайла из кэша
            tile_manager.cache.load_tile(tile, with_metadata=True)
            if tile.coord is not None and not is_cached(tile_manager, tile):
                creator = TileCreatorEx(tile_manager, dimensions={})
                created_tiles = creator.create_tiles([tile])
                for created_tile in created_tiles:
                    if created_tile.coord == tile.coord:
                        tile = created_tile
                        if tile.source is None:
                            img = BlankImageSource(size=grid.tile_size,
                                                   image_opts=ImageOptions(format=format, transparent=True)
                                                   )
                            tile.source = img.as_buffer().read()

        if not aimg:
            aimg = tile.source
        else:
            try:
                aimg = Image.alpha_composite(aimg, tile.source)
            except ValueError:
                env.cache.logger.error('Ошибка объединения очередного тайла')

    if aimg is None:
        aimg = Image.new('RGBA', (256, 256))

    buf = StringIO()
    aimg.save(buf, 'png')
    buf.seek(0)

    return Response(body_file=buf, content_type=b'image/png')


def setup_pyramid(comp, config):
    config.add_route('render.cache', '/api/component/render/cache').add_view(cache)
