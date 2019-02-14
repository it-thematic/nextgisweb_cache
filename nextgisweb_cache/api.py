# -*- coding: utf-8 -*-
from __future__ import absolute_import

from StringIO import StringIO

from mapproxy.cache.tile import Tile
from mapproxy.image import Image, ImageSource

from nextgisweb.env import env
from nextgisweb.render.api import tile as render_tile
from nextgisweb.resource import DataScope, Resource

from pyramid.response import Response


PD_READ = DataScope.read
sett_name = 'permissions.disable_check.rendering'


def cache(request):
    z = int(request.GET['z'])
    x = int(request.GET['x'])
    y = int(request.GET['y'])

    p_resource = request.GET['resource'].split(',')
    aimg = None
    for resource_id in p_resource:
        resource_proxy = env.cache.get_proxy(resource_id)
        caches = resource_proxy.caches[resource_id].caches()
        grid, extent, tile_manager = caches[0]
        tile = Tile((z, x, y))  # type: Tile
        with tile_manager.session():
            with tile_manager.lock(tile):
                # Загрузка тайла из кэша
                tile_manager.cache.load_tile(tile)
                # Если тайл не содержится в кэше
                if tile.coord is not None and not tile_manager.cache.is_cached(tile):
                    env.cache.logger.debug('Тайла нет в кэше. Запрос из истчника (component/tile)')
                    response = render_tile(request)
                    env.cache.logger.debug('Тайл из источника получен. Сохранение в кэш.')

                    buf = StringIO(response.body)
                    buf.seek(0)
                    source = ImageSource(Image.open(buf), cacheable=True)  # type: ImageSource
                    source.as_buffer(tile_manager.image_opts)
                    source.image_opts = tile_manager.image_opts
                    print source
                    tile.source = source
                    tile.cacheable = source.cacheable
                    tile = tile_manager.apply_tile_filter(tile)
                    if source.cacheable:
                        tile_manager.cache.store_tile(tile)

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
