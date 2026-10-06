import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:lakad/api/api_client.dart';

// A report as the server sends it (server/app/db/models.py).
Map<String, dynamic> serverReport({Object? heading = 87.5, String status = 'open'}) => {
  'id': '3f2a',
  'category': 'pothole',
  'severity': 2,
  'lat': 14.5547,
  'lng': 121.0244,
  'heading': heading,
  'note': 'deep, by the jeepney stop',
  'photo_url': '/photos/3f2a.jpg',
  'status': status,
  'created_at': '2026-10-06T07:31:05+00:00',
  'updated_at': '2026-10-06T07:31:05+00:00',
};

ApiClient apiWith(MockClient mock) =>
    ApiClient(client: mock, base: 'http://server', timeout: const Duration(milliseconds: 50));

http.Response jsonResponse(Object body, int status) =>
    http.Response(jsonEncode(body), status, headers: {'content-type': 'application/json'});

// JPEG magic, then 150 KB: three 64 KB pieces for the progress callback.
final photo = Uint8List.fromList([0xFF, 0xD8, 0xFF, 0xE0, ...List.filled(150 * 1024, 0x41)]);

Future<Report> send(ApiClient api) =>
    api.sendReport(photo: photo, category: 'pothole', lat: 14.5547, lng: 121.0244);

Matcher apiError(Object message) =>
    throwsA(isA<ApiException>().having((e) => e.message, 'message', message));

