// Transit hubs: one blue badge per station or terminal, the glyph telling the kind apart
// (train, bus, jeepney / UV, ferry), with the name beside it. map/map_view.dart draws it.
// Positions are OpenStreetMap (Overpass, Oct 2026), kept to Makati. Add one = one line in _hubs.
import 'dart:convert';
import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:flutter/material.dart' show Icons, IconData, Colors, TextPainter, TextSpan, TextStyle;
import 'package:mapbox_maps_flutter/mapbox_maps_flutter.dart';

const hubBlue = ui.Color(0xFF1D6FD8); // every hub, whatever the kind

const _id = 'hubs';

// kind -> glyph. The kind is also the image id suffix (hub-train, ...).
const _icons = {
  'train': Icons.train, // MRT-3, PNR
  'bus': Icons.directions_bus, // EDSA Carousel, P2P and city bus terminals
  'jeepney': Icons.airport_shuttle, // jeepney and UV Express terminals (Material has no jeepney)
  'ferry': Icons.directions_boat, // Pasig River Ferry
};

// (kind, name, lat, lng)
const _hubs = [
  ('train', 'Magallanes MRT-3', 14.54194, 121.01939),
  ('train', 'Ayala MRT-3', 14.54919, 121.02792),
  ('train', 'Buendia MRT-3', 14.55437, 121.03422),
  ('train', 'Guadalupe MRT-3', 14.56711, 121.04554),
  ('train', 'EDSA PNR', 14.54125, 121.01675),
  ('train', 'Pasay Road PNR', 14.54987, 121.01219),
  ('train', 'Dela Rosa PNR', 14.55623, 121.00867),
  ('bus', 'Ayala Carousel', 14.55029, 121.02816),
  ('bus', 'Buendia Carousel', 14.55506, 121.0351),
  ('bus', 'Guadalupe Carousel', 14.56824, 121.04591),
  ('bus', 'BGC - Ayala Terminal', 14.54926, 121.02925),
  ('bus', 'Circuit Makati Terminal', 14.57528, 121.0172),
  ('jeepney', 'UV Express Terminal', 14.54937, 121.02555),
  ('jeepney', 'EDSA-Jupiter Jeepney', 14.55582, 121.03526),
  ('jeepney', 'PRC-Libertad Jeepney', 14.57071, 121.01539),
  ('jeepney', 'PRC-Mantrade Jeepney', 14.57395, 121.01614),
  ('jeepney', 'Guadalupe Jeepney', 14.56638, 121.04649),
  ('ferry', 'Guadalupe Ferry', 14.56799, 121.04787),
  ('ferry', 'Valenzuela Ferry', 14.57395, 121.02577),
];

final _layer = {
  'id': _id,
  'type': 'symbol',
  'source': _id,
  'layout': {
    'icon-image': ['concat', 'hub-', ['get', 'kind']],
    'icon-size': ['interpolate', ['linear'], ['zoom'], 12, 0.6, 16, 0.9, 19, 1.1],
    'icon-allow-overlap': true, // a hub never hides because a label is near
    'text-field': ['get', 'name'],
    'text-font': ['DIN Pro Medium', 'Arial Unicode MS Regular'],
    'text-size': 11,
    'text-anchor': 'top',
    'text-offset': [0, 1.2],
    'text-optional': true, // crowded: the badge stays, the name goes
  },
  'paint': {
    'text-color': '#1D6FD8',
    'text-halo-color': '#ffffff',
    'text-halo-width': 1.5,
  },
};

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
      style: TextStyle(
        fontFamily: icon.fontFamily,
        package: icon.fontPackage,
        fontSize: 64,
        color: Colors.white,
      ),
    ),
    textDirection: ui.TextDirection.ltr,
  )..layout();
  glyph.paint(canvas, ui.Offset((size - glyph.width) / 2, (size - glyph.height) / 2));
  final img = await rec.endRecording().toImage(size.toInt(), size.toInt());
  return (await img.toByteData(format: ui.ImageByteFormat.png))!.buffer.asUint8List();
}

/// Draws the hubs: adds the badge images, the source and the layer, each only if a style load
/// has cleared them. Raw style-spec JSON, like reports_layer.dart.
Future<void> showHubs(MapboxMap map) async {
  for (final MapEntry(:key, :value) in _icons.entries) {
    if (!await map.hasStyleImage('hub-$key')) {
      await map.addImage('hub-$key', 3, StyleImage.bytes(await _badge(value)));
    }
  }
  if (!await map.styleSourceExists(_id)) {
    await map.addStyleSource(
      _id,
      jsonEncode({
        'type': 'geojson',
        'data': {
          'type': 'FeatureCollection',
          'features': [
            for (final (kind, name, lat, lng) in _hubs)
              {
                'type': 'Feature',
                'geometry': {
                  'type': 'Point',
                  'coordinates': [lng, lat],
                },
                'properties': {'kind': kind, 'name': name},
              },
          ],
        },
      }),
    );
  }
  if (!await map.styleLayerExists(_id)) await map.addStyleLayer(jsonEncode(_layer), null); // null: on top
}
