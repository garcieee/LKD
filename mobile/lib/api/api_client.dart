// The server's API at Env.apiBaseUrl: reports (server/app/routers/reports.py), place search
// (server/app/routers/geocode.py), walking routes (server/app/routers/routes.py) and transit hubs
// (server/app/routers/transit.py). An SOS goes up as a video to POST /sos (server/app/routers/reports.py).
// Report mirrors server/app/db/models.py, minus what the app never shows: severity and the ticket engine's fields
// (sos_kind, district_id, priority, band). A field it does not list is ignored.
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
  // Accessibility barriers for persons with disability. Only the Accessible route steers around the first three;
  // a steep or broken sidewalk trips anyone, so Walkable avoids it too.
  'missing_ramp': 'Missing or broken ramp',
  'blocked_tactile_paving': 'Blocked or missing tactile paving',
  'broken_elevator': 'Broken elevator or escalator',
  'unsafe_sidewalk': 'Steep or broken sidewalk',
  'other': 'Other',
};

/// The category of an SOS. Not in [categoryLabels]: nobody picks it. Only the shutter's hold-to-record files one.
const sosCategory = 'sos';
const sosLabel = 'SOS';

/// Open -> Verified -> Assigned -> Fixed, set by the dashboard. Rejected: the city judged it not real. The public list
/// never sends one, but /my-tickets does, to the phone that filed it.
const statusLabels = {
  'open': 'Open',
  'verified': 'Verified',
  'assigned': 'Assigned',
  'fixed': 'Fixed',
  'rejected': 'Rejected',
};

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
      videoUrl = json['video_url'] as String?,
      status = statusLabels.containsKey(json['status']) ? json['status'] as String : 'open',
      createdAt = DateTime.parse(json['created_at'] as String),
      updatedAt = DateTime.tryParse('${json['updated_at']}') ?? DateTime.parse(json['created_at'] as String),
      ticketId = json['ticket_id'] as String?,
      handler = json['handler'] as String?,
      verifiedNote = json['verified_note'] as String?,
      rejectedNote = json['rejected_note'] as String?,
      resolvedNote = json['resolved_note'] as String?,
      source = json;

  final String id;
  final String category;
  final double lat;
  final double lng;
  final double? heading; // compass heading of the camera when the photo was taken
  final String note;
  final String photoUrl; // a path on the server, e.g. /photos/<id>.jpg. Empty for an SOS
  final String? videoUrl; // an SOS only: a path on the server, e.g. /videos/<id>.mp4
  final String status;
  final DateTime createdAt;
  final DateTime updatedAt; // when the status last changed, so a phone can tell a ticket has news
  final String? ticketId; // the ticket this report is a sighting of, once the server has made one
  final String? handler; // who was assigned to fix it, once the city has
  // Notes the city left for the reporter. Only /my-tickets sends them: the public list leaves them out.
  final String? verifiedNote; // when it confirmed the report (optional)
  final String? rejectedNote; // why it rejected it (always given)
  final String? resolvedNote; // when it marked it resolved (optional)
  final Map<String, dynamic> source; // the JSON this came from, so a phone can keep the ticket and read it back

  bool get isSos => category == sosCategory;

  /// "LKD-3F2A9C": what the dashboard shows as the ticket's ID, so someone can read it out and be found there.
  String get code => 'LKD-${(ticketId ?? id).substring(0, math.min(6, (ticketId ?? id).length)).toUpperCase()}';

  String get label => isSos ? sosLabel : categoryLabels[category] ?? 'Other';
}

/// The route modes the server takes, with their labels, in the order the toggle shows them.
const routeModes = {'fastest': 'Fastest', 'walkable': 'Walkable', 'accessible': 'Accessible'};

/// One manoeuvre of a walking route, as the server's router sends it. No steps (a ride, an estimated walk, or a
/// router that sent none) is an empty list, never an error.
class RouteStep {
  RouteStep.fromJson(Map<String, dynamic> json)
    : type = (json['type'] as num).toInt(),
      text = json['text'] as String,
      name = json['name'] as String? ?? '',
      distanceM = (json['distance_m'] as num).toDouble(),
      at = (json['at'] as num).toInt();

  final int type; // ORS's turn code: see [turnIcon] in features/navigate/nav_bar.dart
  final String text; // "Turn right onto Paseo de Roxas"
  final String name; // the street this step goes along, empty when it has none
  final double distanceM; // along this step, until the next manoeuvre
  final int at; // index into the line where the manoeuvre happens
}

List<RouteStep> _steps(Map<String, dynamic> json) => [
  for (final s in json['steps'] as List? ?? const []) RouteStep.fromJson(s as Map<String, dynamic>),
];

