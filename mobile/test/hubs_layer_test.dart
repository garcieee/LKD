import 'package:flutter/painting.dart' show Color;
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
  group('hubColor', () {
    test('one kind of PUV takes its own colour', () {
      expect(hubColor(hub('terminal', ['jeepney'])), hubModeColors['jeepney']);
      expect(hubColor(hub('terminal', ['uv_express'])), hubModeColors['uv_express']);
      expect(hubColor(hub('stop', ['city_bus'])), hubModeColors['city_bus']);
      expect(hubColor(hub('terminal', ['p2p_bus'])), hubModeColors['p2p_bus']);
    });

    test('several kinds of PUV share the mixed colour', () {
      expect(hubColor(hub('terminal', ['jeepney', 'uv_express'])), hubMixedColor);
    });

    test('a station takes its line colour even when buses stop there too', () {
      expect(hubColor(hub('station', ['mrt3', 'city_bus'])), hubModeColors['mrt3']);
      expect(hubColor(hub('station', ['lrt1', 'jeepney', 'p2p_bus'])), hubModeColors['lrt1']);
    });

    test('an unknown mode falls back to the mixed colour; every mode has a different colour', () {
      expect(hubColor(hub('terminal', ['ferry'])), hubMixedColor);
      expect({...hubModeColors.values, hubMixedColor}.length, hubModeColors.length + 1);
    });

    test('every mode the server sends has a colour and a label', () {
      expect(hubModeColors.keys.toSet(), hubModeLabels.keys.toSet());
    });
  });

  group('hubLegend', () {
    test('lists only what is on the map, in the fixed order, with the mixed colour last', () {
      final legend = hubLegend([
        hub('stop', ['city_bus']),
        hub('terminal', ['jeepney']),
        hub('terminal', ['jeepney', 'uv_express']),
        hub('station', ['mrt3', 'city_bus']),
      ]);
      expect(legend.map((e) => e.label), ['Jeepney', 'City bus', 'MRT-3', 'Several kinds']);
      expect(legend.first.color, hubModeColors['jeepney']);
    });

    test('a bus stop at a station does not add a City bus entry on its own; no hubs, no key', () {
      expect(hubLegend([hub('station', ['lrt1', 'city_bus'])]).map((e) => e.label), ['LRT-1']);
      expect(hubLegend(const []), isEmpty);
    });

    test('colours are opaque', () {
      expect(hubLegend([hub('terminal', ['jeepney'])]).single.color, isA<Color>().having((c) => c.a, 'alpha', 1.0));
    });
  });
}
