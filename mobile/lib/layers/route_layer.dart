// The route: a thick blue line with a white casing and white arrowheads pointing the way, under the report and
// destination pins. map/map_view.dart draws what the user has chosen (state/trip_state.dart): a walking route, or
// a commute option made of several legs, where each walking leg is a thinner blue line and each ride the navy one.
import 'dart:convert';
import 'dart:ui' show Color;

import 'package:flutter/services.dart' show rootBundle;
import 'package:mapbox_maps_flutter/mapbox_maps_flutter.dart';

import '../api/api_client.dart';
import '../state/trip_progress.dart';
import '../theme.dart';

const _id = 'route';
const _casingId = 'route-casing';
const _chevronId = 'route-chevrons';
const _chevronImage = 'route-chevron';

String _hex(Color c) => '#${(c.toARGB32() & 0xFFFFFF).toRadixString(16).padLeft(6, '0')}';

String get _navy => _hex(navy);
String get _blue => _hex(routeBlue);

// A commute's walking legs carry thin: true; the walking route and every ride do not. A ride carries a kind.
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

// White arrowheads along the line, turned the way the route goes (the line runs from the user to the destination).
final _chevrons = {
  'id': _chevronId,
  'type': 'symbol',
  'source': _id,
  'layout': {
    'symbol-placement': 'line',
    'symbol-spacing': 38,
    'icon-image': _chevronImage,
    'icon-size': [
      'interpolate',
      ['linear'],
      ['zoom'],
      12,
      ['case', _thin, 0.28, 0.35],
      16,
      ['case', _thin, 0.5, 0.65],
      19,
      ['case', _thin, 0.75, 1.0],
    ],
    'icon-allow-overlap': true,
    'icon-ignore-placement': true,
  },
};

/// The GeoJSON for a walking route.
Map<String, Object> walkGeoJson(WalkRoute route) => {
  'type': 'Feature',
  'geometry': {'type': 'LineString', 'coordinates': route.line},
  'properties': {'mode': route.mode},
};

Map<String, Object> _feature(CommuteLeg leg, List<List<double>> line, {required bool thin}) => {
  'type': 'Feature',
  'geometry': {'type': 'LineString', 'coordinates': line},
  'properties': {'kind': leg.kind, 'thin': thin},
};

/// The GeoJSON for a commute option: one line per leg, in order.
Map<String, Object> commuteGeoJson(CommuteOption option) => {
  'type': 'FeatureCollection',
  'features': [for (final leg in option.legs) _feature(leg, leg.line, thin: leg.isWalk)],
};

/// The GeoJSON for a trip being travelled: what is left of it. The leg the user is on starts at their spot on it
/// ([TripProgress.ahead]), the legs before it are gone, the legs after it are whole. A walk-only trip is one thick
/// line, like the planned route; with a ride in it the walking legs are the thin ones. [legs] is not empty.
Map<String, Object> tripGeoJson(List<CommuteLeg> legs, TripProgress? progress) {
  final from = progress == null ? 0 : progress.leg.clamp(0, legs.length - 1);
  return {
    'type': 'FeatureCollection',
    'features': [
      for (var i = from; i < legs.length; i++)
        _feature(
          legs[i],
          i == from && progress != null ? progress.ahead : legs[i].line,
          thin: legs[i].isWalk && legs.length > 1,
        ),
    ],
  };
}

/// Draws [route], or removes the line when it is null.
Future<void> showRoute(MapboxMap map, WalkRoute? route) => _draw(map, route == null ? null : walkGeoJson(route));

/// Draws a commute [option] leg by leg, or removes the line when it is null.
Future<void> showCommute(MapboxMap map, CommuteOption? option) =>
    _draw(map, option == null ? null : commuteGeoJson(option));

/// Draws what is left of the trip being travelled, or removes the line when there are no [legs].
Future<void> showTrip(MapboxMap map, List<CommuteLeg> legs, TripProgress? progress) =>
    _draw(map, legs.isEmpty ? null : tripGeoJson(legs, progress));

/// Draws [geojson], or removes the line when it is null. Adds the source and layers when a style load has
/// cleared them. Raw style-spec JSON, like reports_layer.dart.
Future<void> _draw(MapboxMap map, Map<String, Object>? geojson) async {
  if (geojson == null) {
    for (final id in [_chevronId, _id, _casingId]) {
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
            [12, 8, 6],
            [16, 15, 10],
            [19, 22, 15],
          ]),
        ),
      ),
      below,
    );
  }
  if (!await map.styleLayerExists(_id)) {
    // A ride (it has a kind) is navy; a walk, the whole route or a leg of a commute, is blue.
    final color = [
      'case',
      _thin,
      _blue,
      ['has', 'kind'],
      _navy,
      _blue,
    ];
    await map.addStyleLayer(
      jsonEncode(
        _line(
          _id,
          color,
          _widths([
            [12, 5, 4],
            [16, 10, 7],
            [19, 16, 11],
          ]),
        ),
      ),
      below,
    );
  }
  if (!await map.styleLayerExists(_chevronId)) {
    if (!await map.hasStyleImage(_chevronImage)) {
      final bytes = (await rootBundle.load('assets/route_chevron.png')).buffer.asUint8List();
      await map.addImage(_chevronImage, 3, StyleImage.bytes(bytes));
    }
    await map.addStyleLayer(jsonEncode(_chevrons), below);
  }
  await map.setStyleSourceProperty(_id, 'data', jsonEncode(geojson));
}
