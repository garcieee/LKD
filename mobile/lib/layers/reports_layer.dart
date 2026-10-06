// Report pins: a dot per report that is not fixed, coloured by status, drawn above every other layer.
// map/map_view.dart fetches and redraws them; tapping one opens its card (map/pin_chip.dart).
import 'dart:convert';

import 'package:flutter/painting.dart' show Color;
import 'package:mapbox_maps_flutter/mapbox_maps_flutter.dart';

import '../api/api_client.dart';
import '../theme.dart';

const reportsRefresh = Duration(seconds: 60);

/// Pin colour per status (the dashboard's danger, warn and navy). Fixed reports are not drawn.
const statusColors = {'open': Color(0xFFA63722), 'verified': warn, 'assigned': navy};

const _id = 'reports';

String _hex(Color c) => '#${(c.toARGB32() & 0xFFFFFF).toRadixString(16).padLeft(6, '0')}';

final _layer = {
  'id': _id,
  'type': 'circle',
  'source': _id,
  'paint': {
    'circle-color': [
      'match',
      ['get', 'status'],
      for (final MapEntry(:key, :value) in statusColors.entries) ...[key, _hex(value)],
      _hex(statusColors['open']!),
    ],
    // A dot at city scale, an easy target up close.
    'circle-radius': ['interpolate', ['linear'], ['zoom'], 12, 5, 16, 8, 19, 11],
    'circle-stroke-width': 2,
    'circle-stroke-color': '#ffffff',
  },
};

/// Draws [reports]. Adds the source, and the layer on top of all others, when a style load has
/// cleared them. Raw style-spec JSON, like congestion_layer.dart.
Future<void> showReports(MapboxMap map, List<Report> reports) async {
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
          if (r.status != 'fixed')
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