/// A walking route: GET /route/walk answers one of these per mode.
class WalkRoute {
  WalkRoute.fromJson(Map<String, dynamic> json)
    : mode = json['mode'] as String,
      distanceM = (json['distance_m'] as num).toDouble(),
      durationS = (json['duration_s'] as num).toDouble(),
      line = [
        for (final p in json['geometry'] as List) [for (final n in p as List) (n as num).toDouble()],
      ],
      steps = _steps(json),
      hazardIds = [for (final id in json['hazard_ids'] as List) id as String],
      avoidsHazards = json['avoids_hazards'] as bool;

  final String mode; // a key of routeModes
  final double distanceM;
  final double durationS;
  final List<List<double>> line; // [[lng, lat], ...], the order Mapbox takes
  final List<RouteStep> steps; // turn by turn along [line]
  final List<String> hazardIds; // unresolved reports within 20 m of the line
  final bool avoidsHazards; // false for Fastest, and when the server could not route around hazards
}

/// One stretch of a commute: a walk, or a ride on one kind of PUV or train.
class CommuteLeg {
  CommuteLeg.fromJson(Map<String, dynamic> json)
    : kind = json['kind'] as String,
      durationS = (json['duration_s'] as num).toDouble(),
      distanceM = (json['distance_m'] as num).toDouble(),
      label = json['label'] as String,
      line = [
        for (final p in json['geometry'] as List) [for (final n in p as List) (n as num).toDouble()],
      ],
      steps = _steps(json);

  /// A walking route as a single leg, for a trip with no ride.
  CommuteLeg.walk(WalkRoute r, this.label)
    : kind = 'walk',
      durationS = r.durationS,
      distanceM = r.distanceM,
      line = r.line,
      steps = r.steps;

  final String kind; // 'walk', or a key of hubModeLabels
  final double durationS;
  final double distanceM;
  final String label; // e.g. "Walk to Ayala Terminal"
  final List<List<double>> line; // [[lng, lat], ...]
  final List<RouteStep> steps; // a street-routed walk only; a ride or an estimated walk has none

  bool get isWalk => kind == 'walk';
}

/// A way to get there by walking and riding: GET /route/commute answers a list of these, quickest first.
/// The ride is an estimate: the server has no timetables or route lines.
class CommuteOption {
  CommuteOption.fromJson(Map<String, dynamic> json)
    : id = json['id'] as String,
      totalS = (json['total_s'] as num).toDouble(),
      walkS = (json['walk_s'] as num).toDouble(),
      tags = [for (final t in json['tags'] as List) t as String],
      legs = [for (final l in json['legs'] as List) CommuteLeg.fromJson(l as Map<String, dynamic>)];

  final String id;
  final double totalS;
  final double walkS;
  final List<String> tags; // 'earliest', 'least_walking'
  final List<CommuteLeg> legs;

  bool get isEarliest => tags.contains('earliest');
}

/// A place the search found: GET /geocode answers a list of these.
class Place {
  const Place({required this.label, required this.lat, required this.lng});

  Place.fromJson(Map<String, dynamic> json)
    : this(
        label: json['label'] as String,
        lat: (json['lat'] as num).toDouble(),
        lng: (json['lng'] as num).toDouble(),
      );

  final String label; // e.g. "Ayala Triangle Gardens, Makati, Philippines"
  final double lat;
  final double lng;
}

/// What serves a hub, with labels: the study's four kinds of PUV, then the two running train lines.
const hubModeLabels = {
  'jeepney': 'Jeepney',
  'uv_express': 'UV Express',
  'city_bus': 'City bus',
  'p2p_bus': 'P2P bus',
  'mrt3': 'MRT-3',
  'lrt1': 'LRT-1',
};

/// A PUV terminal or bus stop from the 2025 Makati PUV study, or an MRT-3 / LRT-1 station: GET /transit/hubs
/// answers a list of these. The position is an estimate, [errorM] metres of doubt around it.
/// A station also lists the PUV that stop at it, train first.
class Hub {
  Hub.fromJson(Map<String, dynamic> json)
    : id = json['id'] as String,
      name = json['name'] as String,
      kind = json['kind'] as String,
      modes = [for (final m in json['modes'] as List) m as String],
      lat = (json['lat'] as num).toDouble(),
      lng = (json['lng'] as num).toDouble(),
      errorM = (json['error_m'] as num).round();

  final String id;
  final String name; // as printed on the study's map, e.g. "Washington Terminal"
  final String kind; // 'terminal', 'stop' (a bus stop) or 'station' (a train station)
  final List<String> modes; // keys of hubModeLabels
  final double lat;
  final double lng;
  final int errorM;

  bool get isTerminal => kind == 'terminal';
  bool get isStation => kind == 'station';

  /// "Terminal", "Bus stop" or "Station".
  String get kindLabel => switch (kind) {
    'terminal' => 'Terminal',
    'station' => 'Station',
    _ => 'Bus stop',
  };

