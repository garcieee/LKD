// The server's API at Env.apiBaseUrl: reports (server/app/routers/reports.py), place search
// (server/app/routers/geocode.py) and walking routes (server/app/routers/routes.py).
// Report mirrors server/app/db/models.py, minus severity and updated_at, which the app never shows.
import 'dart:convert';
import 'dart:math' as math;
import 'dart:typed_data';

import 'package:http/http.dart' as http;

import '../config/env.dart';

/// The categories the server takes, with their labels, in the order the picker shows them.
const categoryLabels = {
  'pothole': 'Pothole',
  'open_manhole': 'Open manhole',
  'flooded_drain': 'Flooded drain',
  'broken_streetlight': 'Broken streetlight',
  'blocked_sidewalk': 'Blocked sidewalk',
  'other': 'Other',
};

/// Open -> Verified -> Assigned -> Fixed, set by the dashboard.
const statusLabels = {'open': 'Open', 'verified': 'Verified', 'assigned': 'Assigned', 'fixed': 'Fixed'};

class Report {
  /// A status this app does not know reads as open, so the report still shows.
  Report.fromJson(Map<String, dynamic> json)
    : id = json['id'] as String,
      category = json['category'] as String,
      lat = (json['lat'] as num).toDouble(),
      lng = (json['lng'] as num).toDouble(),
      heading = (json['heading'] as num?)?.toDouble(),
      note = json['note'] as String? ?? '',
      photoUrl = json['photo_url'] as String,
      status = statusLabels.containsKey(json['status']) ? json['status'] as String : 'open',
      createdAt = DateTime.parse(json['created_at'] as String);

  final String id;
  final String category;
  final double lat;
  final double lng;
  final double? heading; // compass heading of the camera when the photo was taken
  final String note;
  final String photoUrl; // a path on the server, e.g. /photos/<id>.jpg
  final String status;
  final DateTime createdAt;

  String get label => categoryLabels[category] ?? 'Other';
}

/// The route modes the server takes, with their labels, in the order the toggle shows them.
const routeModes = {'fastest': 'Fastest', 'walkable': 'Walkable', 'accessible': 'Accessible'};

/// A walking route: GET /route/walk answers one of these per mode.
class WalkRoute {
  WalkRoute.fromJson(Map<String, dynamic> json)
    : mode = json['mode'] as String,
      distanceM = (json['distance_m'] as num).toDouble(),
      durationS = (json['duration_s'] as num).toDouble(),
      line = [
        for (final p in json['geometry'] as List) [for (final n in p as List) (n as num).toDouble()],
      ],
      hazardIds = [for (final id in json['hazard_ids'] as List) id as String],
      avoidsHazards = json['avoids_hazards'] as bool;

  final String mode; // a key of routeModes
  final double distanceM;
  final double durationS;
  final List<List<double>> line; // [[lng, lat], ...], the order Mapbox takes
  final List<String> hazardIds; // unresolved reports within 20 m of the line
  final bool avoidsHazards; // false for Fastest, and when the server could not route around hazards
}

/// A place the search found: GET /geocode answers a list of these.
class Place {
  Place.fromJson(Map<String, dynamic> json)
    : label = json['label'] as String,
      lat = (json['lat'] as num).toDouble(),
      lng = (json['lng'] as num).toDouble();

  final String label; // e.g. "Ayala Triangle Gardens, Makati, Philippines"
  final double lat;
  final double lng;
}

/// A failed call, with a message fit to show the user.
class ApiException implements Exception {
  const ApiException(this.message);

  final String message;

  @override
  String toString() => message;
}

/// The client the app uses.
final api = ApiClient();

class ApiClient {
  ApiClient({http.Client? client, this.base = Env.apiBaseUrl, this.timeout = const Duration(seconds: 20)})
    : _http = client ?? http.Client();

  final http.Client _http;
  final String base;
  final Duration timeout; // per call, upload included

  /// Every report, newest first.
  Future<List<Report>> reports() async {
    final body = await _send(http.AbortableRequest('GET', Uri.parse('$base/reports'), abortTrigger: _deadline()));
    return [for (final r in body as List) Report.fromJson(r as Map<String, dynamic>)];
  }

