import 'package:flutter/material.dart' show Icons;
import 'package:flutter_test/flutter_test.dart';
import 'package:lakad/api/api_client.dart';
import 'package:lakad/layers/hubs_layer.dart';

Hub hub(String kind, List<String> modes) => Hub.fromJson({
  'id': '$kind-${modes.join()}',
  'name': 'x',
  'kind': kind,
  'modes': modes,
  'lat': 14.55,
  'lng': 121.02,
  'error_m': 60,
});

void main() {
  group('hubIconKey', () {
    test('a station is a train, whatever else stops there', () {
      expect(hubIconKey(hub('station', ['mrt3'])), 'train');
      expect(hubIconKey(hub('station', ['lrt1', 'jeepney', 'p2p_bus'])), 'train');
    });

    test('a terminal or stop takes the glyph of what serves it', () {
      expect(hubIconKey(hub('stop', ['city_bus'])), 'bus');
      expect(hubIconKey(hub('terminal', ['p2p_bus'])), 'bus');
      expect(hubIconKey(hub('terminal', ['jeepney'])), 'jeepney');
      expect(hubIconKey(hub('terminal', ['uv_express'])), 'jeepney');
    });

    test('kinds that share a glyph stay single; different glyphs are mixed', () {
      expect(hubIconKey(hub('terminal', ['jeepney', 'uv_express'])), 'jeepney');
      expect(hubIconKey(hub('terminal', ['city_bus', 'p2p_bus'])), 'bus');
      expect(hubIconKey(hub('terminal', ['jeepney', 'city_bus'])), 'mixed');
    });

    test('every mode and every key has a glyph', () {
      for (final m in hubModeLabels.keys) {
        expect(hubIcons, contains(hubIconKey(hub('terminal', [m]))));
      }
      expect(hubIcons['mixed']!.icon, Icons.commute);
    });
  });

  group('hubLegend', () {
    test('lists only the glyphs on the map, in the fixed order', () {
      final legend = hubLegend([
        hub('stop', ['city_bus']),
        hub('terminal', ['jeepney']),
        hub('terminal', ['jeepney', 'city_bus']),
        hub('station', ['mrt3', 'city_bus']),
      ]);
      expect(legend.map((e) => e.label), ['Train station', 'Bus', 'Jeepney / UV Express', 'Several kinds']);
    });

    test('no hubs, no key', () {
      expect(hubLegend(const []), isEmpty);
    });
  });
}