  /// "Jeepney · UV Express".
  String get modesLabel => [for (final m in modes) hubModeLabels[m] ?? m].join(' · ');

  Place get place => Place(label: name, lat: lat, lng: lng);
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
  ApiClient({
    http.Client? client,
    String base = Env.apiBaseUrl,
    this.timeout = const Duration(seconds: 20),
    this.sosTimeout = const Duration(seconds: 90),
  }) : base = base.replaceFirst(RegExp(r'/+$'), ''), // "http://host:8000/" would make every call "//reports"
       _http = client ?? http.Client();

  final http.Client _http;
  final String base; // no trailing slash
  final Duration timeout; // per call, upload included
  final Duration sosTimeout; // a video over a weak connection: longer than a photo, still one call

  /// Every report, newest first.
  Future<List<Report>> reports() async {
    final body = await _send(http.AbortableRequest('GET', Uri.parse('$base/reports'), abortTrigger: _deadline()));
    return [for (final r in body as List) Report.fromJson(r as Map<String, dynamic>)];
  }

  /// The reports this phone filed, by [ids] (at most 100), in the order asked, with the city's notes to the reporter.
  /// There are no accounts: only the phone that filed a ticket knows its id, so asking for it is the proof it is
  /// theirs, and an SOS or a rejected ticket comes back too. An id the server does not know is left out.
  Future<List<Report>> myTickets(List<String> ids) async {
    if (ids.isEmpty) return const [];
    final url = Uri.parse('$base/my-tickets').replace(queryParameters: {'ids': ids.join(',')});
    final body = await _send(http.AbortableRequest('GET', url, abortTrigger: _deadline()));
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

  /// Makati's PUV terminals and bus stops, optionally only one [kind] ('terminal' or 'stop') or [mode]. Not sorted:
  /// the app sorts by the user's position as it moves.
  Future<List<Hub>> hubs({String? kind, String? mode, int limit = 50}) async {
    final url = Uri.parse('$base/transit/hubs').replace(
      queryParameters: {'limit': '$limit', 'kind': ?kind, 'mode': ?mode},
    );
    final body = await _send(http.AbortableRequest('GET', url, abortTrigger: _deadline()));
    return [for (final h in body as List) Hub.fromJson(h as Map<String, dynamic>)];
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

  /// Ways to get from [from] to [to] by walking and riding one PUV or train. The walking legs are routed in
  /// [mode], a key of routeModes.
  Future<List<CommuteOption>> commute({
    required ({double lat, double lng}) from,
    required ({double lat, double lng}) to,
    required String mode,
  }) async {
    final url = Uri.parse('$base/route/commute').replace(
      queryParameters: {
        'from_lat': '${from.lat}',
        'from_lng': '${from.lng}',
        'to_lat': '${to.lat}',
        'to_lng': '${to.lng}',
        'mode': mode,
      },
    );
    final body = await _send(http.AbortableRequest('GET', url, abortTrigger: _deadline()));
    return [for (final o in body as List) CommuteOption.fromJson(o as Map<String, dynamic>)];
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

  /// Sends an SOS: the clip the shutter recorded, filed at once as an urgent ticket (POST /sos). [onProgress] gets
  /// the share uploaded so far, 0..1. The server reads the container from the bytes (MP4, MOV or WebM).
  Future<Report> sendSos({
    required Uint8List video,
    required double lat,
    required double lng,
    double? heading,
    void Function(double sent)? onProgress,
  }) async {
    final req = http.AbortableMultipartRequest('POST', Uri.parse('$base/sos'), abortTrigger: _deadline(sosTimeout))
      ..fields.addAll({'lat': '$lat', 'lng': '$lng', if (heading != null) 'heading': '$heading'})
      ..files.add(
        http.MultipartFile(
          'video',
          _chunks(video, onProgress),
          video.length,
          filename: 'sos.mp4',
          contentType: http.MediaType('video', 'mp4'),
        ),
      );
    return Report.fromJson(await _send(req, within: sosTimeout) as Map<String, dynamic>);
  }

  // Aborts the call, socket and all, so a retry after a timeout cannot race a slow first upload.
  Future<void> _deadline([Duration? within]) => Future.delayed(within ?? timeout);

  // The answer's JSON. [within] is the deadline the request was given, for the message.
  Future<Object?> _send(http.BaseRequest request, {Duration? within}) async {
    final http.Response res;
    try {
      res = await http.Response.fromStream(await _http.send(request));
    } on http.RequestAbortedException {
      throw ApiException('No answer from the server in ${(within ?? timeout).inSeconds} s. Try again.');
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

// The photo (or SOS video) in 64 KB pieces, so progress moves as the connection takes them.
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
