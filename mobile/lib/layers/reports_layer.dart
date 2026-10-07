// Report pins: a teardrop per active report, coloured by status, with its tip at the location.
// map/map_view.dart fetches and redraws them; tapping one opens its card (map/pin_chip.dart).
import 'dart:convert';
import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:flutter/painting.dart' show Color;
import 'package:mapbox_maps_flutter/mapbox_maps_flutter.dart';

import '../api/api_client.dart';
import '../theme.dart';

const reportsRefresh = Duration(seconds: 60);

/// Pin colour per status (the dashboard's purple priority, warn and navy). Fixed reports are not drawn.
const statusColors = {'open': Color(0xFF70449A), 'verified': warn, 'assigned': navy};

const _id = 'reports';

final _images = <String, Uint8List>{};

Future<Uint8List> _pin(Color color) async {
  final recorder = ui.PictureRecorder();
  final canvas = ui.Canvas(recorder)..scale(3);
  ui.Path shape(double radius, double tip) => ui.Path.combine(
    ui.PathOperation.union,
    ui.Path()..addOval(ui.Rect.fromCircle(center: const ui.Offset(16, 15), radius: radius)),
    ui.Path()
      ..moveTo(16 - radius * 0.85, 20)
      ..lineTo(16, tip)
      ..lineTo(16 + radius * 0.85, 20)
      ..close(),
  );
  canvas.drawPath(shape(14, 42), ui.Paint()..color = const Color(0xFFFFFFFF));
  canvas.drawPath(shape(12, 38), ui.Paint()..color = color);
  canvas.drawCircle(const ui.Offset(16, 15), 4, ui.Paint()..color = const Color(0xFFFFFFFF));
  final picture = recorder.endRecording();
  final image = await picture.toImage(96, 126);
  final bytes = (await image.toByteData(format: ui.ImageByteFormat.png))!.buffer.asUint8List();
  image.dispose();
  picture.dispose();
  return bytes;
}

final _layer = {
  'id': _id,
  'type': 'symbol',
  'source': _id,
  'layout': {
    'icon-image': [
      'match', ['get', 'status'],
      for (final status in statusColors.keys) ...[status, 'ticket-pin-$status'],
      'ticket-pin-open',
    ],
    'icon-anchor': 'bottom',
    'icon-size': ['interpolate', ['linear'], ['zoom'], 12, 0.65, 16, 0.9, 19, 1.1],
    'icon-allow-overlap': true,
    'icon-ignore-placement': true,
    'icon-pitch-alignment': 'viewport',
  },
};

/// Draws [reports]. Adds the source, and the layer on top of all others, when a style load has
/// cleared them. Raw style-spec JSON, like congestion_layer.dart.
Future<void> showReports(MapboxMap map, List<Report> reports) async {
  for (final entry in statusColors.entries) {
    final id = 'ticket-pin-${entry.key}';
    if (!await map.hasStyleImage(id)) {
      final bytes = _images[id] ??= await _pin(entry.value);
      await map.addImage(id, 3, StyleImage.bytes(bytes));
    }
  }
  // Data goes in after the add, as the typed GeoJsonSource.addToStyle does in 3.0.0.
  if (!await map.styleSourceExists(_id)) {
    await map.addStyleSource(_id, jsonEncode({'type': 'geojson', 'data': ''}));
  }
  if (!await map.styleLayerExists(_id)) await map.addStyleLayer(jsonEncode(_layer), null); // null: on top
  await map.setStyleSourceProperty(
    _id,
    'data',
    jsonEncode({
      'type': 'FeatureCollection',
      'features': [
        for (final r in reports)
          if (r.status != 'fixed' && r.status != 'rejected')
            {
              'type': 'Feature',
              'geometry': {
                'type': 'Point',
                'coordinates': [r.lng, r.lat],
              },
              'properties': {'id': r.id, 'status': r.status},
            },
      ],
    }),
  );
}

/// Calls [onTap] with the id of a tapped pin. Once per map: interactions outlive style loads.
void onReportTap(MapboxMap map, void Function(String id) onTap) {
  map.addInteraction(
    TapInteraction(
      FeaturesetDescriptor(layerId: _id),
      (feature, _) {
        if (feature.properties['id'] case final String id) onTap(id);
      },
      radius: 12, // extra pixels around the finger, so a small dot is easy to hit
    ),
    interactionID: _id,
  );
}
