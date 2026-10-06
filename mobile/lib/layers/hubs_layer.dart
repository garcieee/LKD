// Transit hubs, one dot each, coloured by what serves them: PUV terminals (large) and bus stops (small), and
// MRT-3 / LRT-1 stations (largest, dark ring, always named). Names show at close zoom.
// map/map_view.dart loads them once and draws them; a tap opens the hub card (features/transfer_walk/hub_picker.dart).
import 'dart:convert';

import 'package:flutter/painting.dart' show Color;
import 'package:mapbox_maps_flutter/mapbox_maps_flutter.dart';

import '../api/api_client.dart';

const _id = 'hubs';
const _labelId = 'hubs-label';
const _stationLabelId = 'hubs-station-label';

/// The colour of each kind of PUV, in the study's own order. A hub served by one kind takes its colour; a
/// station takes its line's colour; a hub served by several kinds is [hubMixedColor].
const hubModeColors = {
  'jeepney': Color(0xFFE8590C), // orange, as on the study's jeepney map
  'uv_express': Color(0xFF0E9AB7), // teal
  'city_bus': Color(0xFFD99A00), // gold
  'p2p_bus': Color(0xFFC2185B), // magenta
  'mrt3': Color(0xFF1565C0), // blue
  'lrt1': Color(0xFF388E3C), // green
};
const hubMixedColor = Color(0xFF6C4E8A); // purple

Color hubColor(Hub h) {
  final single = h.isStation || h.modes.length == 1;
  return (single ? hubModeColors[h.modes.first] : null) ?? hubMixedColor;
}

/// The colour key for the hubs on the map: only what is there, in a fixed order.
List<({Color color, String label})> hubLegend(List<Hub> hubs) {
  final single = {for (final h in hubs) if (!h.isStation && h.modes.length == 1) h.modes.first};
  final lines = {for (final h in hubs) if (h.isStation) h.modes.first};
  return [
    for (final m in hubModeColors.keys)
      if (single.contains(m) || lines.contains(m)) (color: hubModeColors[m]!, label: hubModeLabels[m] ?? m),
    if (hubs.any((h) => !h.isStation && h.modes.length > 1)) (color: hubMixedColor, label: 'Several kinds'),
  ];
}

String _hex(Color c) => '#${(c.toARGB32() & 0xFFFFFF).toRadixString(16).padLeft(6, '0')}';

Object _byKind(Object station, Object terminal, Object stop) => [
  'case',
  ['==', ['get', 'kind'], 'station'],
  station,
  ['==', ['get', 'kind'], 'terminal'],
  terminal,
  stop,
];

final _layer = {
  'id': _id,
  'type': 'circle',
  'source': _id,
  'paint': {
    'circle-color': ['get', 'color'],
    'circle-radius': [
      'interpolate', ['linear'], ['zoom'],
      12, _byKind(6, 4, 2.5),
      16, _byKind(11, 8, 5),
      19, _byKind(14, 11, 7),
    ],
    'circle-stroke-width': _byKind(3, 2, 2),
    'circle-stroke-color': _byKind('#262626', '#ffffff', '#ffffff'),
  },
};

// Stations are named from a wide view: there are only 11, and they are what people look for first.
final _stationLabels = {
  'id': _stationLabelId,
  'type': 'symbol',
  'source': _id,
  'minzoom': 12.5,
  'filter': ['==', ['get', 'kind'], 'station'],
  'layout': {
    'text-field': ['get', 'name'],
    'text-size': 12,
    'text-offset': [0, 1.3],
    'text-anchor': 'top',
    'text-optional': true,
  },
  'paint': {'text-color': '#262626', 'text-halo-color': '#ffffff', 'text-halo-width': 1.8},
};

// Terminal and stop names appear once the map is close enough to read them.
final _labels = {
  'id': _labelId,
  'type': 'symbol',
  'source': _id,
  'minzoom': 15,
  'filter': ['!=', ['get', 'kind'], 'station'],
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
/// so a pothole is never hidden by a terminal or a station.
Future<void> showHubs(MapboxMap map, List<Hub> hubs) async {
  if (!await map.styleSourceExists(_id)) {
    await map.addStyleSource(_id, jsonEncode({'type': 'geojson', 'data': ''}));
  }
  final below = await map.styleLayerExists('reports') ? LayerPosition(below: 'reports') : null;
  if (!await map.styleLayerExists(_id)) await map.addStyleLayer(jsonEncode(_layer), below);
  if (!await map.styleLayerExists(_labelId)) await map.addStyleLayer(jsonEncode(_labels), below);
  if (!await map.styleLayerExists(_stationLabelId)) await map.addStyleLayer(jsonEncode(_stationLabels), below);
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
            'properties': {'id': h.id, 'name': h.name, 'kind': h.kind, 'color': _hex(hubColor(h))},
          },
      ],
    }),
  );
}

/// Removes the hubs from the map (the layer switch is off).
Future<void> hideHubs(MapboxMap map) async {
  for (final id in [_stationLabelId, _labelId, _id]) {
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
