// The phone's ApiClient against a real server instead of a mock. Skipped unless LAKAD_API_URL is set.
// It files reports, so point it at a server on throwaway storage:
//   cd server && STORAGE_DIR=/tmp/lakad-contract .venv/bin/uvicorn app.main:app --port 8000
//   cd mobile && LAKAD_API_URL=http://localhost:8000 flutter test test/api_contract_test.dart
// No testWidgets in this file: its binding would swap real HTTP for a fake that answers 400.
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:lakad/api/api_client.dart';
import 'package:lakad/config/makati.dart';
import 'package:lakad/features/report/ar_math.dart';

final base = Platform.environment['LAKAD_API_URL'];
final skip = base == null ? 'Set LAKAD_API_URL to a running server to check the contract.' : null;

// A real 1x1 grey baseline JPEG, 141 bytes: one quantisation table, one-code Huffman tables.
final jpeg = base64Decode(
  '/9j/2wBDAAEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQH/wAALCAAB'
  'AAEBAREA/8QAFAABAAAAAAAAAAAAAAAAAAAAAP/EABQQAQAAAAAAAAAAAAAAAAAAAAD/2gAIAQEAAD8AP//Z',
);

// An MP4's first bytes (an `ftyp` box) and filler: the server reads the container from the bytes.
final mp4 = Uint8List.fromList([0, 0, 0, 0x18, ...'ftypmp42'.codeUnits, ...List.filled(2048, 0)]);

Object fields(Report r) => (r.id, r.category, r.lat, r.lng, r.heading, r.note, r.photoUrl, r.status, r.createdAt);

Matcher apiError(Object message) => throwsA(isA<ApiException>().having((e) => e.message, 'message', message));

void main() {
  final api = ApiClient(base: base ?? 'http://unset');
  Future<Report> send({double lat = 14.5547, double lng = 121.0244, double? heading, String category = 'other'}) =>
      api.sendReport(photo: jpeg, category: category, lat: lat, lng: lng, heading: heading);

  test('a report goes up and comes back the same, photo and all', () async {
    const note = 'Baha — hanggang tuhod 🌊'; // not ASCII: the multipart field is UTF-8
    final sent = await api.sendReport(
      photo: jpeg,
      category: 'flooded_drain',
      lat: 14.5547,
      lng: 121.0244,
      heading: 87.5,
      note: note,
    );
    expect((sent.category, sent.lat, sent.lng, sent.heading, sent.note), ('flooded_drain', 14.5547, 121.0244, 87.5, note));
    expect((sent.status, sent.label, sent.photoUrl), ('open', 'Flooded drain', '/photos/${sent.id}.jpg'));
    expect(sent.createdAt.isUtc, isTrue);
    expect(DateTime.now().difference(sent.createdAt).abs(), lessThan(const Duration(minutes: 1)));

    final listed = await api.reports();
    expect(fields(listed.first), fields(sent)); // newest first, and read the same both ways

    final photo = await http.get(Uri.parse('$base${sent.photoUrl}')); // what the pin card loads
    expect(photo.statusCode, 200);
    expect(photo.headers['content-type'], 'image/jpeg');
    expect(photo.bodyBytes, jpeg);
  }, skip: skip);

  test('an SOS goes up as a video, comes back as an urgent ticket with its clip, and stays out of the public list', () async {
    final sent = await api.sendSos(video: mp4, lat: 14.5547, lng: 121.0244, heading: 12);
    expect((sent.category, sent.isSos, sent.status, sent.photoUrl), ('sos', true, 'open', ''));
    expect(sent.videoUrl, '/videos/${sent.id}.mp4');

    final clip = await http.get(Uri.parse('$base${sent.videoUrl}')); // what the dashboard plays
    expect(clip.statusCode, 200);
    expect(clip.headers['content-type'], 'video/mp4');
    expect(clip.bodyBytes, mp4);

    expect((await api.reports()).any((r) => r.id == sent.id), isFalse, reason: 'the public list leaves SOS out');
    final all = await http.get(Uri.parse('$base/reports?include_sos=true')); // the dashboard asks for them
    expect((jsonDecode(all.body) as List).first['id'], sent.id);
  }, skip: skip);

  test('the server takes every category the picker offers, and a heading of 0 or 360', () async {
    for (final category in categoryLabels.keys) {
      expect((await send(category: category)).category, category);
    }
    for (final heading in [0.0, 360.0]) {
      expect((await send(heading: heading)).heading, heading);
    }
  }, skip: skip);

  test('the server draws the city line exactly where inMakati does', () async {
    const m = cityMarginDeg, hair = 1e-9;
    final (s, n, w, e) = (Makati.south - m, Makati.north + m, Makati.west - m, Makati.east + m);
    for (final (lat, lng) in [(s, w), (n, e)]) {
      expect(inMakati(lat, lng), isTrue);
      expect((await send(lat: lat, lng: lng)).lat, lat); // on the line: the shutter is on, so must the server be
    }
    for (final (lat, lng) in [(s - hair, w), (n + hair, e), (s, w - hair), (n, e + hair)]) {
      expect(inMakati(lat, lng), isFalse);
      await expectLater(send(lat: lat, lng: lng), apiError('That location is outside the city.'));
    }
  }, skip: skip);

  test("the server's field errors come out one per line", () async {
    await expectLater(send(heading: 400), apiError(allOf(startsWith('heading: '), contains('360'))));
  }, skip: skip);
}
