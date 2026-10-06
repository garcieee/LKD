// Transit hubs, one blue badge each; the glyph says what serves it: a train for MRT-3 / LRT-1 stations,
// a bus, a van for jeepney and UV Express, or "commute" where several kinds meet. Size says what it is:
// stations (largest, always named), PUV terminals, bus stops (small). Names show at close zoom.
// map/map_view.dart loads them once and draws them; a tap opens the hub card (features/transfer_walk/hub_picker.dart).
import 'dart:convert';
import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:flutter/material.dart' show Colors, IconData, Icons, TextPainter, TextSpan, TextStyle;
import 'package:mapbox_maps_flutter/mapbox_maps_flutter.dart';

import '../api/api_client.dart';

const _id = 'hubs';
const _labelId = 'hubs-label';
const _stationLabelId = 'hubs-station-label';

const hubBlue = ui.Color(0xFF1D6FD8); // every hub, whatever serves it

/// Glyph per icon key (see [hubIconKey]) and its legend label. The key is also the image id suffix.
const hubIcons = {
  'train': (icon: Icons.train, label: 'Train station'),
  'bus': (icon: Icons.directions_bus, label: 'Bus'),
  'jeepney': (icon: Icons.airport_shuttle, label: 'Jeepney / UV Express'), // Material has no jeepney
  'mixed': (icon: Icons.commute, label: 'Several kinds'),
};

const _iconOfMode = {
  'mrt3': 'train',
  'lrt1': 'train',
  'city_bus': 'bus',
  'p2p_bus': 'bus',
  'jeepney': 'jeepney',
  'uv_express': 'jeepney',
};

/// Which glyph a hub wears: a station is a train; any other hub takes the glyph of what serves it, or
/// "mixed" when its kinds of service have different glyphs.
String hubIconKey(Hub h) {
  if (h.isStation) return 'train';
  final keys = {for (final m in h.modes) _iconOfMode[m] ?? 'mixed'};
  return keys.length == 1 ? keys.single : 'mixed';
}

/// The key for the hubs on the map: only the glyphs that are there, in a fixed order.
List<({IconData icon, String label})> hubLegend(List<Hub> hubs) {
  final present = {for (final h in hubs) hubIconKey(h)};
  return [
    for (final MapEntry(:key, :value) in hubIcons.entries)
      if (present.contains(key)) value,
  ];
}

Object _byKind(Object station, Object terminal, Object stop) => [
  'case',
  ['==', ['get', 'kind'], 'station'],
  station,
  ['==', ['get', 'kind'], 'terminal'],
  terminal,
  stop,
];

// A blue rounded square with a white glyph, as a PNG. 96 px drawn at scale 3 = 32 logical px.
Future<Uint8List> _badge(IconData icon) async {
  const size = 96.0;
  final rec = ui.PictureRecorder();
  final canvas = ui.Canvas(rec);
  canvas.drawRRect(
    ui.RRect.fromRectAndRadius(const ui.Rect.fromLTWH(0, 0, size, size), const ui.Radius.circular(22)),
    ui.Paint()..color = hubBlue,
  );
  final glyph = TextPainter(
    text: TextSpan(
      text: String.fromCharCode(icon.codePoint),
      style: TextStyle(fontFamily: icon.fontFamily, package: icon.fontPackage, fontSize: 64, color: Colors.white),
    ),
    textDirection: ui.TextDirection.ltr,
  )..layout();
  glyph.paint(canvas, ui.Offset((size - glyph.width) / 2, (size - glyph.height) / 2));
  final img = await rec.endRecording().toImage(size.toInt(), size.toInt());
  return (await img.toByteData(format: ui.ImageByteFormat.png))!.buffer.asUint8List();
}

final _layer = {
  'id': _id,
  'type': 'symbol',
  'source': _id,
  'layout': {
    'icon-image': ['concat', 'hub-', ['get', 'icon']],
    'icon-size': [
      'interpolate', ['linear'], ['zoom'],
      12, _byKind(0.6, 0.5, 0.35),
      16, _byKind(1.0, 0.8, 0.6),
      19, _byKind(1.2, 1.0, 0.75),
    ],
    'icon-allow-overlap': true, // a hub never hides because another is near
    'symbol-sort-key': _byKind(3, 2, 1), // stations on top
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
  'paint': {'text-color': '#1D6FD8', 'text-halo-color': '#ffffff', 'text-halo-width': 1.5},
};

/// Draws [hubs]. Adds the source and layers when a style load has cleared them, under the report pins
/// so a pothole is never hidden by a terminal or a station.
Future<void> showHubs(MapboxMap map, List<Hub> hubs) async {
  for (final MapEntry(:key, :value) in hubIcons.entries) {
    if (!await map.hasStyleImage('hub-$key')) {
      await map.addImage('hub-$key', 3, StyleImage.bytes(await _badge(value.icon)));
    }
  }
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
            'properties': {'id': h.id, 'name': h.name, 'kind': h.kind, 'icon': hubIconKey(h)},
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