void main() {
  group('Report.fromJson', () {
    test('reads a server report', () {
      final r = Report.fromJson(serverReport());
      expect(r.id, '3f2a');
      expect(r.category, 'pothole');
      expect(r.label, 'Pothole');
      expect(r.lat, 14.5547);
      expect(r.lng, 121.0244);
      expect(r.heading, 87.5);
      expect(r.note, 'deep, by the jeepney stop');
      expect(r.photoUrl, '/photos/3f2a.jpg');
      expect(r.status, 'open');
      expect(r.createdAt, DateTime.utc(2026, 10, 6, 7, 31, 5));
    });

    test('takes a null heading and whole-number coordinates', () {
      final r = Report.fromJson({...serverReport(heading: null), 'lat': 14});
      expect(r.heading, isNull);
      expect(r.lat, 14.0);
    });

    test('keeps a heading of 0 (north) apart from no heading, and reads a missing note as empty', () {
      expect(Report.fromJson(serverReport(heading: 0)).heading, 0.0);
      expect(Report.fromJson({...serverReport(), 'note': null}).note, '');
    });

    test('reads a status it does not know as open, and keeps the known ones', () {
      expect(Report.fromJson(serverReport(status: 'triaged')).status, 'open');
      for (final s in statusLabels.keys) {
        expect(Report.fromJson(serverReport(status: s)).status, s);
      }
    });

    test('labels the server categories, and anything else as Other', () {
      expect(categoryLabels.keys, [
        'pothole',
        'open_manhole',
        'flooded_drain',
        'broken_streetlight',
        'blocked_sidewalk',
        'other',
      ]);
      expect(Report.fromJson({...serverReport(), 'category': 'open_manhole'}).label, 'Open manhole');
      expect(Report.fromJson({...serverReport(), 'category': 'sinkhole'}).label, 'Other');
    });
  });

  group('ApiClient.sendReport', () {
    test('posts the photo and fields as multipart and returns the report', () async {
      late http.BaseRequest sent;
      late List<int> bytes;
      final api = apiWith(
        MockClient.streaming((req, body) async {
          sent = req;
          bytes = await body.toBytes();
          return http.StreamedResponse(Stream.value(utf8.encode(jsonEncode(serverReport()))), 201);
        }),
      );
      final progress = <double>[];
      final report = await api.sendReport(
        photo: photo,
        category: 'pothole',
        lat: 14.5547,
        lng: 121.0244,
        heading: 87.5,
        note: 'deep, by the jeepney stop',
        onProgress: progress.add,
      );

      expect(report.id, '3f2a');
      expect(sent.method, 'POST');
      expect(sent.url.toString(), 'http://server/reports');
      expect(sent.headers['content-type'], startsWith('multipart/form-data; boundary='));
      expect(sent.contentLength, bytes.length); // the Content-Length a real upload declares
      final body = latin1.decode(bytes);
      String field(String name, String value) => 'name="$name"\r\n\r\n$value\r\n';
      expect(body, contains(field('category', 'pothole')));
      expect(body, contains(field('lat', '14.5547')));
      expect(body, contains(field('lng', '121.0244')));
      expect(body, contains(field('heading', '87.5')));
      expect(body, contains(field('note', 'deep, by the jeepney stop')));
      expect(
        body,
        contains('content-type: image/jpeg\r\ncontent-disposition: form-data; name="photo"; filename="report.jpg"'),
      );
      expect(body, contains(latin1.decode(photo))); // every byte, in order
      expect(progress, hasLength(3));
      expect(progress, orderedEquals([...progress]..sort()));
      expect(progress.last, 1.0);
    });

    test('leaves out a missing heading and an empty note', () async {
      late String body;
      final api = apiWith(
        MockClient((req) async {
          body = latin1.decode(req.bodyBytes);
          return jsonResponse(serverReport(heading: null), 201);
        }),
      );
      await api.sendReport(photo: photo, category: 'other', lat: 14.5547, lng: 121.0244);
      expect(body, isNot(contains('name="heading"')));
      expect(body, isNot(contains('name="note"')));
      expect(body, contains('name="category"\r\n\r\nother\r\n'));
    });

    test("shows FastAPI's field errors (422) one per line", () {
      final api = apiWith(
        MockClient(
          (_) async => jsonResponse({
            'detail': [
              {
                'type': 'string_too_long',
                'loc': ['body', 'note'],
                'msg': 'String should have at most 280 characters',
              },
              {
                'type': 'less_than_equal',
                'loc': ['body', 'heading'],
                'msg': 'Input should be less than or equal to 360',
              },
            ],
          }, 422),
        ),
      );
      expect(
        send(api),
        apiError(
          'note: String should have at most 280 characters\n'
          'heading: Input should be less than or equal to 360',
        ),
      );
    });

    test("shows the server's own message (413, 422)", () {
      final tooBig = apiWith(MockClient((_) async => jsonResponse({'detail': 'Photo is larger than 10 MB.'}, 413)));
      expect(send(tooBig), apiError('Photo is larger than 10 MB.'));
      final outside = apiWith(
        MockClient((_) async => jsonResponse({'detail': 'That location is outside the city.'}, 422)),
      );
      expect(send(outside), apiError('That location is outside the city.'));
    });

    test('falls back to the status when the error is not JSON', () {
      final api = apiWith(MockClient((_) async => http.Response('<h1>Bad gateway</h1>', 502)));
      expect(send(api), apiError('Server error 502.'));
      final odd = apiWith(MockClient((_) async => jsonResponse({'error': 'no detail'}, 500)));
      expect(send(odd), apiError('Server error 500.'));
    });

    test('treats a 200 that is not JSON (a Wi-Fi sign-in page) as a failed call', () {
      final api = apiWith(MockClient((_) async => http.Response('<html>Sign in to free Wi-Fi</html>', 200)));
      expect(send(api), apiError(contains("Can't read the answer from http://server")));
      expect(api.reports(), apiError(contains("Can't read the answer from http://server")));
    });

    test('says when the server cannot be reached', () {
      final api = apiWith(MockClient((req) async => throw http.ClientException('Connection refused', req.url)));
      expect(
        send(api),
        apiError(allOf(contains("Can't reach the server at http://server"), contains('Connection refused'))),
      );
    });

    test('gives up when the server does not answer in time', () {
      // MockClient leaves aborting to the handler: wait for the deadline, then abort as IOClient does.
      final api = apiWith(
        MockClient.streaming((req, _) async {
          await (req as http.Abortable).abortTrigger;
          throw http.RequestAbortedException(req.url);
        }),
      );
      expect(send(api), apiError(startsWith('No answer from the server')));
    });
  });

  test('ApiClient.reports reads the list in the order sent (newest first)', () async {
    late http.Request got;
    final api = apiWith(
      MockClient((req) async {
        got = req;
        return jsonResponse([
          serverReport(),
          {...serverReport(status: 'fixed'), 'id': 'older'},
        ], 200);
      }),
    );
    final reports = await api.reports();
    expect(got.method, 'GET');
    expect(got.url.toString(), 'http://server/reports');
    expect(reports.map((r) => r.id), ['3f2a', 'older']);
    expect(reports.last.status, 'fixed');
  });

  group('ApiClient.geocode', () {
    // A place as GET /geocode sends it (server/app/routers/geocode.py).
    Map<String, dynamic> place({String label = 'Ayala Triangle Gardens, Makati, Philippines'}) => {
      'label': label,
      'lat': 14.5547,
      'lng': 121,
    };

    test('asks for the text, reads places in order, takes whole-number coordinates', () async {
      late http.Request got;
      final api = apiWith(
        MockClient((req) async {
          got = req;
          return jsonResponse([place(), place(label: 'Greenbelt, Makati')], 200);
        }),
      );
      final places = await api.geocode('Ayala');
      expect(got.method, 'GET');
      expect(got.url.path, '/geocode');
      expect(got.url.queryParameters, {'q': 'Ayala'}, reason: 'no position sent unless given');
      expect(places.map((p) => p.label), ['Ayala Triangle Gardens, Makati, Philippines', 'Greenbelt, Makati']);
      expect(places.first.lat, 14.5547);
      expect(places.first.lng, 121.0);
    });

    test('sends the position so nearby places rank first, and escapes the text', () async {
      late http.Request got;
      final api = apiWith(
        MockClient((req) async {
          got = req;
          return jsonResponse([], 200);
        }),
      );
      expect(await api.geocode('Jupiter & Makati Ave', near: (lat: 14.55, lng: 121.02)), isEmpty);
      expect(got.url.queryParameters, {'q': 'Jupiter & Makati Ave', 'lat': '14.55', 'lng': '121.02'});
    });

    test("shows the server's message when search is down", () {
      final api = apiWith(
        MockClient((_) async => jsonResponse({'detail': 'Place search is unavailable. Try again.'}, 502)),
      );
      expect(api.geocode('Ayala'), apiError('Place search is unavailable. Try again.'));
    });

    test('the server not being reachable reads as an error, not a crash', () {
      final api = apiWith(MockClient((_) async => throw http.ClientException('no route to host')));
      expect(api.geocode('Ayala'), apiError(contains("Can't reach the server")));
    });
  });

  group('ApiClient.route', () {
    // A route as GET /route/walk sends it (server/app/routers/routes.py).
    Map<String, dynamic> serverRoute({String mode = 'walkable', List<String> hazards = const ['a1']}) => {
      'mode': mode,
      'distance_m': 480,
      'duration_s': 345.2,
      'geometry': [
        [121.0244, 14.5547],
        [121.021, 14.553],
      ],
      'hazard_ids': hazards,
      'avoids_hazards': true,
    };

    const from = (lat: 14.5547, lng: 121.0244), to = (lat: 14.553, lng: 121.021);

    test('asks for the walk in the chosen mode and reads the route', () async {
      late http.Request got;
      final api = apiWith(
        MockClient((req) async {
          got = req;
          return jsonResponse(serverRoute(), 200);
        }),
      );
      final r = await api.route(from: from, to: to, mode: 'walkable');
      expect(got.method, 'GET');
      expect(got.url.path, '/route/walk');
      expect(got.url.queryParameters, {
        'from_lat': '14.5547',
        'from_lng': '121.0244',
        'to_lat': '14.553',
        'to_lng': '121.021',
        'mode': 'walkable',
      });
      expect(r.mode, 'walkable');
      expect(r.distanceM, 480.0, reason: 'a whole number is read as a double');
      expect(r.durationS, 345.2);
      expect(r.line, [
        [121.0244, 14.5547],
        [121.021, 14.553],
      ]);
      expect(r.hazardIds, ['a1']);
      expect(r.avoidsHazards, isTrue);
    });

    test('a route that passes no hazards has an empty list', () async {
      final api = apiWith(MockClient((_) async => jsonResponse(serverRoute(hazards: []), 200)));
      expect((await api.route(from: from, to: to, mode: 'fastest')).hazardIds, isEmpty);
    });

    test("shows the server's message when there is no route", () {
      final api = apiWith(
        MockClient((_) async => jsonResponse({'detail': 'No walking route found between those points.'}, 404)),
      );
      expect(api.route(from: from, to: to, mode: 'fastest'), apiError('No walking route found between those points.'));
    });

    test('the modes are the three the server takes, in toggle order', () {
      expect(routeModes.keys, ['fastest', 'walkable', 'accessible']);
    });
  });

  group('ApiClient.hubs', () {
    // A hub as GET /transit/hubs sends it (server/app/routers/transit.py).
    Map<String, dynamic> serverHub({String name = 'Washington Terminal', String kind = 'terminal'}) => {
      'id': 'washington-terminal',
      'name': name,
      'kind': kind,
      'modes': ['jeepney', 'uv_express'],
      'lat': 14.55856,
      'lng': 121,
      'error_m': 80,
      'distance_m': null,
    };

    test('asks for the list and reads each hub', () async {
      late http.Request got;
      final api = apiWith(
        MockClient((req) async {
          got = req;
          return jsonResponse([serverHub(), serverHub(name: 'Dian', kind: 'stop')], 200);
        }),
      );
      final hubs = await api.hubs();
      expect(got.url.path, '/transit/hubs');
      expect(got.url.queryParameters, {'limit': '50'});
      expect(hubs.map((h) => h.name), ['Washington Terminal', 'Dian']);
      expect(hubs.map((h) => h.isTerminal), [true, false]);
      expect(hubs.first.lat, 14.55856);
      expect(hubs.first.lng, 121.0, reason: 'a whole number is read as a double');
      expect(hubs.first.errorM, 80);
      expect(hubs.first.modesLabel, 'Jeepney · UV Express');
    });

    test('passes the kind and mode filters along', () async {
      late http.Request got;
      final api = apiWith(
        MockClient((req) async {
          got = req;
          return jsonResponse([], 200);
        }),
      );
      expect(await api.hubs(kind: 'terminal', mode: 'p2p_bus', limit: 5), isEmpty);
      expect(got.url.queryParameters, {'limit': '5', 'kind': 'terminal', 'mode': 'p2p_bus'});
    });

    test('a hub becomes a Place to walk to; an unknown mode shows as sent', () {
      final hub = Hub.fromJson({...serverHub(), 'modes': ['jeepney', 'ferry']});
      expect(hub.place.label, 'Washington Terminal');
      expect(hub.place.lat, 14.55856);
      expect(hub.modesLabel, 'Jeepney · ferry');
    });

    test('a server error is an ApiException', () {
      final api = apiWith(MockClient((_) async => jsonResponse({'detail': 'Server error.'}, 500)));
      expect(api.hubs(), apiError('Server error.'));
    });
  });
}
