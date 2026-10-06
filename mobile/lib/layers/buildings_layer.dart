// 3D buildings, Organic Maps style: grey blocks whose walls shade darker than their roofs.
// Drawn from the base style's own building tiles, so it needs no extra source or key.
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:mapbox_maps_flutter/mapbox_maps_flutter.dart';

const _id = 'lakad-buildings';
const _source = 'composite'; // the vector source the Mapbox styles keep their buildings in

// A missing or zero height (common in OSM-derived tiles) would draw a flat roof: use 10 m, about 3 floors.
const _height = ['to-number', ['get', 'height'], 0];

final _layer = {
  'id': _id,
  'type': 'fill-extrusion',
  'source': _source,
  'source-layer': 'building',
  'minzoom': 15,
  'paint': {
    // Darker than light-v11's near-white ground, or the blocks vanish into it.
    'fill-extrusion-color': '#bab6b0', // 10% darker than the first try, for a firmer block
    'fill-extrusion-height': ['case', ['>', _height, 0], _height, 10],
    'fill-extrusion-base': ['to-number', ['get', 'min_height'], 0],
    'fill-extrusion-opacity': 1,
    'fill-extrusion-vertical-gradient': true, // walls darken towards the ground
  },
};

Future<void> removeBuildings(MapboxMap map) async {
  if (await map.styleLayerExists(_id)) await map.removeStyleLayer(_id);
}

/// Adds the extruded buildings under the labels, once per style load. Safe to call again.
// ponytail: no setLights() sun. In Mapbox's 3D light model it would dim every other layer too;
// walls shade by the vertical gradient only. Upgrade: setLights plus emissive strength on the rest.
Future<void> addBuildings(MapboxMap map) async {
  if (await map.styleLayerExists(_id)) return;
  if (!await map.styleSourceExists(_source)) {
    final sources = [for (final s in await map.getStyleSources()) s?.id];
    debugPrint('buildings layer: no "$_source" source, the style has $sources');
    return;
  }
  // Under the first label layer, so street names stay readable over the blocks.
  final layers = await map.getStyleLayers();
  final label = layers.where((l) => l?.type == 'symbol').firstOrNull;
  await map.addStyleLayer(jsonEncode(_layer), label == null ? null : LayerPosition(below: label.id));
  debugPrint('buildings layer: added below ${label?.id ?? 'the top'}');
}
