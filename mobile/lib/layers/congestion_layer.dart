// TomTom traffic flow, drawn under the basemap's street labels.
// Mirrors dashboard/src/layers/congestion.ts. Everything the dashboard spec decides (tile URL and
// type, source, layer, paint) is a constant below, so syncing is editing these, not the functions.
import 'dart:convert';

import 'package:mapbox_maps_flutter/mapbox_maps_flutter.dart';

import '../config/makati.dart';

// ---- Sync with dashboard/src/layers/congestion.ts ------------------------------------------
// Tile URL. The segment before {z} is TomTom's flow style (absolute | relative | relative-delay |
// reduced-sensitivity); the extension is the tile type (png raster | pbf vector).
const congestionTiles = 'https://api.tomtom.com/traffic/map/4/tile/flow/relative/{z}/{x}/{y}.png';
const congestionThickness = 10; // TomTom 1-20, default 10: lower = thinner bands (png only)
const congestionTileSize = 256; // TomTom 256 | 512 (png only); congestionSource must match
// Query added after `key=`; the cache-buster `t=` follows it.
const congestionQuery = 'thickness=$congestionThickness&tileSize=$congestionTileSize';
// The Mapbox source and layer as style-spec JSON, the same shape as the dashboard's addSource and
// addLayer. Added by the code below: source `tiles`, `bounds`, `attribution`; layer `id`, `source`.
const congestionSource = {'type': 'raster', 'tileSize': congestionTileSize};
const congestionLayer = {
  'type': 'raster',
  'paint': {'raster-opacity': 0.85},
};
const congestionRefresh = Duration(seconds: 120);
// ---------------------------------------------------------------------------------------------

const _id = 'congestion';

// `stamp` busts the tile cache so a refresh really refetches.
String _tileUrl(String key, DateTime stamp) =>
    '$congestionTiles?key=${Uri.encodeComponent(key)}&$congestionQuery'
    '&t=${stamp.millisecondsSinceEpoch}';

/// (Re)draws the layer. Raw style-spec JSON on purpose: in mapbox_maps_flutter 3.0.0 the typed
/// `addLayer(layer, position)` drops its position (style_manager.dart passes null), while
/// `addStyleLayer(json, position)` honours it.
Future<void> addCongestion(MapboxMap map, String key, DateTime stamp) async {
  await removeCongestion(map);
  await map.addStyleSource(
    _id,
    jsonEncode({
      ...congestionSource,
      'tiles': [_tileUrl(key, stamp)],
      'bounds': [Makati.west, Makati.south, Makati.east, Makati.north], // no tiles outside the city
      'attribution': 'Traffic © TomTom',
    }),
  );
  // Under the first symbol layer, so street labels stay readable on top.
  final layers = await map.getStyleLayers();
  final label = layers.firstWhere((l) => l?.type == 'symbol', orElse: () => null)?.id;
  await map.addStyleLayer(
    jsonEncode({'id': _id, 'source': _id, ...congestionLayer}),
    label == null ? null : LayerPosition(below: label),
  );
}

/// Layer first: a source still used by a layer cannot be removed.
Future<void> removeCongestion(MapboxMap map) async {
  if (await map.styleLayerExists(_id)) await map.removeStyleLayer(_id);
  if (await map.styleSourceExists(_id)) await map.removeStyleSource(_id);
}
