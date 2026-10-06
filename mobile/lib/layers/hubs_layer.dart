// Transit hubs: a purple dot per terminal (large) and bus stop (small), with the name at close zoom.
// map/map_view.dart loads them once and draws them; a tap opens the hub card (features/transfer_walk/hub_picker.dart).
import 'dart:convert';

import 'package:mapbox_maps_flutter/mapbox_maps_flutter.dart';

import '../api/api_client.dart';

const _id = 'hubs';
const _labelId = 'hubs-label';

const terminalColor = '#6c4e8a';
const stopColor = '#a493bd';

Object _byKind(Object terminal, Object stop) => [
  'case',
  ['==', ['get', 'kind'], 'terminal'],
  terminal,
  stop,
];

final _layer = {
  'id': _id,
  'type': 'circle',
  'source': _id,
  'paint': {
    'circle-color': _byKind(terminalColor, stopColor),
    'circle-radius': [
      'interpolate', ['linear'], ['zoom'],
      12, _byKind(4, 2.5),
      16, _byKind(8, 5),
      19, _byKind(11, 7),
    ],
    'circle-stroke-width': 2,
    'circle-stroke-color': '#ffffff',
  },
};

// Names appear once the map is close enough to read them. Stops are named too: there are only 15.
final _labels = {
  'id': _labelId,
  'type': 'symbol',
  'source': _id,
  'minzoom': 15,
  'layout': {
    'text-field': ['get', 'name'],
    'text-size': 11,
    'text-offset': [0, 1.1],
    'text-anchor': 'top',
    'text-optional': true,
  },
  'paint': {'text-color': '#3f2d57', 'text-halo-color': '#ffffff', 'text-halo-width': 1.5},
};

/// Draws [hubs]. Adds the source and layers when a style load has cleared them, under the report pins
/// so a pothole is never hidden by a terminal.
Future<void> showHubs(MapboxMap map, List<Hub> hubs) async {
  if (!await map.styleSourceExists(_id)) {
    await map.addStyleSource(_id, jsonEncode({'type': 'geojson', 'data': ''}));
  }
  final below = await map.styleLayerExists('reports') ? LayerPosition(below: 'reports') : null;
  if (!await map.styleLayerExists(_id)) await map.addStyleLayer(jsonEncode(_layer), below);
  if (!await map.styleLayerExists(_labelId)) await map.addStyleLayer(jsonEncode(_labels), below);
  await map.setStyleSourceProperty(
    _id,
    'data',
    jsonEncode({
      'type': 'FeatureCollection',
      'features': [
        for (final h in hubs)
          {
            'type': 'Feature',
            'geometry': {
              'type': 'Point',
              'coordinates': [h.lng, h.lat],
            },
            'properties': {'id': h.id, 'name': h.name, 'kind': h.isTerminal ? 'terminal' : 'stop'},
          },
      ],
    }),
  );
}

/// Removes the hubs from the map (the layer switch is off).
Future<void> hideHubs(MapboxMap map) async {
  for (final id in [_labelId, _id]) {
    if (await map.styleLayerExists(id)) await map.removeStyleLayer(id);
  }
  if (await map.styleSourceExists(_id)) await map.removeStyleSource(_id);
}

/// Calls [onTap] with the id of a tapped hub. Once per map: interactions outlive style loads.
void onHubTap(MapboxMap map, void Function(String id) onTap) {
  map.addInteraction(
    TapInteraction(
      FeaturesetDescriptor(layerId: _id),
      (feature, _) {
        if (feature.properties['id'] case final String id) onTap(id);
      },
      radius: 14, // extra pixels around the finger, so a small dot is easy to hit
    ),
    interactionID: _id,
  );
}
