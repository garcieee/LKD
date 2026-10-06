// The route: a navy line with a white casing, under the report and destination pins. map/map_view.dart draws
// what the user has chosen (state/trip_state.dart): a walking route, or a commute option made of several legs,
// where each walking leg is a thin grey line and each ride the thick navy one.
import 'dart:convert';
import 'dart:ui' show Color;

import 'package:mapbox_maps_flutter/mapbox_maps_flutter.dart';

import '../api/api_client.dart';
import '../theme.dart';

const _id = 'route';
const _casingId = 'route-casing';

String _hex(Color c) => '#${(c.toARGB32() & 0xFFFFFF).toRadixString(16).padLeft(6, '0')}';

String get _navy => _hex(navy);
String get _grey => _hex(muted);

// A commute's walking legs carry thin: true; the walking route and every ride do not.
final _thin = [
  '==',
  ['get', 'thin'],
  true,
];

/// A zoom ramp of widths: [thick] for a ride or a whole walking route, [thin] for a commute's walking legs.
List<Object> _widths(List<List<num>> stops) => [
  'interpolate',
  ['linear'],
  ['zoom'],
  for (final [zoom, thick, thin] in stops) ...[
    zoom,
    ['case', _thin, thin, thick],
  ],
];

Map<String, Object> _line(String id, Object color, List<Object> width) => {
  'id': id,
  'type': 'line',
  'source': _id,
  'layout': {'line-cap': 'round', 'line-join': 'round'},
  'paint': {'line-color': color, 'line-width': width},
};

/// The GeoJSON for a walking route.
Map<String, Object> walkGeoJson(WalkRoute route) => {
  'type': 'Feature',
  'geometry': {'type': 'LineString', 'coordinates': route.line},
  'properties': {'mode': route.mode},
};

/// The GeoJSON for a commute option: one line per leg, in order.
Map<String, Object> commuteGeoJson(CommuteOption option) => {
  'type': 'FeatureCollection',
  'features': [
    for (final leg in option.legs)
      {
        'type': 'Feature',
        'geometry': {'type': 'LineString', 'coordinates': leg.line},
        'properties': {'kind': leg.kind, 'thin': leg.isWalk},
      },
  ],
};

/// Draws [route], or removes the line when it is null.
Future<void> showRoute(MapboxMap map, WalkRoute? route) => _draw(map, route == null ? null : walkGeoJson(route));

/// Draws a commute [option] leg by leg, or removes the line when it is null.
Future<void> showCommute(MapboxMap map, CommuteOption? option) =>
    _draw(map, option == null ? null : commuteGeoJson(option));

/// Draws [geojson], or removes the line when it is null. Adds the source and layers when a style load has
/// cleared them. Raw style-spec JSON, like reports_layer.dart.
Future<void> _draw(MapboxMap map, Map<String, Object>? geojson) async {
  if (geojson == null) {
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
      jsonEncode(
        _line(
          _casingId,
          '#ffffff',
          _widths([
            [12, 6, 4],
            [16, 10, 6],
            [19, 14, 9],
          ]),
        ),
      ),
      below,
    );
  }
  if (!await map.styleLayerExists(_id)) {
    final color = ['case', _thin, _grey, _navy];
    await map.addStyleLayer(
      jsonEncode(
        _line(
          _id,
          color,
          _widths([
            [12, 3, 2],
            [16, 6, 3],
            [19, 9, 5],
          ]),
        ),
      ),
      below,
    );
  }
  await map.setStyleSourceProperty(_id, 'data', jsonEncode(geojson));
}
