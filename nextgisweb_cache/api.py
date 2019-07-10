# -*- coding: utf-8 -*-
from __future__ import absolute_import

from StringIO import StringIO

from mapproxy.cache.tile import Tile, TileCreator, TileManager
from mapproxy.image import BlankImageSource, Image, ImageSource
from mapproxy.image.opts import ImageOptions
from mapproxy.service.tile import TileServiceGrid

from nextgisweb.env import env
from nextgisweb.render.api import tile as render_tile
from nextgisweb.resource import DataScope, Resource

from pyramid.response import Response
from pyramid.exceptions import HTTPBadRequest


PD_READ = DataScope.read
sett_name = 'permissions.disable_check.rendering'


class TileCreatorEx(TileCreator):

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request')
        super(TileCreatorEx, self).__init__(*args, **kwargs)

    def create_tiles(self, tiles):
        return self._create_single_tiles(tiles)

    def _create_single_tile(self, tile):
        with self.tile_mgr.lock(tile):
            if not self.is_cached(tile):
                response = render_tile(self.request)  # type: Response
                buf = StringIO(response.body)
                buf.seek(0)
                image = Image.open(buf)
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

    def internal_tile_coord(tile_manager, tile_coord, use_profiles):
        """
        Преобразование координат к правильному виду

        :param TileManager tile_manager: параметры тайловой сетки
        :param tuple[int, int, int] tile_coord: координаты тайла
        :param bool use_profiles:
        :return:
        :rtype: tuple[int, int, int]
        """
        grid_service = TileServiceGrid(tile_manager.grid)  # type: TileServiceGrid
        coord = grid_service.internal_tile_coord(tile_coord, use_profiles)
        if coord is None:
            raise HTTPBadRequest(b'Недопустимые значения тайловых координат')
        return grid_service.flip_tile_coord(coord)

    setting_disable_check = request.env.core.settings.get(sett_name, 'false').lower()
    if setting_disable_check in ('true', 'yes', '1'):
        setting_disable_check = True
    else:
        setting_disable_check = False

    z = int(request.GET['z'])
    x = int(request.GET['x'])
    y = int(request.GET['y'])

    p_resource = map(None, filter(None, request.GET['resource'].split(',')))

    aimg = None
    for resource_id in p_resource:
        obj = Resource.filter_by(id=resource_id).one()
        if not setting_disable_check:
            request.resource_permission(PD_READ, obj)
        
        resource_proxy = env.cache.get_proxy(resource_id)
        caches = resource_proxy.caches[resource_id].caches()
        tile_manager = None  # type: TileManager
        grid, extent, tile_manager = caches[0]
        tile_coord = internal_tile_coord(tile_manager, (x, y, z), True)
        tile = Tile(tile_coord)  # type: Tile
        with tile_manager.session():
            # Попытка загрузки тайла из кэша
            tile_manager.cache.load_tile(tile, with_metadata=True)
            print
            if tile.coord is not None and not is_cached(tile_manager, tile):
                creator = TileCreatorEx(tile_manager, dimensions={}, request=request)
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
            aimg = tile.source.as_image()
        else:
            try:
                aimg = Image.alpha_composite(aimg, tile.source.as_image())
            except ValueError:
                env.cache.logger.error(b'Ошибка объединения очередного тайла')

    if aimg is None:
        aimg = Image.new(b'RGBA', (256, 256))

    buf = StringIO()
    aimg.save(buf, b'png')
    buf.seek(0)

    return Response(body_file=buf, content_type=b'image/png')


def setup_pyramid(comp, config):
    config.add_route('render.cache', '/api/component/render/cache').add_view(cache)
