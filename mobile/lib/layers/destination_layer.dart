// The two ends of the trip: a red "To" pin on the destination and a green "From" pin where the route starts,
// above every other layer. map/map_view.dart draws them when the user picks a place (state/trip_state.dart).
import 'dart:convert';
import 'dart:math' as math;
import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:flutter/material.dart' show Color, FontWeight, TextPainter, TextSpan, TextStyle;
import 'package:mapbox_maps_flutter/mapbox_maps_flutter.dart';

import '../api/api_client.dart';

const _id = 'destination';

const _to = Color(0xFFD9453D);
const _from = Color(0xFF2E9E5B);

// A teardrop with a white edge and a word in the bulb, as a PNG. 96 x 120 px drawn at scale 3 = 32 x 40 logical.
Future<Uint8List> _pin(String word, Color color) async {
  const w = 96.0, h = 120.0, r = 42.0, cx = w / 2, cy = 46.0, spread = 35 * math.pi / 180;
  final rec = ui.PictureRecorder();
  final canvas = ui.Canvas(rec);
  final drop = ui.Path.combine(
    ui.PathOperation.union,
    ui.Path()..addOval(ui.Rect.fromCircle(center: const ui.Offset(cx, cy), radius: r)),
    ui.Path()
      ..moveTo(cx - r * math.sin(spread), cy + r * math.cos(spread))
      ..lineTo(cx, h - 4)
      ..lineTo(cx + r * math.sin(spread), cy + r * math.cos(spread))
      ..close(),
  );
  canvas.drawPath(
    drop,
    ui.Paint()
      ..style = ui.PaintingStyle.stroke
      ..strokeWidth = 8
      ..strokeJoin = ui.StrokeJoin.round
      ..color = const Color(0xFFFFFFFF),
  );
  canvas.drawPath(drop, ui.Paint()..color = color);
  final text = TextPainter(
    text: TextSpan(
      text: word,
      style: const TextStyle(fontSize: 27, fontWeight: FontWeight.w700, color: Color(0xFFFFFFFF)),
    ),
    textDirection: ui.TextDirection.ltr,
  )..layout();
  text.paint(canvas, ui.Offset(cx - text.width / 2, cy - text.height / 2));
  final img = await rec.endRecording().toImage(w.toInt(), h.toInt());
  return (await img.toByteData(format: ui.ImageByteFormat.png))!.buffer.asUint8List();
}

final _layer = {
  'id': _id,
  'type': 'symbol',
  'source': _id,
  'layout': {
    'icon-image': ['get', 'icon'],
    'icon-anchor': 'bottom', // the tip of the drop is the place
    'icon-size': [
      'interpolate',
      ['linear'],
      ['zoom'],
      12,
      0.7,
      16,
      1.0,
      19,
      1.25,
    ],
    'icon-allow-overlap': true,
    'symbol-sort-key': [
      'case',
      [
        '==',
        ['get', 'icon'],
        'pin-to',
      ],
      2,
      1,
    ], // "To" over "From" when they meet
  },
};

/// Draws [place] as the "To" pin, and, when [start] ([lng, lat]) is known, the "From" pin there. Removes both
/// when [place] is null. Adds the source and layer when a style load has cleared them. Raw style-spec JSON,
/// like reports_layer.dart.
Future<void> showDestination(MapboxMap map, Place? place, {List<double>? start}) async {
  if (place == null) {
    if (await map.styleLayerExists(_id)) await map.removeStyleLayer(_id);
    if (await map.styleSourceExists(_id)) await map.removeStyleSource(_id);
    return;
  }
  for (final (name, word, color) in [('pin-to', 'To', _to), ('pin-from', 'From', _from)]) {
    if (!await map.hasStyleImage(name)) await map.addImage(name, 3, StyleImage.bytes(await _pin(word, color)));
  }
  if (!await map.styleSourceExists(_id)) {
    await map.addStyleSource(_id, jsonEncode({'type': 'geojson', 'data': ''}));
  }
  if (!await map.styleLayerExists(_id)) await map.addStyleLayer(jsonEncode(_layer), null); // null: on top
  Map<String, Object> pin(String icon, List<double> at) => {
    'type': 'Feature',
    'geometry': {'type': 'Point', 'coordinates': at},
    'properties': {'icon': icon},
  };
  await map.setStyleSourceProperty(
    _id,
    'data',
    jsonEncode({
      'type': 'FeatureCollection',
      'features': [
        if (start != null) pin('pin-from', start),
        pin('pin-to', [place.lng, place.lat]),
      ],
    }),
  );
}