  /// Places in Makati matching [text], best first. [near] (lat, lng) ranks nearby places higher.
  Future<List<Place>> geocode(String text, {({double lat, double lng})? near}) async {
    final url = Uri.parse('$base/geocode').replace(
      queryParameters: {'q': text, if (near != null) ...{'lat': '${near.lat}', 'lng': '${near.lng}'}},
    );
    final body = await _send(http.AbortableRequest('GET', url, abortTrigger: _deadline()));
    return [for (final p in body as List) Place.fromJson(p as Map<String, dynamic>)];
  }

  /// A walking route between two points in Makati. A 404 ("No walking route found…") is an ApiException.
  Future<WalkRoute> route({
    required ({double lat, double lng}) from,
    required ({double lat, double lng}) to,
    required String mode,
  }) async {
    final url = Uri.parse('$base/route/walk').replace(
      queryParameters: {
        'from_lat': '${from.lat}',
        'from_lng': '${from.lng}',
        'to_lat': '${to.lat}',
        'to_lng': '${to.lng}',
        'mode': mode,
      },
    );
    final body = await _send(http.AbortableRequest('GET', url, abortTrigger: _deadline()));
    return WalkRoute.fromJson(body as Map<String, dynamic>);
  }

  /// Files a report. [onProgress] gets the share of the photo uploaded so far, 0..1.
  Future<Report> sendReport({
    required Uint8List photo,
    required String category,
    required double lat,
    required double lng,
    double? heading,
    String note = '',
    void Function(double sent)? onProgress,
  }) async {
    final req = http.AbortableMultipartRequest('POST', Uri.parse('$base/reports'), abortTrigger: _deadline())
      ..fields.addAll({
        'category': category,
        'lat': '$lat',
        'lng': '$lng',
        if (heading != null) 'heading': '$heading',
        if (note.isNotEmpty) 'note': note,
      })
      // FastAPI only treats a part as a file when it has a filename. The server checks the bytes.
      ..files.add(
        http.MultipartFile(
          'photo',
          _chunks(photo, onProgress),
          photo.length,
          filename: 'report.jpg',
          contentType: http.MediaType('image', 'jpeg'),
        ),
      );
    return Report.fromJson(await _send(req) as Map<String, dynamic>);
  }

  // Aborts the call, socket and all, so a retry after a timeout cannot race a slow first upload.
  Future<void> _deadline() => Future.delayed(timeout);

  // The answer's JSON.
  Future<Object?> _send(http.BaseRequest request) async {
    final http.Response res;
    try {
      res = await http.Response.fromStream(await _http.send(request));
    } on http.RequestAbortedException {
      throw ApiException('No answer from the server in ${timeout.inSeconds} s. Try again.');
    } on http.ClientException catch (e) {
      throw ApiException("Can't reach the server at $base (${e.message}). Check the connection and try again.");
    }
    if (res.statusCode >= 300) throw ApiException(_detail(res));
    try {
      return jsonDecode(res.body);
    } on FormatException {
      // e.g. a Wi-Fi sign-in page answering in the server's place
      throw ApiException("Can't read the answer from $base. Check the connection and try again.");
    }
  }
}

// The photo in 64 KB pieces, so progress moves as the connection takes them.
Stream<List<int>> _chunks(Uint8List bytes, void Function(double)? onProgress) async* {
  const size = 64 * 1024;
  for (var start = 0; start < bytes.length; start += size) {
    final end = math.min(start + size, bytes.length);
    yield Uint8List.sublistView(bytes, start, end);
    onProgress?.call(end / bytes.length);
  }
}

// FastAPI says what went wrong as {"detail": "..."}, or for bad fields
// {"detail": [{"loc": ["body", "note"], "msg": "..."}, ...]}.
String _detail(http.Response res) {
  try {
    final detail = (jsonDecode(res.body) as Map)['detail'];
    if (detail is String) return detail;
    if (detail is List) return [for (final d in detail) '${(d['loc'] as List).last}: ${d['msg']}'].join('\n');
  } catch (_) {
    // not FastAPI's JSON, e.g. a proxy's error page
  }
  return 'Server error ${res.statusCode}.';
}
