// The walking route: a navy line with a white casing, under the report and destination pins.
// map/map_view.dart draws the mode the user has chosen (state/trip_state.dart).
import 'dart:convert';

import 'package:mapbox_maps_flutter/mapbox_maps_flutter.dart';

import '../api/api_client.dart';
import '../theme.dart';

const _id = 'route';
const _casingId = 'route-casing';

String get _navy => '#${(navy.toARGB32() & 0xFFFFFF).toRadixString(16).padLeft(6, '0')}';

Map<String, Object> _line(String id, String color, List<Object> width) => {
  'id': id,
  'type': 'line',
  'source': _id,
  'layout': {'line-cap': 'round', 'line-join': 'round'},
  'paint': {'line-color': color, 'line-width': width},
};

/// Draws [route], or removes the line when it is null. Adds the source and layers when a style load has
/// cleared them. Raw style-spec JSON, like reports_layer.dart.
Future<void> showRoute(MapboxMap map, WalkRoute? route) async {
  if (route == null) {
    for (final id in [_id, _casingId]) {
      if (await map.styleLayerExists(id)) await map.removeStyleLayer(id);
    }
    if (await map.styleSourceExists(_id)) await map.removeStyleSource(_id);
    return;
  }
  if (!await map.styleSourceExists(_id)) {
    await map.addStyleSource(_id, jsonEncode({'type': 'geojson', 'data': ''}));
  }
  // Under the report pins, so a line over a pothole never hides it. Pins come first on a normal start:
  // before they exist (the first load), the line goes on top and the pins are added above it.
  final below = await map.styleLayerExists('reports') ? LayerPosition(below: 'reports') : null;
  if (!await map.styleLayerExists(_casingId)) {
    await map.addStyleLayer(
      jsonEncode(_line(_casingId, '#ffffff', ['interpolate', ['linear'], ['zoom'], 12, 6, 16, 10, 19, 14])),
      below,
    );
  }
  if (!await map.styleLayerExists(_id)) {
    await map.addStyleLayer(
      jsonEncode(_line(_id, _navy, ['interpolate', ['linear'], ['zoom'], 12, 3, 16, 6, 19, 9])),
      below,
    );
  }
  await map.setStyleSourceProperty(
    _id,
    'data',
    jsonEncode({
      'type': 'Feature',
      'geometry': {'type': 'LineString', 'coordinates': route.line},
      'properties': {'mode': route.mode},
    }),
  );
}
