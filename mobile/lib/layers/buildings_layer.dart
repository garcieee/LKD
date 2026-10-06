// 3D buildings, Organic Maps style: opaque grey blocks whose sides shade against their roofs.
// Drawn from the base style's own building tiles, so it needs no extra source or key.
import 'dart:convert';

import 'package:mapbox_maps_flutter/mapbox_maps_flutter.dart';

const _id = 'lakad-buildings';

final _layer = {
  'id': _id,
  'type': 'fill-extrusion',
  'source': 'composite',
  'source-layer': 'building',
  'minzoom': 15,
  'paint': {
    'fill-extrusion-color': '#e3dfda', // warm grey: roofs; the light shades the walls darker
    // Rise out of the ground between zoom 15 and 16 instead of popping in.
    'fill-extrusion-height': ['interpolate', ['linear'], ['zoom'], 15, 0, 16, ['coalesce', ['get', 'height'], 10]],
    'fill-extrusion-base': ['interpolate', ['linear'], ['zoom'], 15, 0, 16, ['coalesce', ['get', 'min_height'], 0]],
    'fill-extrusion-opacity': 1,
    'fill-extrusion-vertical-gradient': true,
  },
};

/// Adds the extruded buildings under the labels, once per style load. Safe to call again.
Future<void> addBuildings(MapboxMap map) async {
  if (await map.styleLayerExists(_id)) return;
  // Under the first label layer, so street names stay readable over the blocks.
  final layers = await map.getStyleLayers();
  final label = layers.where((l) => l?.type == 'symbol').firstOrNull;
  await map.addStyleLayer(jsonEncode(_layer), label == null ? null : LayerPosition(below: label.id));
}
