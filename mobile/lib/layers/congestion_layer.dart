// TomTom traffic flow as vector tiles: one thin line per carriageway, coloured by how slow it is,
// under the basemap's street labels. Mirrors dashboard/src/layers/congestion.ts (its source spec and
// congestionLayer()): keep the two in step.
// Vector, not TomTom's PNG tiles: the PNGs paint every carriageway as a fat band, and where roads run
// close (the Skyway over Osmeña Highway) the bands stack into one blob at zoom 17-19.
import 'dart:convert';

import 'package:mapbox_maps_flutter/mapbox_maps_flutter.dart';

import '../config/makati.dart';

const congestionRefresh = Duration(seconds: 120);

const _id = 'congestion';
// Flow style "relative": current speed against free-flow speed, which is congestion.
const _tiles = 'https://api.tomtom.com/traffic/map/4/tile/flow/relative/{z}/{x}/{y}.pbf';
// traffic_level snapped to tenths: TomTom merges neighbouring segments, so tiles are smaller.
const _levelStep = 0.1;
// Layer inside the tiles. Each feature is a road segment with traffic_level (current over free-flow
// speed: 1 free flow, 0 standstill), traffic_road_coverage ("full" | "one_side") and road_type.
const _sourceLayer = 'Traffic flow';

// traffic_level -> colour, ascending as Mapbox needs.
const _ramp = [(0.0, '#e54b4b'), (0.33, '#f28c28'), (0.67, '#f7d154'), (1.0, '#2ecc71')];

// Line width in px by zoom for a main road. Thin on purpose: close carriageways touch when wider.
const _width = [(11, 2.2), (13, 3.0), (15, 3.4), (17, 3.4), (19, 6.0)];
const _roadScale = [
  'match',
  ['get', 'road_type'],
  ['Motorway', 'International road', 'Major road', 'Secondary road'],
  1,
  ['Connecting road', 'Major local road'],
  0.8,
  0.6, // Local road, Minor local road
];

// Mapbox allows "zoom" only as the input of a top-level interpolate, so the per-feature part goes in
// each stop's output.
List<Object> _byZoom(Object Function(double w) px) => [
  'interpolate',
  ['exponential', 1.5],
  ['zoom'],
  for (final (z, w) in _width) ...[z, px(w)],
];

final _layer = {
  'id': _id,
  'type': 'line',
  'source': _id,
  'source-layer': _sourceLayer,
  'layout': {
    'line-cap': 'round',
    'line-join': 'round',
    'line-sort-key': ['-', 1, ['get', 'traffic_level']], // worst congestion draws last, on top
  },
  'paint': {
    'line-color': [
      'interpolate',
      ['linear'],
      ['get', 'traffic_level'],
      for (final (level, color) in _ramp) ...[level, color],
    ],
    'line-width': _byZoom((w) => ['*', _roadScale, w]),
    // "one_side" is one direction of a two-way road, drawn the way traffic goes. Shifting it right of
    // that (the Philippines drives on the right) sets both directions side by side; "full" stays centred.
    'line-offset': _byZoom(
      (w) => [
        'case',
        ['==', ['get', 'traffic_road_coverage'], 'one_side'],
        ['*', _roadScale, w / 2],
        0,
      ],
    ),
  },
};

// `stamp` busts the tile cache so each refresh really refetches.
String _tileUrl(String key, DateTime stamp) =>
    '$_tiles?key=${Uri.encodeComponent(key)}&trafficLevelStep=$_levelStep'
    '&t=${stamp.millisecondsSinceEpoch}';

/// (Re)draws the layer; each refresh rebuilds the source with a new `t`. Raw style-spec JSON on
/// purpose: in mapbox_maps_flutter 3.0.0 the typed `addLayer(layer, position)` drops its position
/// (style_manager.dart passes null), while `addStyleLayer(json, position)` honours it. The JSON is
/// also the dashboard's, expression for expression.
Future<void> addCongestion(MapboxMap map, String key, DateTime stamp) async {
  await removeCongestion(map);
  await map.addStyleSource(
    _id,
    jsonEncode({
      'type': 'vector',
      'tiles': [_tileUrl(key, stamp)],
      'bounds': [Makati.west, Makati.south, Makati.east, Makati.north], // no tiles outside the city
      'attribution': 'Traffic © TomTom',
    }),
  );
  // Under the first symbol layer, so street labels stay readable on top.
  final layers = await map.getStyleLayers();
  final label = layers.firstWhere((l) => l?.type == 'symbol', orElse: () => null)?.id;
  await map.addStyleLayer(jsonEncode(_layer), label == null ? null : LayerPosition(below: label));
}

/// Layer first: a source still used by a layer cannot be removed.
Future<void> removeCongestion(MapboxMap map) async {
  if (await map.styleLayerExists(_id)) await map.removeStyleLayer(_id);
  if (await map.styleSourceExists(_id)) await map.removeStyleSource(_id);
}
