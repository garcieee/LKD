// The destination pin: one big green dot with a white ring, above every other layer.
// map/map_view.dart draws it when the user picks a place (state/trip_state.dart).
import 'dart:convert';

import 'package:mapbox_maps_flutter/mapbox_maps_flutter.dart';

import '../api/api_client.dart';

const _id = 'destination';

// The dashboard's --ok green. Fixed reports are not drawn, so no report pin shares it.
final _layer = {
  'id': _id,
  'type': 'circle',
  'source': _id,
  'paint': {
    'circle-color': '#41755e',
    'circle-radius': ['interpolate', ['linear'], ['zoom'], 12, 8, 16, 11, 19, 14],
    'circle-stroke-width': 3,
    'circle-stroke-color': '#ffffff',
  },
};

/// Draws [place], or removes the pin when it is null. Adds the source and layer when a style load
/// has cleared them. Raw style-spec JSON, like reports_layer.dart.
Future<void> showDestination(MapboxMap map, Place? place) async {
  if (place == null) {
    if (await map.styleLayerExists(_id)) await map.removeStyleLayer(_id);
    if (await map.styleSourceExists(_id)) await map.removeStyleSource(_id);
    return;
  }
  if (!await map.styleSourceExists(_id)) {
    await map.addStyleSource(_id, jsonEncode({'type': 'geojson', 'data': ''}));
  }
  if (!await map.styleLayerExists(_id)) await map.addStyleLayer(jsonEncode(_layer), null); // null: on top
  await map.setStyleSourceProperty(
    _id,
    'data',
    jsonEncode({
      'type': 'Feature',
      'geometry': {
        'type': 'Point',
        'coordinates': [place.lng, place.lat],
      },
      'properties': {'label': place.label},
    }),
  );
}
